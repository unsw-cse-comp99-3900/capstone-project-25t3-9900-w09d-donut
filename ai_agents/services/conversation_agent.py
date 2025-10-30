from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Protocol, Sequence

from .focused_synthesis import FocusedSynthesisTool
from .models import (
    AgentReply,
    ConversationIntent,
    ConversationSession,
    PaperSummary,
    UploadedFileInfo,
)
from .query_refiner import KeywordExpansionTool
from .search_list_manager import SearchListManager
from .session_memory import SessionMemory
from .summarizer import GlobalSummaryTool, QuickSummaryTool
from .tooling import ToolContext, ToolExecutionError, ToolRegistry, ToolResult


# ---------------------------------------------------------------------------
# Protocols for pluggable components
# ---------------------------------------------------------------------------


class InsightGenerator(Protocol):
    def generate(self, question: str, papers: Sequence[PaperSummary]) -> tuple[str, List[str]]:
        ...


class DeepSearchEngine(Protocol):
    def search(self, *, query: str, files: Sequence[UploadedFileInfo], limit: int = 5) -> Sequence[PaperSummary]:
        ...


# ---------------------------------------------------------------------------
# Natural language interpreter
# ---------------------------------------------------------------------------


@dataclass
class ParsedIntent:
    action: str
    target_ids: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    years: Optional[int] = None
    limit: Optional[int] = None
    query: Optional[str] = None
    focus_aspect: Optional[str] = None
    language: str = "en"
    request_expansion: bool = False


class NaturalLanguageInterpreter:
    YEAR_RANGE_PATTERN = re.compile(r"(last|past)\s+(\d+)\s+year")
    SINCE_PATTERN = re.compile(r"since\s+(\d{4})")
    SINGLE_YEAR_PATTERN = re.compile(r"\b(20\d{2}|19\d{2})\b")
    INDEX_PATTERN = re.compile(r"paper\s*(\d+)\b", re.IGNORECASE)
    ID_PATTERN = re.compile(r"\b([A-Za-z]+?\d{1,4})\b")
    URL_PATTERN = re.compile(r"https?://[^\s,]+")
    ORDINAL_PATTERN = re.compile(
        r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b",
        re.IGNORECASE,
    )
    CH_ORDINAL_PATTERN = re.compile(r"第([一二三四五六七八九十]+)篇?")
    CH_NUM_MAP = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    ORDINAL_MAP = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
    }

    def parse(self, message: str, session: ConversationSession) -> ParsedIntent:
        lower = message.lower().strip()
        if not lower:
            return ParsedIntent(action="smalltalk")

        if any(term in lower for term in ["keyword", "expand", "refine", "关键词", "拓展"]):
            keywords = self._extract_keyword_candidates(message)
            return ParsedIntent(action="keyword_expand", keywords=keywords, request_expansion=True)

        if any(term in lower for term in ["overall summary", "global summary", "科学总结", "总体概括"]):
            return ParsedIntent(action="global_summary", target_ids=list(session.selected_ids))

        if any(term in lower for term in ["focus on", "针对", "关于", "方面"]):
            focus = self._extract_focus_aspect(message)
            targets = self._resolve_targets(message, session)
            return ParsedIntent(action="focused_summary", target_ids=targets or list(session.selected_ids), focus_aspect=focus or "the requested aspect")

        if any(term in lower for term in ["summary", "summarize", "概括", "总结"]):
            targets = self._resolve_targets(message, session)
            return ParsedIntent(action="quick_summary", target_ids=targets or list(session.selected_ids))

        years = self._extract_year_window(lower)
        if years is not None:
            return ParsedIntent(action="filter_year", years=years)

        if any(token in lower for token in ["only", "keep", "focus", "just these"]):
            targets = self._resolve_targets(message, session)
            if targets:
                return ParsedIntent(action="keep_specific", target_ids=targets)

        if any(token in lower for token in ["remove", "drop", "exclude"]):
            targets = self._resolve_targets(message, session)
            if targets:
                return ParsedIntent(action="remove_specific", target_ids=targets)

        if "list" in lower or ("show" in lower and "selection" in lower):
            return ParsedIntent(action="list_selection")

        if "deep search" in lower or "search files" in lower:
            limit = self._extract_limit(lower)
            return ParsedIntent(action="deep_search", limit=limit, query=message)

        keywords = self._extract_keyword_candidates(message)
        if keywords:
            return ParsedIntent(action="filter_keyword", keywords=keywords)

        return ParsedIntent(action="question", query=message)

    def _extract_year_window(self, text: str) -> Optional[int]:
        if "recent" in text or "latest" in text or "this year" in text:
            return 1
        match = self.YEAR_RANGE_PATTERN.search(text)
        if match:
            return max(1, int(match.group(2)))
        if "last year" in text or "past year" in text:
            return 1
        match_since = self.SINCE_PATTERN.search(text)
        if match_since:
            year = int(match_since.group(1))
            return max(1, self._current_year() - year + 1)
        if "year" in text:
            match_single = self.SINGLE_YEAR_PATTERN.search(text)
            if match_single:
                year = int(match_single.group(1))
                return max(1, self._current_year() - year + 1)
        return None

    def _current_year(self) -> int:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).year

    def _extract_limit(self, text: str) -> Optional[int]:
        match = re.search(r"(?:top|first|limit)\s+(\d+)", text)
        if match:
            return int(match.group(1))
        return None

    def _extract_keyword_candidates(self, text: str) -> List[str]:
        extracted = re.findall(r"(?:keyword|关键词|topic|focus on)\s+([a-zA-Z0-9\u4e00-\u9fa5\s\-]+)", text, flags=re.IGNORECASE)
        if extracted:
            return self._normalize_terms(extracted)
        raw_terms = re.findall(r'"([^"]+)"', text)
        if raw_terms:
            return self._normalize_terms(raw_terms)
        return []

    @staticmethod
    def _normalize_terms(segments: Iterable[str]) -> List[str]:
        terms: List[str] = []
        for segment in segments:
            parts = [part.strip() for part in re.split(r"[,/，；;]", segment) if part.strip()]
            for part in parts:
                if part and part.lower() not in (t.lower() for t in terms):
                    terms.append(part)
        return terms

    def _extract_focus_aspect(self, message: str) -> Optional[str]:
        match = re.search(r"focus on\s+([a-zA-Z0-9\s\-]+)", message, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        match_cn = re.search(r"针对(.+?)(?:的)?(总结|概括)", message)
        if match_cn:
            return match_cn.group(1).strip()
        return None

    def _resolve_targets(self, message: str, session: ConversationSession) -> List[str]:
        ids = set(self.ID_PATTERN.findall(message))
        url_matches = self.URL_PATTERN.findall(message)
        for url in url_matches:
            ids.add(url.strip().rstrip("."))

        index_matches = self.INDEX_PATTERN.findall(message)
        for index_str in index_matches:
            try:
                index = int(index_str) - 1
                if 0 <= index < len(session.selected_ids):
                    ids.add(session.selected_ids[index])
            except ValueError:
                continue

        for match in self.ORDINAL_PATTERN.findall(message):
            ordinal_index = self.ORDINAL_MAP.get(match.lower())
            if ordinal_index is not None and 0 < ordinal_index <= len(session.selected_ids):
                ids.add(session.selected_ids[ordinal_index - 1])

        ch_match = self.CH_ORDINAL_PATTERN.search(message)
        if ch_match:
            numeral = ch_match.group(1)
            total = 0
            for char in numeral:
                value = self.CH_NUM_MAP.get(char)
                if value is None:
                    total = 0
                    break
                total = total * 10 + value
            if total == 0 and numeral == "十":
                total = 10
            if 0 < total <= len(session.selected_ids):
                ids.add(session.selected_ids[total - 1])

        return list(ids)


# ---------------------------------------------------------------------------
# Fallback insight generator
# ---------------------------------------------------------------------------


class SimpleInsightGenerator:
    """Fallback insight generator that returns heuristic insights."""

    def generate(self, question: str, papers: Sequence[PaperSummary]) -> tuple[str, List[str]]:
        if not papers:
            return ("No papers are available for insight generation.", [])

        lines = []
        citations = []
        for paper in papers:
            snippet = paper.abstract[:300].strip()
            lines.append(f"{paper.title}: {snippet}")
            citations.append(paper.title)
        text = " ".join(lines)
        return (text, citations)


# ---------------------------------------------------------------------------
# Conversation agent orchestrator
# ---------------------------------------------------------------------------


class ConversationAgent:
    """Coordinates multi-turn conversations and tool execution."""

    def __init__(
        self,
        *,
        tool_registry: Optional[ToolRegistry] = None,
        interpreter: Optional[NaturalLanguageInterpreter] = None,
        insight_generator: Optional[InsightGenerator] = None,
        deep_search_engine: Optional[DeepSearchEngine] = None,
        search_manager: Optional[SearchListManager] = None,
    ) -> None:
        self._interpreter = interpreter or NaturalLanguageInterpreter()
        self._insight_generator = insight_generator or SimpleInsightGenerator()
        self._deep_search_engine = deep_search_engine
        self._tool_registry = tool_registry or self._build_default_registry()
        self._search_manager = search_manager or SearchListManager()
        self._sessions: Dict[str, ConversationSession] = {}
        self._memory: Dict[str, SessionMemory] = {}

    # ----------------------------- session management --------------------- #

    def ingest_papers(self, papers: Iterable[PaperSummary]) -> None:
        self._search_manager.register(papers)

    def start_session(self, session_id: str, initial_selection: Optional[Iterable[str]] = None) -> ConversationSession:
        selection = list(dict.fromkeys(initial_selection or []))
        session = ConversationSession(session_id=session_id, selected_ids=selection)
        self._sessions[session_id] = session
        self._memory[session_id] = SessionMemory(session=session)
        return session

    def get_session(self, session_id: str) -> ConversationSession:
        if session_id not in self._sessions:
            raise KeyError(f"Session '{session_id}' does not exist.")
        return self._sessions[session_id]

    def register_uploads(self, session_id: str, files: Sequence[UploadedFileInfo]) -> None:
        session = self.get_session(session_id)
        session.record_uploads(files)

    # ----------------------------- core handler --------------------------- #

    def handle_message(self, session_id: str, message: str) -> AgentReply:
        session = self.get_session(session_id)
        memory = self._memory[session_id]

        memory.add_user_message(message)
        parsed = self._interpreter.parse(message, session)
        intent_payload = {
            "target_ids": parsed.target_ids,
            "keywords": parsed.keywords,
            "years": parsed.years,
            "limit": parsed.limit,
            "query": parsed.query,
            "focus_aspect": parsed.focus_aspect,
            "language": parsed.language,
            "request_expansion": parsed.request_expansion,
        }
        intent = ConversationIntent(action=parsed.action, payload=intent_payload)
        memory.add_intent(intent)

        reply = self._dispatch_intent(session, memory, parsed)
        memory.add_assistant_message(reply.text)
        return reply

    # ----------------------------- action handlers ------------------------ #

    def _dispatch_intent(self, session: ConversationSession, memory: SessionMemory, parsed: ParsedIntent) -> AgentReply:
        if parsed.action == "keyword_expand":
            return self._handle_keyword_expansion(session, memory, parsed)
        if parsed.action == "quick_summary":
            return self._handle_quick_summary(session, memory, parsed)
        if parsed.action == "global_summary":
            return self._handle_global_summary(session, memory, parsed)
        if parsed.action == "focused_summary":
            return self._handle_focused_summary(session, memory, parsed)
        if parsed.action == "filter_year":
            return self._handle_filter_year(session, parsed.years or 1)
        if parsed.action == "filter_keyword":
            return self._handle_filter_keywords(session, parsed.keywords)
        if parsed.action == "keep_specific":
            return self._handle_keep_specific(session, parsed.target_ids)
        if parsed.action == "remove_specific":
            return self._handle_remove_specific(session, parsed.target_ids)
        if parsed.action == "list_selection":
            return self._handle_list(session)
        if parsed.action == "deep_search":
            return self._handle_deep_search(session, parsed)
        if parsed.action == "question":
            return self._handle_generic_question(session, parsed.query or "")

        return AgentReply(
            text="I am tracking your preferences. Please clarify if you want to refine keywords, filter papers, or request a summary.",
            selected_ids=list(session.selected_ids),
            citations=[],
        )

    def _handle_keyword_expansion(self, session: ConversationSession, memory: SessionMemory, parsed: ParsedIntent) -> AgentReply:
        keywords = parsed.keywords or session.filters.get("keywords", [])
        if not keywords:
            return AgentReply(
                text="请提供需要扩展的关键词。",
                selected_ids=list(session.selected_ids),
                citations=[],
            )

        payload = {
            "keywords": keywords,
            "domain": session.filters.get("domain") or "ml",
            "language": parsed.language,
        }
        result = self._run_tool(session, memory, "keyword_expansion", payload)
        if result.metadata.get("error"):
            return AgentReply(
                text=f"关键词扩展失败：{result.metadata.get('error')}",
                selected_ids=list(session.selected_ids),
                citations=[],
                metadata=result.metadata,
            )
        must_terms = result.metadata.get("must_terms", [])
        should_terms = result.metadata.get("should_terms", [])
        filters = result.metadata.get("filters", {})
        memory.upsert_filter("keywords", must_terms + should_terms)
        memory.upsert_filter("search_filters", filters)

        message_parts = ["已完成关键词扩展。"]
        if must_terms:
            message_parts.append(f"核心词：{', '.join(must_terms)}")
        if should_terms:
            message_parts.append(f"可选词：{', '.join(should_terms)}")
        if filters:
            formatted_filters = ", ".join(f"{k}={v}" for k, v in filters.items())
            message_parts.append(f"建议过滤：{formatted_filters}")

        return AgentReply(
            text="；".join(message_parts),
            selected_ids=list(session.selected_ids),
            citations=[],
            metadata=result.metadata,
        )

    def _handle_quick_summary(self, session: ConversationSession, memory: SessionMemory, parsed: ParsedIntent) -> AgentReply:
        target_ids = parsed.target_ids or list(session.selected_ids)
        papers = self._search_manager.bulk_get(target_ids)
        if not papers:
            return AgentReply(text="没有找到可用于概括的论文。", selected_ids=list(session.selected_ids), citations=[])

        payload = {
            "papers": papers,
            "user_goal": "Provide a concise summary of the selected papers.",
            "selected_ids": target_ids,
            "language": parsed.language,
        }
        result = self._run_tool(session, memory, "quick_summary", payload)
        if result.metadata.get("error"):
            return AgentReply(
                text=f"生成概括时出错：{result.metadata.get('error')}",
                selected_ids=list(session.selected_ids),
                citations=[],
                metadata=result.metadata,
            )
        memory.store_artifact("last_quick_summary", result.text)
        return AgentReply(
            text=result.text,
            selected_ids=list(session.selected_ids),
            citations=list(result.citations),
            metadata=result.metadata,
        )

    def _handle_global_summary(self, session: ConversationSession, memory: SessionMemory, parsed: ParsedIntent) -> AgentReply:
        papers = self._search_manager.bulk_get(session.selected_ids) or self._search_manager.list_catalogue()
        if not papers:
            return AgentReply(text="当前没有可用于生成全局总结的论文。", selected_ids=[], citations=[])

        payload = {
            "papers": papers,
            "user_goal": "Produce a scientific synthesis covering methods, findings, and gaps.",
            "language": parsed.language,
        }
        result = self._run_tool(session, memory, "global_summary", payload)
        if result.metadata.get("error"):
            return AgentReply(
                text=f"生成全局总结时出错：{result.metadata.get('error')}",
                selected_ids=list(session.selected_ids),
                citations=[],
                metadata=result.metadata,
            )
        memory.store_artifact("last_global_summary", result.text)
        return AgentReply(
            text=result.text,
            selected_ids=list(session.selected_ids),
            citations=list(result.citations),
            metadata=result.metadata,
        )

    def _handle_focused_summary(self, session: ConversationSession, memory: SessionMemory, parsed: ParsedIntent) -> AgentReply:
        target_ids = parsed.target_ids or list(session.selected_ids)
        papers = self._search_manager.bulk_get(target_ids)
        if not papers:
            return AgentReply(text="没有找到可用于专题总结的论文。", selected_ids=list(session.selected_ids), citations=[])

        payload = {
            "papers": papers,
            "user_goal": f"Synthesize findings with a focus on: {parsed.focus_aspect}",
            "focus_aspect": parsed.focus_aspect,
            "selected_ids": target_ids,
        }
        result = self._run_tool(session, memory, "focused_synthesis", payload)
        if result.metadata.get("error"):
            return AgentReply(
                text=f"专题总结失败：{result.metadata.get('error')}",
                selected_ids=list(session.selected_ids),
                citations=[],
                metadata=result.metadata,
            )
        artifact_key = f"focused_summary::{parsed.focus_aspect}"
        memory.store_artifact(artifact_key, result.text)
        return AgentReply(
            text=result.text,
            selected_ids=list(session.selected_ids),
            citations=list(result.citations),
            metadata=result.metadata,
        )

    def _handle_filter_year(self, session: ConversationSession, years: int) -> AgentReply:
        filtered = self._search_manager.filter_by_years(years)
        session.selected_ids = [paper.paper_id for paper in filtered]
        summary = self._summarize_selection(filtered, prefix=f"保留了近 {years} 年的论文")
        return AgentReply(text=summary, selected_ids=list(session.selected_ids), citations=[paper.title for paper in filtered])

    def _handle_filter_keywords(self, session: ConversationSession, keywords: Sequence[str]) -> AgentReply:
        filtered = self._search_manager.filter_by_keywords(keywords)
        session.selected_ids = [paper.paper_id for paper in filtered]
        summary = self._summarize_selection(filtered, prefix=f"保留包含关键词 {', '.join(keywords)} 的论文")
        return AgentReply(text=summary, selected_ids=list(session.selected_ids), citations=[paper.title for paper in filtered])

    def _handle_keep_specific(self, session: ConversationSession, target_ids: Sequence[str]) -> AgentReply:
        papers = self._search_manager.select(session, target_ids)
        if not papers:
            return AgentReply(text="没有找到匹配的论文。", selected_ids=list(session.selected_ids), citations=[])
        summary = self._summarize_selection(papers, prefix="更新后的论文列表")
        return AgentReply(text=summary, selected_ids=list(session.selected_ids), citations=[paper.title for paper in papers])

    def _handle_remove_specific(self, session: ConversationSession, target_ids: Sequence[str]) -> AgentReply:
        papers = self._search_manager.remove_from_selection(session, target_ids)
        summary = self._summarize_selection(papers, prefix="已移除指定论文")
        return AgentReply(text=summary, selected_ids=list(session.selected_ids), citations=[paper.title for paper in papers])

    def _handle_list(self, session: ConversationSession) -> AgentReply:
        papers = self._search_manager.bulk_get(session.selected_ids)
        summary = self._summarize_selection(papers, prefix="当前选中的论文")
        return AgentReply(text=summary, selected_ids=list(session.selected_ids), citations=[paper.title for paper in papers])

    def _handle_deep_search(self, session: ConversationSession, parsed: ParsedIntent) -> AgentReply:
        if not self._deep_search_engine:
            return AgentReply(text="Deep search is not configured.", selected_ids=list(session.selected_ids), citations=[])

        results = self._deep_search_engine.search(
            query=parsed.query or "",
            files=session.uploaded_files,
            limit=parsed.limit or 5,
        )
        self._search_manager.register(results)
        session.selected_ids = [paper.paper_id for paper in results]
        summary = self._summarize_selection(results, prefix="已将深度搜索结果加入列表")
        return AgentReply(text=summary, selected_ids=list(session.selected_ids), citations=[paper.title for paper in results])

    def _handle_generic_question(self, session: ConversationSession, question: str) -> AgentReply:
        papers = self._search_manager.bulk_get(session.selected_ids) or self._search_manager.list_catalogue()
        text, citations = self._insight_generator.generate(question, papers)
        return AgentReply(text=text, selected_ids=list(session.selected_ids), citations=citations)

    # ----------------------------- helpers -------------------------------- #

    def _run_tool(self, session: ConversationSession, memory: SessionMemory, tool_name: str, payload: Dict[str, object]) -> ToolResult:
        context = ToolContext(
            session_id=session.session_id,
            memory_snapshot=memory.snapshot(),
            extras={"selected_ids": list(session.selected_ids)},
        )
        try:
            return self._tool_registry.execute(tool_name, context, payload)
        except ToolExecutionError as exc:
            return ToolResult(
                text=str(exc),
                citations=[],
                selected_ids=list(session.selected_ids),
                metadata={"error": exc.code, "details": exc.details},
            )

    def _summarize_selection(self, papers: Sequence[PaperSummary], prefix: str) -> str:
        if not papers:
            return f"{prefix}。当前选中列表为空。"
        lines = [prefix + ":"]
        for index, paper in enumerate(papers, start=1):
            year_part = f" ({paper.year})" if paper.year else ""
            lines.append(f"{index}. {paper.title}{year_part}")
        return "\n".join(lines)

    def _build_default_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(KeywordExpansionTool())
        registry.register(QuickSummaryTool())
        registry.register(GlobalSummaryTool())
        registry.register(FocusedSynthesisTool())
        return registry

    def available_tools(self) -> List[str]:
        return list(self._tool_registry.available_tools().keys())
