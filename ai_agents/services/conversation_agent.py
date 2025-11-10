from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Protocol, Sequence, Any

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
from .tooling import AgentTool, ToolContext, ToolExecutionError, ToolRegistry, ToolResult


# ---------------------------------------------------------------------------
# Protocols for pluggable components
# ---------------------------------------------------------------------------


class InsightGenerator(Protocol):
    def generate(self, question: str, papers: Sequence[PaperSummary]) -> tuple[str, List[str]]:
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
    WORD_LIMIT_PATTERN = re.compile(
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:more|additional)\b",
        re.IGNORECASE,
    )
    NUMBER_WORDS = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
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

        if any(term in lower for term in ["keyword", "expand", "refine"]):
            keywords = self._extract_keyword_candidates(message)
            return ParsedIntent(action="keyword_expand", keywords=keywords, request_expansion=True)

        if any(term in lower for term in ["overall summary", "global summary"]):
            return ParsedIntent(action="global_summary", target_ids=list(session.selected_ids))

        if any(term in lower for term in ["focus on", "focus around", "regarding"]):
            focus = self._extract_focus_aspect(message)
            targets = self._resolve_targets(message, session)
            return ParsedIntent(action="focused_summary", target_ids=targets or list(session.selected_ids), focus_aspect=focus or "the requested aspect")

        if any(term in lower for term in ["cite", "citation", "references"]):
            targets = self._resolve_targets(message, session)
            return ParsedIntent(action="cite", target_ids=targets or list(session.selected_ids))

        if any(term in lower for term in ["summary", "summarize"]):
            targets = self._resolve_targets(message, session)
            return ParsedIntent(action="quick_summary", target_ids=targets or list(session.selected_ids))

        years = self._extract_year_window(lower)
        if years is not None:
            return ParsedIntent(action="filter_year", years=years)

        if any(term in lower for term in ["add", "include", "attach"]):
            targets = self._resolve_targets(message, session)
            if targets:
                return ParsedIntent(action="add_specific", target_ids=targets)

        if any(token in lower for token in ["only", "keep", "focus", "just these"]):
            targets = self._resolve_targets(message, session)
            if targets:
                return ParsedIntent(action="keep_specific", target_ids=targets)

        if any(token in lower for token in ["remove", "drop", "exclude"]):
            targets = self._resolve_targets(message, session)
            if targets:
                return ParsedIntent(action="remove_specific", target_ids=targets)

        if self._is_search_extension_request(lower):
            keywords = self._extract_search_terms(message)
            if not keywords:
                keywords = session.filters.get("keywords", [])
            limit = self._extract_limit(lower)
            return ParsedIntent(action="extend_search", keywords=keywords, limit=limit)

        if "list" in lower or ("show" in lower and "selection" in lower):
            return ParsedIntent(action="list_selection")

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
        match_more = re.search(r"\b(\d+)\s+(?:more|additional)\b", text)
        if match_more:
            return int(match_more.group(1))
        match_word = self.WORD_LIMIT_PATTERN.search(text)
        if match_word:
            return self.NUMBER_WORDS.get(match_word.group(1).lower())
        return None

    def _extract_keyword_candidates(self, text: str) -> List[str]:
        extracted = re.findall(r"(?:keyword|topic|focus on)\s+([a-zA-Z0-9\s\-]+)", text, flags=re.IGNORECASE)
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
        return None

    def _extract_search_terms(self, message: str) -> List[str]:
        # Try explicit keyword cues first
        keywords = self._extract_keyword_candidates(message)
        if keywords:
            return keywords

        # Look for "about/on/regarding" phrases
        about_match = re.search(
            r"(?:about|on|regarding|around)\s+([a-zA-Z0-9,\-\s]+)",
            message,
            flags=re.IGNORECASE,
        )
        if about_match:
            fragment = about_match.group(1)
            fragment = re.split(r"[.?!]", fragment)[0]
            return self._normalize_terms([fragment])
        return []

    def _is_search_extension_request(self, text: str) -> bool:
        if not any(token in text for token in ["search", "find", "look for", "discover"]):
            return False
        return any(term in text for term in ["more", "additional", "another", "extra"])

    def _resolve_targets(self, message: str, session: ConversationSession) -> List[str]:
        def _normalize(raw: str) -> str:
            value = raw.strip().rstrip(".")
            if "openalex.org" in value:
                value = value.replace("/works/", "/")
            return value

        ids = set(self.ID_PATTERN.findall(message))
        url_matches = self.URL_PATTERN.findall(message)
        for url in url_matches:
            ids.add(_normalize(url))

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
        search_manager: Optional[SearchListManager] = None,
    ) -> None:
        self._interpreter = interpreter or NaturalLanguageInterpreter()
        self._insight_generator = insight_generator or SimpleInsightGenerator()
        self._tool_registry = tool_registry or self._build_default_registry()
        self._search_manager = search_manager or SearchListManager()
        self._sessions: Dict[str, ConversationSession] = {}
        self._memory: Dict[str, SessionMemory] = {}
        self._session_context: Dict[str, Dict[str, object]] = {}
        self._system_prompt = (
            "You are an academic research assistant. Manage search results, help refine keywords, "
            "add or remove papers, provide citations, summaries, comparisons, and insights. "
            "Always ground responses in the provided paper list and clearly describe any actions taken."
        )

    # ----------------------------- session management --------------------- #

    def ingest_papers(self, papers: Iterable[PaperSummary]) -> None:
        self._search_manager.register(papers)

    def start_session(
        self,
        session_id: str,
        initial_selection: Optional[Iterable[str]] = None,
        metadata: Optional[Mapping[str, object]] = None,
    ) -> ConversationSession:
        selection = list(dict.fromkeys(initial_selection or []))
        session = ConversationSession(session_id=session_id, selected_ids=selection)
        self._sessions[session_id] = session
        self._memory[session_id] = SessionMemory(session=session)
        if metadata:
            self._session_context[session_id] = dict(metadata)
        return session

    def get_session(self, session_id: str) -> ConversationSession:
        if session_id not in self._sessions:
            raise KeyError(f"Session '{session_id}' does not exist.")
        return self._sessions[session_id]

    def register_uploads(self, session_id: str, files: Sequence[UploadedFileInfo]) -> None:
        session = self.get_session(session_id)
        session.record_uploads(files)

    def set_session_context(self, session_id: str, **metadata: object) -> None:
        context = self._session_context.setdefault(session_id, {})
        context.update(metadata)

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
        memory.append_summary(f"User: {message.strip()} | Assistant: {reply.text.strip()}")
        return reply

    def generate_summary(
        self,
        session_id: str,
        *,
        summary_type: str = "comprehensive",
        focus_aspect: Optional[str] = None,
        language: str = "en",
    ) -> AgentReply:
        session = self.get_session(session_id)
        memory = self._memory[session_id]

        summary_key = summary_type.lower().strip() if summary_type else "comprehensive"
        if summary_key in {"quick", "short"}:
            parsed = ParsedIntent(
                action="quick_summary",
                target_ids=list(session.selected_ids),
                language=language,
            )
        elif summary_key in {"focused", "focus"}:
            if not focus_aspect:
                raise ValueError("focus_aspect is required for focused summaries")
            parsed = ParsedIntent(
                action="focused_summary",
                target_ids=list(session.selected_ids),
                focus_aspect=focus_aspect,
                language=language,
            )
        else:
            parsed = ParsedIntent(
                action="global_summary",
                target_ids=list(session.selected_ids),
                language=language,
            )

        reply = self._dispatch_intent(session, memory, parsed)
        memory.add_assistant_message(reply.text)
        memory.append_summary(f"Assistant summary ({summary_key}): {reply.text.strip()}")
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
        if parsed.action == "cite":
            return self._handle_citations(session, parsed.target_ids)
        if parsed.action == "filter_year":
            return self._handle_filter_year(session, parsed.years or 1)
        if parsed.action == "filter_keyword":
            return self._handle_filter_keywords(session, parsed.keywords)
        if parsed.action == "keep_specific":
            return self._handle_keep_specific(session, parsed.target_ids)
        if parsed.action == "remove_specific":
            return self._handle_remove_specific(session, parsed.target_ids)
        if parsed.action == "add_specific":
            return self._handle_add_specific(session, parsed.target_ids)
        if parsed.action == "extend_search":
            return self._handle_search_extension(session, memory, parsed)
        if parsed.action == "list_selection":
            return self._handle_list(session)
        if parsed.action == "question":
            return self._handle_generic_question(session, memory, parsed.query or "")

        return AgentReply(
            text="I am tracking your preferences. Please clarify if you want to refine keywords, filter papers, or request a summary.",
            selected_ids=list(session.selected_ids),
            citations=[],
        )

    def _handle_keyword_expansion(self, session: ConversationSession, memory: SessionMemory, parsed: ParsedIntent) -> AgentReply:
        keywords = parsed.keywords or session.filters.get("keywords", [])
        if not keywords:
            return AgentReply(
                text="Please provide the keywords that need expansion.",
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
                text=f"Keyword expansion failed: {result.metadata.get('error')}",
                selected_ids=list(session.selected_ids),
                citations=[],
                metadata=result.metadata,
            )
        must_terms = result.metadata.get("must_terms", [])
        should_terms = result.metadata.get("should_terms", [])
        filters = result.metadata.get("filters", {})
        memory.upsert_filter("keywords", must_terms + should_terms)
        memory.upsert_filter("search_filters", filters)

        message_parts = ["Keyword expansion completed."]
        if must_terms:
            message_parts.append(f"Core terms: {', '.join(must_terms)}")
        if should_terms:
            message_parts.append(f"Optional terms: {', '.join(should_terms)}")
        if filters:
            formatted_filters = ", ".join(f"{k}={v}" for k, v in filters.items())
            message_parts.append(f"Suggested filters: {formatted_filters}")

        return AgentReply(
            text="; ".join(message_parts),
            selected_ids=list(session.selected_ids),
            citations=[],
            metadata=result.metadata,
        )

    def _handle_quick_summary(self, session: ConversationSession, memory: SessionMemory, parsed: ParsedIntent) -> AgentReply:
        target_ids = parsed.target_ids or list(session.selected_ids)
        papers = self._search_manager.bulk_get(target_ids)
        if not papers:
            return AgentReply(text="No papers available for summarization.", selected_ids=list(session.selected_ids), citations=[])

        payload = {
            "papers": papers,
            "user_goal": "Provide a concise summary of the selected papers.",
            "selected_ids": target_ids,
            "language": parsed.language,
        }
        result = self._run_tool(session, memory, "quick_summary", payload)
        if result.metadata.get("error"):
            return AgentReply(
                text=f"Failed to generate summary: {result.metadata.get('error')}",
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
            return AgentReply(text="No papers are available to produce a global synthesis.", selected_ids=[], citations=[])

        payload = {
            "papers": papers,
            "user_goal": "Produce a scientific synthesis covering methods, findings, and gaps.",
            "language": parsed.language,
            "mode": "comprehensive",
        }
        result = self._run_tool(session, memory, "global_summary", payload)
        if result.metadata.get("error"):
            return AgentReply(
                text=f"Failed to produce global summary: {result.metadata.get('error')}",
                selected_ids=list(session.selected_ids),
                citations=[],
                metadata=result.metadata,
            )
        memory.store_artifact("last_global_summary", result.text)
        metadata = dict(result.metadata)
        metadata.setdefault("summary_type", "comprehensive")
        return AgentReply(
            text=result.text,
            selected_ids=list(session.selected_ids),
            citations=list(result.citations),
            metadata=metadata,
        )

    def _handle_focused_summary(self, session: ConversationSession, memory: SessionMemory, parsed: ParsedIntent) -> AgentReply:
        target_ids = parsed.target_ids or list(session.selected_ids)
        papers = self._search_manager.bulk_get(target_ids)
        if not papers:
            return AgentReply(text="No papers are available for focused synthesis.", selected_ids=list(session.selected_ids), citations=[])

        payload = {
            "papers": papers,
            "user_goal": f"Synthesize findings with a focus on: {parsed.focus_aspect}",
            "focus_aspect": parsed.focus_aspect,
            "selected_ids": target_ids,
        }
        result = self._run_tool(session, memory, "focused_synthesis", payload)
        if result.metadata.get("error"):
            return AgentReply(
                text=f"Focused synthesis failed: {result.metadata.get('error')}",
                selected_ids=list(session.selected_ids),
                citations=[],
                metadata=result.metadata,
            )
        artifact_key = f"focused_summary::{parsed.focus_aspect}"
        memory.store_artifact(artifact_key, result.text)
        metadata = dict(result.metadata)
        metadata.setdefault("summary_type", "focused")
        metadata.setdefault("focus_aspect", parsed.focus_aspect)
        return AgentReply(
            text=result.text,
            selected_ids=list(session.selected_ids),
            citations=list(result.citations),
            metadata=metadata,
        )

    def _handle_filter_year(self, session: ConversationSession, years: int) -> AgentReply:
        filtered = self._search_manager.filter_by_years(years)
        session.selected_ids = [paper.paper_id for paper in filtered]
        summary = self._summarize_selection(filtered, prefix=f"Kept papers from the last {years} year(s)")
        return AgentReply(text=summary, selected_ids=list(session.selected_ids), citations=[paper.title for paper in filtered])

    def _handle_filter_keywords(self, session: ConversationSession, keywords: Sequence[str]) -> AgentReply:
        filtered = self._search_manager.filter_by_keywords(keywords)
        session.selected_ids = [paper.paper_id for paper in filtered]
        summary = self._summarize_selection(filtered, prefix=f"Kept papers matching keywords: {', '.join(keywords)}")
        return AgentReply(text=summary, selected_ids=list(session.selected_ids), citations=[paper.title for paper in filtered])

    def _handle_keep_specific(self, session: ConversationSession, target_ids: Sequence[str]) -> AgentReply:
        papers = self._search_manager.select(session, target_ids)
        if not papers:
            return AgentReply(text="No matching papers were found for your request.", selected_ids=list(session.selected_ids), citations=[])
        summary = self._summarize_selection(papers, prefix="Updated selection")
        return AgentReply(text=summary, selected_ids=list(session.selected_ids), citations=[paper.title for paper in papers])

    def _handle_remove_specific(self, session: ConversationSession, target_ids: Sequence[str]) -> AgentReply:
        papers = self._search_manager.remove_from_selection(session, target_ids)
        summary = self._summarize_selection(papers, prefix="Removed requested papers")
        return AgentReply(text=summary, selected_ids=list(session.selected_ids), citations=[paper.title for paper in papers])

    def _handle_add_specific(self, session: ConversationSession, target_ids: Sequence[str]) -> AgentReply:
        if not target_ids:
            return AgentReply(text="Please specify which papers to add.", selected_ids=list(session.selected_ids), citations=[])
        papers = self._search_manager.add_to_selection(session, target_ids)
        if not papers:
            return AgentReply(text="No papers were added because none were found.", selected_ids=list(session.selected_ids), citations=[])
        summary = self._summarize_selection(papers, prefix="Added the requested papers")
        return AgentReply(text=summary, selected_ids=list(session.selected_ids), citations=[paper.title for paper in papers])

    def _handle_search_extension(self, session: ConversationSession, memory: SessionMemory, parsed: ParsedIntent) -> AgentReply:
        keywords = parsed.keywords or session.filters.get("keywords", [])
        if not keywords:
            return AgentReply(
                text="Please specify the keywords that should be used for the new search.",
                selected_ids=list(session.selected_ids),
                citations=[],
            )

        limit = parsed.limit or 3
        session_meta = self._session_context.get(session.session_id, {})
        history_id = session_meta.get("history_id")
        if history_id is None:
            return AgentReply(
                text="I cannot run a new search because this conversation is not linked to a stored history.",
                selected_ids=list(session.selected_ids),
                citations=[],
            )

        existing_ids = [paper.paper_id for paper in self._search_manager.list_catalogue()]
        payload = {
            "keywords": keywords,
            "limit": limit,
            "history_id": history_id,
            "existing_ids": existing_ids,
            "selected_ids": list(session.selected_ids),
            "system_prompt": self._system_prompt,
            "conversation_summary": memory.conversation_summary,
        }
        if "search_extension" not in self.available_tools():
            return AgentReply(
                text="Search extension is not available in the current configuration.",
                selected_ids=list(session.selected_ids),
                citations=[],
            )
        result = self._run_tool(session, memory, "search_extension", payload)
        if result.metadata.get("error"):
            return AgentReply(
                text=f"Search extension failed: {result.metadata.get('error')}",
                selected_ids=list(session.selected_ids),
                citations=[],
                metadata=result.metadata,
            )

        raw_items = result.metadata.get("papers") or []
        new_summaries: List[PaperSummary] = []
        for item in raw_items:
            paper = self._coerce_external_paper(item)
            if paper:
                new_summaries.append(paper)

        added_ids = [paper.paper_id for paper in new_summaries]
        if new_summaries:
            self._search_manager.register(new_summaries)
            self._search_manager.add_to_selection(session, added_ids)
            memory.upsert_filter("keywords", keywords)
            message_text = result.text or f"Added {len(new_summaries)} new paper(s) to the selection."
        else:
            message_text = result.text or "No additional papers were found for that request."

        metadata = dict(result.metadata)
        metadata.setdefault("added_ids", added_ids)
        return AgentReply(
            text=message_text,
            selected_ids=list(session.selected_ids),
            citations=[],
            metadata=metadata,
        )

    def _handle_list(self, session: ConversationSession) -> AgentReply:
        papers = self._search_manager.bulk_get(session.selected_ids)
        summary = self._summarize_selection(papers, prefix="Current selection")
        return AgentReply(text=summary, selected_ids=list(session.selected_ids), citations=[paper.title for paper in papers])

    def _handle_citations(self, session: ConversationSession, target_ids: Sequence[str]) -> AgentReply:
        ids = list(target_ids or session.selected_ids)
        papers = self._search_manager.bulk_get(ids)
        if not papers:
            return AgentReply(text="There are no citations available at the moment.", selected_ids=list(session.selected_ids), citations=[])

        lines = ["References:"]
        citations: List[str] = []
        for index, paper in enumerate(papers, start=1):
            authors = ", ".join(paper.authors)
            year = paper.year or "n.d."
            citation = f"{authors} ({year}). {paper.title}."
            url_part = f" {paper.url}" if paper.url else ""
            lines.append(f"{index}. {citation}{url_part}")
            citations.append(paper.title)
        return AgentReply(text="\n".join(lines), selected_ids=list(session.selected_ids), citations=citations)

    def _handle_generic_question(self, session: ConversationSession, memory: SessionMemory, question: str) -> AgentReply:
        papers = self._search_manager.bulk_get(session.selected_ids) or self._search_manager.list_catalogue()
        if memory.conversation_summary:
            augmented_question = f"{question}\n\nConversation summary so far:\n{memory.conversation_summary}"
        else:
            augmented_question = question
        text, citations = self._insight_generator.generate(augmented_question, papers)
        return AgentReply(text=text, selected_ids=list(session.selected_ids), citations=citations)

    # ----------------------------- helpers -------------------------------- #

    def _run_tool(self, session: ConversationSession, memory: SessionMemory, tool_name: str, payload: Dict[str, object]) -> ToolResult:
        extras: Dict[str, object] = {"selected_ids": list(session.selected_ids)}
        session_meta = self._session_context.get(session.session_id)
        if session_meta:
            extras.update(session_meta)
        context = ToolContext(
            session_id=session.session_id,
            memory_snapshot=memory.snapshot(),
            extras=extras,
        )
        payload.setdefault("system_prompt", self._system_prompt)
        payload.setdefault("conversation_summary", memory.conversation_summary)
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
            return f"{prefix}. The selection is currently empty."
        lines = [prefix + ":"]
        for index, paper in enumerate(papers, start=1):
            year_part = f" ({paper.year})" if paper.year else ""
            lines.append(f"{index}. {paper.title}{year_part}")
        return "\n".join(lines)

    def _coerce_external_paper(self, item: Mapping[str, Any]) -> Optional[PaperSummary]:
        paper_id = str(item.get("id") or item.get("paper_id") or "").strip()
        if not paper_id:
            return None
        title = str(item.get("title") or item.get("display_name") or "").strip()
        abstract = str(item.get("summary") or item.get("abstract") or item.get("abstract_text") or "")
        authors_raw = item.get("authors") or item.get("author_names") or []
        if isinstance(authors_raw, str):
            authors = tuple(part.strip() for part in authors_raw.split(",") if part.strip())
        else:
            authors = tuple(str(author).strip() for author in authors_raw if author)
        year = item.get("publication_year")
        try:
            year_val = int(year) if year is not None else None
        except (TypeError, ValueError):
            year_val = None
        url = str(item.get("link") or item.get("url") or paper_id)
        return PaperSummary(
            paper_id=paper_id,
            title=title,
            abstract=abstract,
            authors=authors,
            year=year_val,
            url=url,
        )

    def _build_default_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(KeywordExpansionTool())
        registry.register(QuickSummaryTool())
        registry.register(GlobalSummaryTool())
        registry.register(FocusedSynthesisTool())
        return registry

    def available_tools(self) -> List[str]:
        return list(self._tool_registry.available_tools().keys())

    def register_tool(self, tool: AgentTool) -> None:
        self._tool_registry.register(tool)
