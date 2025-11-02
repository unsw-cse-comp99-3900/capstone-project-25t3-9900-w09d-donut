# ai_agents/services/summarizer.py
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Union, cast

from ai_agents.llm.gemini_client import GeminiClient, GeminiText

from .models import PaperSummary
from .tooling import AgentTool, ToolContext, ToolResult


# -------- Data models --------
@dataclass
class PaperInput:
    id: str
    title: str
    abstract: str
    url: str
    year: Optional[int] = None
    authors: Optional[List[str]] = None
    concepts: Optional[List[str]] = None


@dataclass
class SummarizeRequest:
    papers: List[Union[PaperInput, Dict[str, object], PaperSummary]]
    user_goal: str = "Summarize the topic"
    style: str = "bulleted"  # bulleted | paragraph | outline
    include_citations: bool = True
    max_items: int = 8
    max_abstract_chars: int = 1200
    temperature: float = 0.4
    max_output_tokens: int = 1024
    mode: str = "quick"  # quick | global | focused | comprehensive
    focus_aspect: Optional[str] = None
    language: str = "en"
    system_prompt: Optional[str] = None
    conversation_summary: Optional[str] = None


@dataclass
class SummarizeResult:
    text: str
    used_count: int
    citations: List[str]
    prompt_tokens_estimate: int
    citations_map: Dict[str, str] = field(default_factory=dict)  # marker -> title/url
    cost_estimate: Optional[float] = None


# -------- Helpers --------
def _coerce_paper(x: Union[PaperInput, Dict[str, object], PaperSummary]) -> PaperInput:
    if isinstance(x, PaperInput):
        return x
    if isinstance(x, PaperSummary):
        return PaperInput(
            id=x.paper_id,
            title=x.title,
            abstract=x.abstract,
            url=x.url or "",
            year=x.year,
            authors=list(x.authors),
        )
    data = cast(Mapping[str, object], x)
    return PaperInput(
        id=str(data.get("id", "")),
        title=str(data.get("title", "")),
        abstract=str(data.get("abstract", "")),
        url=str(data.get("url", "")),
        year=data.get("year"),  # type: ignore[arg-type]
        authors=list(data.get("authors", [])) if data.get("authors") else None,  # type: ignore[arg-type]
        concepts=list(data.get("concepts", [])) if data.get("concepts") else None,  # type: ignore[arg-type]
    )


def _truncate(s: str, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else (s[: n - 3] + "...")


def _estimate_prompt_tokens(chars: int) -> int:
    return max(1, chars // 4)


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


# -------- Summarizer --------
class PaperSummarizer:
    """
    Core summarizer that prepares prompts and calls Gemini.
    Provides light caching to avoid duplicate LLM calls during a session.
    """

    def __init__(self, gemini: Optional[GeminiClient] = None, enable_cache: bool = True):
        self._client = gemini or GeminiClient()
        self._text: GeminiText = self._client.text
        self._enable_cache = enable_cache
        self._cache: Dict[str, SummarizeResult] = {}

    def summarize(self, req: SummarizeRequest) -> SummarizeResult:
        papers = [_coerce_paper(p) for p in req.papers][: max(1, req.max_items)]
        prompt, titles_for_cite, citations_map = self._build_prompt(papers, req)

        cache_key = _hash_prompt(prompt + req.mode + req.style + (req.focus_aspect or "") + (req.system_prompt or ""))
        if self._enable_cache and cache_key in self._cache:
            cached = self._cache[cache_key]
            return SummarizeResult(
                text=cached.text,
                used_count=cached.used_count,
                citations=list(cached.citations),
                prompt_tokens_estimate=cached.prompt_tokens_estimate,
                citations_map=dict(cached.citations_map),
                cost_estimate=cached.cost_estimate,
            )

        out = self._text.chat(
            prompt,
            temperature=req.temperature,
            max_output_tokens=req.max_output_tokens,
        )

        result = SummarizeResult(
            text=out.strip(),
            used_count=len(papers),
            citations=titles_for_cite,
            prompt_tokens_estimate=_estimate_prompt_tokens(len(prompt)),
            citations_map=citations_map,
            cost_estimate=None,
        )

        if self._enable_cache:
            self._cache[cache_key] = result
        return result

    def summarize_plain(self, papers: List[Union[PaperInput, Dict[str, object], PaperSummary]], user_goal: str, max_items: int = 8) -> str:
        req = SummarizeRequest(papers=papers, user_goal=user_goal, max_items=max_items)
        return self.summarize(req).text

    def _build_prompt(self, papers: Iterable[PaperInput], req: SummarizeRequest) -> tuple[str, List[str], Dict[str, str]]:
        style_line = {
            "bulleted": "Return a concise bulleted list (3-8 bullets).",
            "paragraph": "Return one or two concise paragraphs.",
            "outline": "Return a short outline with hierarchical bullet points.",
        }.get(req.style, "Return a concise bulleted list (3-8 bullets).")

        cite_line = (
            "When referencing evidence, append bracket citations using the numbered titles, e.g., [1], [2]."
            if req.include_citations
            else "Do not include bracket citations."
        )

        language_line = "Respond in English."
        if req.language.lower().startswith("zh"):
            language_line = "Respond in Chinese."
        elif req.language.lower() not in ("en", "english"):
            language_line = f"Respond in {req.language}."

        focus_line = ""
        if req.focus_aspect:
            focus_line = f"Emphasize details related to: {req.focus_aspect}."

        mode_directive = {
            "quick": "Provide a high-level synthesis that highlights the most relevant insights.",
            "global": "Provide an academic-style synthesis covering background, methods, findings, and gaps.",
            "focused": "Provide a comparative analysis focused on the requested aspect.",
            "comprehensive": "Provide a detailed, structured summary covering context, methodology, experiments, key findings, limitations, and future work.",
        }.get(req.mode, "Provide a high-level synthesis.")

        items: List[str] = []
        titles_for_cite: List[str] = []
        citations_map: Dict[str, str] = {}

        for idx, paper in enumerate(papers, start=1):
            title = paper.title.strip() or f"Paper {idx}"
            abstract = _truncate(paper.abstract or "", req.max_abstract_chars)
            year = f"{paper.year}" if paper.year is not None else "N/A"
            url = paper.url or ""
            authors = ", ".join(paper.authors or [])[:200]
            block = (
                f"[{idx}] Title: {title}\n"
                f"Year: {year}\n"
                f"URL: {url}\n"
                f"Authors: {authors}\n"
                f"Abstract: {abstract}\n"
            )
            items.append(block)
            titles_for_cite.append(title)
            citations_map[f"[{idx}]"] = url or title

        context = "\n\n".join(items)

        prompt = f"""You are an academic assistant.
Overall task: {req.user_goal}

Instructions:
- {mode_directive}
- Be accurate and non-redundant; avoid hallucinations.
- {style_line}
- {language_line}
- {cite_line}
- {focus_line}

"""
        if req.system_prompt:
            prompt = req.system_prompt.strip() + "\n\n" + prompt

        if req.conversation_summary:
            prompt += f"\nConversation context:\n{req.conversation_summary.strip()}\n"

        prompt += "\nPapers:\n" + context + "\n"
        return prompt, titles_for_cite, citations_map


# -------- Tool wrappers --------
@dataclass
class QuickSummaryTool(AgentTool):
    name: str = "quick_summary"
    summarizer: PaperSummarizer = field(default_factory=PaperSummarizer)

    def execute(self, context: ToolContext, payload: Mapping[str, object]) -> ToolResult:
        papers = payload.get("papers") or []
        if not papers:
            return ToolResult(
                text="No papers available for summary.",
                selected_ids=payload.get("selected_ids") or [],
                citations=[],
            )

        req = SummarizeRequest(
            papers=list(papers),
            user_goal=str(payload.get("user_goal") or "Summarize the selected papers"),
            style=str(payload.get("style") or "bulleted"),
            include_citations=bool(payload.get("include_citations", True)),
            max_items=int(payload.get("max_items", 6)),
            mode="quick",
            focus_aspect=payload.get("focus_aspect"),
            language=str(payload.get("language") or "en"),
            system_prompt=payload.get("system_prompt"),
            conversation_summary=payload.get("conversation_summary"),
        )
        result = self.summarizer.summarize(req)
        return ToolResult(
            text=result.text,
            citations=result.citations,
            selected_ids=payload.get("selected_ids") or [],
            metadata={
                "used_count": result.used_count,
                "prompt_tokens": result.prompt_tokens_estimate,
                "citations_map": result.citations_map,
            },
        )


@dataclass
class GlobalSummaryTool(AgentTool):
    name: str = "global_summary"
    summarizer: PaperSummarizer = field(default_factory=PaperSummarizer)

    def execute(self, context: ToolContext, payload: Mapping[str, object]) -> ToolResult:
        papers = payload.get("papers") or []
        if not papers:
            return ToolResult(text="No papers available for global summary.", citations=[], selected_ids=[])

        req = SummarizeRequest(
            papers=list(papers),
            user_goal=str(payload.get("user_goal") or "Produce a comprehensive scientific synthesis"),
            style=str(payload.get("style") or "paragraph"),
            include_citations=True,
            max_items=int(payload.get("max_items", 12)),
            mode=str(payload.get("mode") or "comprehensive"),
            language=str(payload.get("language") or "en"),
            system_prompt=payload.get("system_prompt"),
            conversation_summary=payload.get("conversation_summary"),
        )
        result = self.summarizer.summarize(req)
        return ToolResult(
            text=result.text,
            citations=result.citations,
            selected_ids=payload.get("selected_ids") or [],
            metadata={
                "used_count": result.used_count,
                "prompt_tokens": result.prompt_tokens_estimate,
                "citations_map": result.citations_map,
            },
        )
