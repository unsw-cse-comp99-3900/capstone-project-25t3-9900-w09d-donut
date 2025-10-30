"""
Session memory helper for the conversation orchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from .models import ConversationIntent, ConversationMessage, ConversationSession, SessionMemorySnapshot


@dataclass
class SessionMemory:
    """
    Keeps light-weight derived state about a conversation session to reduce duplication
    across tools and improve orchestration decisions.
    """

    session: ConversationSession
    max_history: int = 25
    _condensed_history: List[ConversationMessage] = field(default_factory=list)

    def add_user_message(self, content: str) -> None:
        self.session.record_message("user", content)
        self._refresh_history()

    def add_assistant_message(self, content: str) -> None:
        self.session.record_message("assistant", content)
        self._refresh_history()

    def add_intent(self, intent: ConversationIntent) -> None:
        self.session.record_intent(intent)

    def upsert_filter(self, key: str, value: object) -> None:
        self.session.filters[key] = value

    def remove_filter(self, key: str) -> None:
        self.session.filters.pop(key, None)

    def store_artifact(self, name: str, value: str) -> None:
        self.session.artifacts[name] = value

    def get_artifact(self, name: str) -> Optional[str]:
        return self.session.artifacts.get(name)

    def snapshot(self) -> SessionMemorySnapshot:
        return self.session.snapshot(max_history=self.max_history)

    def _refresh_history(self) -> None:
        if len(self.session.history) <= self.max_history:
            self._condensed_history = list(self.session.history)
        else:
            self._condensed_history = self.session.history[-self.max_history :]

    @property
    def condensed_history(self) -> Iterable[ConversationMessage]:
        if not self._condensed_history:
            self._refresh_history()
        return list(self._condensed_history)
