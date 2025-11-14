from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Mapping

from ai_agents.services.conversation_agent import ConversationAgent
from ai_agents.services.tooling import AgentTool
from ai_agents.services.models import AgentReply, ConversationSession, PaperSummary, UploadedFileInfo
from server.data_access.paper_repository import PaperRepository
from server.data_access.search_history_repository import SearchHistoryRepository


class AIConversationService:
    """
    Thin adaptor that exposes the AI-layer ConversationAgent to the server layer.
    """

    def __init__(
        self,
        agent: Optional[ConversationAgent] = None,
        paper_repository: Optional[PaperRepository] = None,
        history_repository: Optional[SearchHistoryRepository] = None,
    ) -> None:
        self._agent = agent or ConversationAgent()
        self._paper_repository = paper_repository
        self._history_repository = history_repository
        self._session_history: Dict[str, int] = {}

    def ingest_papers(self, papers: Iterable[PaperSummary]) -> None:
        self._agent.ingest_papers(papers)

    def start_session(
        self,
        session_id: str,
        initial_selection: Optional[Iterable[str]] = None,
        metadata: Optional[Mapping[str, object]] = None,
    ) -> ConversationSession:
        session = self._agent.start_session(session_id, initial_selection, metadata=metadata)
        if metadata and "history_id" in metadata:
            try:
                self._session_history[session_id] = int(metadata["history_id"])  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
        return session

    def register_uploads(self, session_id: str, files: Sequence[UploadedFileInfo]) -> None:
        self._agent.register_uploads(session_id, files)

    def handle_message(self, session_id: str, message: str, *, history_id: Optional[int] = None) -> AgentReply:
        if history_id is not None:
            self._session_history[session_id] = history_id
            self._agent.set_session_context(session_id, history_id=history_id)
        elif session_id in self._session_history:
            self._agent.set_session_context(session_id, history_id=self._session_history[session_id])
        return self._agent.handle_message(session_id, message)

    def available_tools(self) -> List[str]:
        return self._agent.available_tools()

    def register_tool(self, tool: AgentTool) -> None:
        self._agent.register_tool(tool)

    def load_history_into_session(self, history_id: int, session_id: Optional[str] = None) -> Optional[ConversationSession]:
        if not self._history_repository:
            raise RuntimeError("History repository not configured for AIConversationService")

        record = self._history_repository.get_history_with_papers(history_id)
        if not record:
            return None

        paper_summaries: List[PaperSummary] = []
        selected_ids: List[str] = []
        for item in record.get("papers", []):
            paper_id = item.get("paper_id")
            if not paper_id:
                continue
            metadata_payload = item.get("fulltext_metadata") or {}
            chunks = item.get("chunks") or []
            if chunks:
                metadata_payload = dict(metadata_payload)
                metadata_payload["chunks"] = chunks
            paper_summaries.append(
                PaperSummary(
                    paper_id=paper_id,
                    title=item.get("title") or "",
                    abstract=item.get("abstract") or "",
                    authors=tuple(item.get("authors") or []),
                    year=item.get("publication_year"),
                    url=item.get("url"),
                    full_text=item.get("full_text") or "",
                    sections=item.get("sections") or [],
                    tables=item.get("tables") or [],
                    metadata=metadata_payload,
                )
            )
            if item.get("selected"):
                selected_ids.append(paper_id)

        if paper_summaries:
            self._agent.ingest_papers(paper_summaries)

        resolved_session_id = session_id or record.get("session_id") or f"history-{history_id}"
        self._agent.set_session_context(resolved_session_id, history_id=history_id)
        self._session_history[resolved_session_id] = history_id
        return self._agent.start_session(resolved_session_id, initial_selection=selected_ids, metadata={"history_id": history_id})

    def persist_session_selection(self, history_id: int, session_id: str) -> None:
        if not self._history_repository:
            raise RuntimeError("History repository not configured for AIConversationService")
        try:
            session = self._agent.get_session(session_id)
        except KeyError:
            session = self.ensure_session(history_id, session_id)
        self._history_repository.update_selection(history_id, session.selected_ids)

    def has_session(self, session_id: str) -> bool:
        try:
            self._agent.get_session(session_id)
            return True
        except KeyError:
            return False

    def ensure_session(self, history_id: int, session_id: str) -> ConversationSession:
        if not self.has_session(session_id):
            session = self.load_history_into_session(history_id, session_id=session_id)
            if not session:
                raise KeyError(f"Unable to load session '{session_id}'")
            return session
        self._session_history.setdefault(session_id, history_id)
        self._agent.set_session_context(session_id, history_id=self._session_history[session_id])
        return self._agent.get_session(session_id)

    def generate_summary(
        self,
        session_id: str,
        *,
        history_id: Optional[int] = None,
        summary_type: str = "comprehensive",
        focus_aspect: Optional[str] = None,
        language: str = "en",
    ) -> AgentReply:
        if history_id is None:
            history_id = self._session_history.get(session_id)
        if history_id is None:
            raise ValueError(f"history_id is required for session '{session_id}'")

        session = self.ensure_session(history_id, session_id)
        self._session_history[session_id] = history_id
        self._agent.set_session_context(session_id, history_id=history_id)

        reply = self._agent.generate_summary(
            session.session_id,
            summary_type=summary_type,
            focus_aspect=focus_aspect,
            language=language,
        )
        if self._history_repository:
            self._history_repository.update_selection(history_id, session.selected_ids)
        return reply
