"""
Utilities for managing paper search results and selections.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from .models import ConversationSession, PaperSummary


@dataclass
class SearchListManager:
    """
    Maintains per-session paper catalogues and selections.
    Provides utilities to merge search results, filter, and track selection history.
    """

    _catalogue: Dict[str, PaperSummary] = field(default_factory=dict)

    def register(self, papers: Iterable[PaperSummary]) -> None:
        for paper in papers:
            self._catalogue[paper.paper_id] = paper

    def get(self, paper_id: str) -> Optional[PaperSummary]:
        return self._catalogue.get(paper_id)

    def list_catalogue(self) -> List[PaperSummary]:
        return list(self._catalogue.values())

    def select(self, session: ConversationSession, paper_ids: Sequence[str]) -> List[PaperSummary]:
        unique_ids = list(dict.fromkeys(pid for pid in paper_ids if pid in self._catalogue))
        session.selected_ids = unique_ids
        return self.bulk_get(unique_ids)

    def add_to_selection(self, session: ConversationSession, paper_ids: Sequence[str]) -> List[PaperSummary]:
        current = list(session.selected_ids)
        seen = set(current)
        for pid in paper_ids:
            if pid in self._catalogue and pid not in seen:
                current.append(pid)
                seen.add(pid)
        session.selected_ids = current
        return self.bulk_get(current)

    def remove_from_selection(self, session: ConversationSession, paper_ids: Sequence[str]) -> List[PaperSummary]:
        paper_ids = set(paper_ids)
        session.selected_ids = [pid for pid in session.selected_ids if pid not in paper_ids]
        return self.bulk_get(session.selected_ids)

    def bulk_get(self, paper_ids: Iterable[str]) -> List[PaperSummary]:
        return [self._catalogue[pid] for pid in paper_ids if pid in self._catalogue]

    def filter_by_years(self, years: int) -> List[PaperSummary]:
        if years <= 0:
            return self.list_catalogue()
        current_year = _dt.datetime.now(_dt.timezone.utc).year
        cutoff = current_year - (years - 1)
        return [paper for paper in self._catalogue.values() if paper.year and paper.year >= cutoff]

    def filter_by_keywords(self, keywords: Sequence[str]) -> List[PaperSummary]:
        if not keywords:
            return self.list_catalogue()
        needles = [word.lower() for word in keywords]
        matches: List[PaperSummary] = []
        for paper in self._catalogue.values():
            haystack = f"{paper.title} {paper.abstract}".lower()
            if all(needle in haystack for needle in needles):
                matches.append(paper)
        return matches
