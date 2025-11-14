"""
Shared data models for the AI service layer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class PaperSummary:
    """
    Lightweight representation of a paper/result item that can be surfaced in conversations.
    """

    paper_id: str
    title: str
    abstract: str
    authors: Sequence[str] = field(default_factory=list)
    year: Optional[int] = None
    url: Optional[str] = None
    full_text: str = ""
    sections: Sequence[Dict[str, Any]] = field(default_factory=list)
    tables: Sequence[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def keywords(self) -> List[str]:
        """Extract a simple keyword list from the abstract for quick matching."""
        source = self.full_text or self.abstract
        tokens = re.findall(r"[a-zA-Z0-9\-]+", source.lower())
        return list(dict.fromkeys(tokens))


@dataclass
class UploadedFileInfo:
    file_id: str
    name: str
    summary: str
    keywords: Sequence[str] = field(default_factory=list)


@dataclass
class ConversationMessage:
    role: str
    content: str


@dataclass
class ConversationIntent:
    """Captured interpretation of a user turn."""

    action: str
    payload: Dict[str, object] = field(default_factory=dict)


@dataclass
class SessionMemorySnapshot:
    """View of derived session state for orchestration/telemetry."""

    condensed_history: List[ConversationMessage]
    last_intent: Optional[ConversationIntent]
    active_filters: Dict[str, object] = field(default_factory=dict)
    generated_artifacts: Dict[str, str] = field(default_factory=dict)


@dataclass
class ConversationSession:
    session_id: str
    selected_ids: List[str] = field(default_factory=list)
    history: List[ConversationMessage] = field(default_factory=list)
    uploaded_files: List[UploadedFileInfo] = field(default_factory=list)
    intents: List[ConversationIntent] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)
    filters: Dict[str, object] = field(default_factory=dict)

    def record_message(self, role: str, content: str) -> None:
        self.history.append(ConversationMessage(role=role, content=content))

    def record_intent(self, intent: ConversationIntent) -> None:
        self.intents.append(intent)

    def record_uploads(self, files: Sequence[UploadedFileInfo]) -> None:
        existing = {f.file_id for f in self.uploaded_files}
        for file_info in files:
            if file_info.file_id not in existing:
                self.uploaded_files.append(file_info)
                existing.add(file_info.file_id)

    def snapshot(self, max_history: int = 10) -> SessionMemorySnapshot:
        condensed = self.history[-max_history:]
        last_intent = self.intents[-1] if self.intents else None
        return SessionMemorySnapshot(
            condensed_history=condensed,
            last_intent=last_intent,
            active_filters=dict(self.filters),
            generated_artifacts=dict(self.artifacts),
        )


@dataclass
class AgentReply:
    text: str
    selected_ids: List[str]
    citations: List[str]
    metadata: Dict[str, object] = field(default_factory=dict)
