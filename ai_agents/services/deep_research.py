from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from ai_agents.llm.gemini_client import GeminiClient, GeminiText


@dataclass
class GeneratedQuery:
    query: str
    focus: Optional[str] = None
    rationale: Optional[str] = None
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "focus": self.focus,
            "rationale": self.rationale,
            "keywords": list(self.keywords),
        }


@dataclass
class DeepResearchRound:
    round_index: int
    queries: List[Dict[str, Any]]
    findings: List[str]
    missing: List[str]
    sources: List[Dict[str, Any]]
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "round_index": self.round_index,
            "queries": self.queries,
            "findings": self.findings,
            "missing": self.missing,
            "sources": self.sources,
        }
        if self.notes:
            payload["notes"] = self.notes
        return payload

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "DeepResearchRound":
        return DeepResearchRound(
            round_index=int(data.get("round_index", 0)),
            queries=list(data.get("queries") or []),
            findings=list(data.get("findings") or []),
            missing=list(data.get("missing") or []),
            sources=list(data.get("sources") or []),
            notes=data.get("notes"),
        )


class DeepResearchAgent:
    """
    Lightweight controller that uses an LLM to manage deep research loops.
    It produces search queries, synthesizes round summaries, and builds final reports.
    """

    def __init__(
        self,
        llm: Optional[GeminiText] = None,
        *,
        max_docs_per_round: int = 8,
        max_chars_per_doc: int = 1800,
    ) -> None:
        self._llm = llm or GeminiClient().text
        self._max_docs = max_docs_per_round
        self._max_chars = max_chars_per_doc

    # ------------------------------------------------------------------ #
    # Query generation
    # ------------------------------------------------------------------ #
    def generate_queries(
        self,
        *,
        user_query: str,
        context: Sequence[Mapping[str, Any]],
        breadth: int = 3,
        language: str = "en",
        extra_instructions: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        breadth = max(1, min(int(breadth or 1), 6))
        context_text = _format_context(context)
        instruction_block = f"Additional guidance: {extra_instructions}" if extra_instructions else ""

        prompt = textwrap.dedent(
            f"""
            You are planning the next search round for a deep research investigation.

            Research question: {user_query.strip()}
            Prior findings and gaps:
            {context_text or 'No prior context available.'}

            Produce {breadth} diverse search ideas that build directly on the findings and missing knowledge above.
            Each idea should include the concrete query to run and the angle or hypothesis it addresses.
            Return strict JSON using this schema:
            {{
              "queries": [
                {{"query": "...", "focus": "...", "rationale": "...", "keywords": ["optional","tokens"]}}
              ],
              "notes": "optional planning comment"
            }}

            {instruction_block}
            Respond in {language}.
            """
        ).strip()

        raw = self._llm.chat(prompt, temperature=0.35, max_output_tokens=768)
        parsed = _extract_json_object(raw)
        queries_raw = parsed.get("queries") if isinstance(parsed, dict) else None

        queries: List[GeneratedQuery] = []
        if isinstance(queries_raw, list):
            for entry in queries_raw:
                query_text = str(entry.get("query") or "").strip()
                if not query_text:
                    continue
                keywords = entry.get("keywords") or []
                if isinstance(keywords, str):
                    keywords = [keywords]
                queries.append(
                    GeneratedQuery(
                        query=query_text,
                        focus=_maybe(entry.get("focus")),
                        rationale=_maybe(entry.get("rationale") or entry.get("reason")),
                        keywords=[str(k).strip() for k in keywords if str(k).strip()],
                    )
                )

        if not queries:
            fallback_lines = [
                line.strip(" -•\t")
                for line in (raw or "").splitlines()
                if line.strip(" -•\t")
            ]
            for line in fallback_lines[:breadth]:
                if not line:
                    continue
                queries.append(GeneratedQuery(query=line, keywords=[line]))

        return [q.to_dict() for q in queries[:breadth]]

    # ------------------------------------------------------------------ #
    # Round synthesis
    # ------------------------------------------------------------------ #
    def summarize_round(
        self,
        *,
        user_query: str,
        round_index: int,
        documents: Sequence[Mapping[str, Any]],
        queries: Sequence[Mapping[str, Any]],
        context: Sequence[Mapping[str, Any]],
        language: str = "en",
        instructions: Optional[str] = None,
    ) -> DeepResearchRound:
        if not documents:
            return DeepResearchRound(
                round_index=round_index,
                queries=[dict(q) for q in queries],
                findings=[],
                missing=["No documents were retrieved for this round."],
                sources=[],
                notes="Empty result set",
            )

        doc_blocks: List[str] = []
        doc_catalog: Dict[str, Dict[str, str]] = {}
        for idx, doc in enumerate(documents[: self._max_docs], start=1):
            doc_id = str(doc.get("id") or doc.get("paper_id") or idx)
            title = (doc.get("title") or doc.get("display_name") or f"Document {idx}").strip()
            snippet = (
                doc.get("full_text")
                or doc.get("summary")
                or doc.get("abstract")
                or ""
            ).strip()
            if len(snippet) > self._max_chars:
                snippet = snippet[: self._max_chars] + "..."
            url = doc.get("link") or doc.get("url") or doc.get("pdf_url") or ""
            doc_catalog[doc_id] = {"id": doc_id, "title": title, "url": url or ""}
            doc_blocks.append(
                f"[{doc_id}] Title: {title}\nURL: {url}\nSummary: {snippet}\n"
            )

        doc_section = "\n".join(doc_blocks)
        query_lines = [
            f"- {item.get('query')} ({item.get('focus') or 'general'})"
            for item in queries
        ]
        context_text = _format_context(context)
        instruction_block = f"User emphasis: {instructions}" if instructions else ""

        prompt = textwrap.dedent(
            f"""
            You just reviewed a batch of documents for a deep research investigation.
            Research question: {user_query.strip()}

            Recent search queries:
            {chr(10).join(query_lines) if query_lines else 'n/a'}

            Prior rounds summary:
            {context_text or 'This is the first round.'}

            Documents:
            {doc_section}

            Analyze the evidence and respond with JSON:
            {{
              "findings": [{{"statement": "...", "sources": ["doc_id"]}}],
              "missing": ["question we still need to investigate"],
              "sources": [{{"id": "doc_id", "title": "...", "url": "...", "reason": "why it matters"}}],
              "notes": "optional reflection"
            }}

            Requirements:
            - Findings must be grounded in the provided documents.
            - Include at least one gap or open question.
            - Prefer concise language.
            {instruction_block}
            Respond in {language}.
            """
        ).strip()

        raw = self._llm.chat(prompt, temperature=0.3, max_output_tokens=1024)
        parsed = _extract_json_object(raw)

        findings_payload = []
        for item in (parsed.get("findings") or []) if isinstance(parsed, dict) else []:
            if isinstance(item, str):
                findings_payload.append(item.strip())
            elif isinstance(item, Mapping):
                statement = str(item.get("statement") or item.get("summary") or "").strip()
                if statement:
                    findings_payload.append(statement)

        missing_payload = []
        for item in (parsed.get("missing") or []) if isinstance(parsed, dict) else []:
            if isinstance(item, str):
                missing_payload.append(item.strip())
            elif isinstance(item, Mapping):
                text = str(item.get("question") or item.get("gap") or "").strip()
                if text:
                    missing_payload.append(text)

        source_entries: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()

        if isinstance(parsed, dict):
            for item in parsed.get("sources") or []:
                if not isinstance(item, Mapping):
                    continue
                doc_id = str(item.get("id") or item.get("paper_id") or "").strip()
                if not doc_id:
                    continue
                meta = doc_catalog.get(doc_id)
                if not meta:
                    continue
                if doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)
                source_entries.append(
                    {
                        "id": doc_id,
                        "title": meta["title"],
                        "url": meta["url"],
                        "reason": _maybe(item.get("reason") or item.get("focus")),
                    }
                )

        if not source_entries:
            for doc_id, meta in list(doc_catalog.items())[:3]:
                if doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)
                source_entries.append(meta)

        notes = parsed.get("notes") if isinstance(parsed, dict) else None

        return DeepResearchRound(
            round_index=round_index,
            queries=[dict(q) for q in queries],
            findings=findings_payload,
            missing=missing_payload,
            sources=source_entries,
            notes=_maybe(notes),
        )

    # ------------------------------------------------------------------ #
    # Final report
    # ------------------------------------------------------------------ #
    def build_report(
        self,
        *,
        user_query: str,
        rounds: Sequence[Mapping[str, Any]],
        instructions: Optional[str] = None,
        language: str = "en",
    ) -> str:
        context_text = _format_context(rounds, include_sources=True)
        instruction_block = f"User preferences: {instructions}" if instructions else ""

        prompt = textwrap.dedent(
            f"""
            Produce a final research memo in Markdown synthesizing the investigation below.

            Research question: {user_query.strip()}
            Investigation rounds:
            {context_text or 'Only a single round of context is available.'}

            Requirements:
            - Structure the memo with sections: Overview, Key Findings, Evidence Table, Open Questions, Recommended Next Steps.
            - Cite evidence inline using [source-id] that matches the provided context.
            - Highlight how later rounds refined earlier assumptions.
            - Keep it concise but information-dense.
            {instruction_block}

            Respond in {language}.
            """
        ).strip()

        result = self._llm.chat(prompt, temperature=0.4, max_output_tokens=2048)
        return result.strip() or "No summary was generated."


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
def _extract_json_object(payload: str) -> Dict[str, Any]:
    payload = (payload or "").strip()
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        pass

    start = payload.find("{")
    end = payload.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = payload[start : end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            return {}
    return {}


def _format_context(context: Sequence[Mapping[str, Any]], *, include_sources: bool = False) -> str:
    if not context:
        return ""
    lines: List[str] = []
    for item in context:
        round_label = item.get("round_index") or len(lines) + 1
        findings = item.get("findings") or []
        missing = item.get("missing") or []
        lines.append(f"Round {round_label}:")
        for entry in findings:
            lines.append(f"  - Finding: {entry}")
        for gap in missing:
            lines.append(f"  - Gap: {gap}")
        if include_sources and item.get("sources"):
            src_lines = ", ".join(
                f"[{src.get('id')}] {src.get('title')}"
                for src in item["sources"][:5]
            )
            if src_lines:
                lines.append(f"  - Sources: {src_lines}")
    return "\n".join(lines)


def _maybe(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
