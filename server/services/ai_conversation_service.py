from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from ai_agents.services.conversation_agent import ConversationAgent
from ai_agents.services.models import AgentReply, ConversationSession, PaperSummary, UploadedFileInfo


class AIConversationService:
    """
    Thin adaptor that exposes the AI-layer ConversationAgent to the server layer.
    """

    def __init__(self, agent: Optional[ConversationAgent] = None) -> None:
        self._agent = agent or ConversationAgent()

    def ingest_papers(self, papers: Iterable[PaperSummary]) -> None:
        self._agent.ingest_papers(papers)

    def start_session(self, session_id: str, initial_selection: Optional[Iterable[str]] = None) -> ConversationSession:
        return self._agent.start_session(session_id, initial_selection)

    def register_uploads(self, session_id: str, files: Sequence[UploadedFileInfo]) -> None:
        self._agent.register_uploads(session_id, files)

    def handle_message(self, session_id: str, message: str) -> AgentReply:
        return self._agent.handle_message(session_id, message)

    def available_tools(self) -> List[str]:
        return self._agent.available_tools()
