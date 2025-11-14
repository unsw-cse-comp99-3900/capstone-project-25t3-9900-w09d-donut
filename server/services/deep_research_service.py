from __future__ import annotations

import logging
from typing import Dict, List, Mapping, Optional, Sequence

from ai_agents.services.deep_research import DeepResearchAgent
from server.data_access.paper_repository import PaperRepository
from server.data_access.search_history_repository import SearchHistoryRepository

logger = logging.getLogger(__name__)


class DeepResearchService:
    """Orchestrates multi-step deep research runs on top of stored papers."""

    def __init__(
        self,
        *,
        paper_repository: Optional[PaperRepository] = None,
        history_repository: Optional[SearchHistoryRepository] = None,
        agent: Optional[DeepResearchAgent] = None,
        max_docs: int = 6,
        max_chars: int = 2200,
    ) -> None:
        self._papers = paper_repository or PaperRepository()
        self._history = history_repository or SearchHistoryRepository()
        self._agent = agent or DeepResearchAgent()
        self._max_docs = max_docs
        self._max_chars = max_chars

    def run(
        self,
        *,
        history_id: int,
        paper_ids: Sequence[str],
        instructions: Optional[str],
        language: str = "en",
    ) -> Dict[str, object]:
        history = self._history.get_history_with_papers(history_id)
        if not history:
            raise ValueError("Search history not found.")

        user_query = str(history.get("query") or instructions or "Deep research request").strip()
        selected_docs = self._collect_documents(history, paper_ids)
        if not selected_docs:
            raise ValueError("Selected papers are not available or have not been parsed yet.")

        doc_payloads = [self._build_document_payload(doc) for doc in selected_docs[: self._max_docs]]
        if not any(doc.get("full_text") for doc in doc_payloads):
            raise ValueError("Selected papers do not have parsed text yet. Refresh the parsed status and try again.")

        round_summary = self._agent.summarize_round(
            user_query=user_query,
            round_index=1,
            documents=doc_payloads,
            queries=[{"query": user_query, "focus": instructions or "core topic"}],
            context=[],
            language=language,
            instructions=instructions,
        )
        round_payload = round_summary.to_dict()
        memo = self._agent.build_report(
            user_query=user_query,
            rounds=[round_payload],
            instructions=instructions,
            language=language,
        )
        query_suggestions = self._agent.generate_queries(
            user_query=user_query,
            context=[round_payload],
            extra_instructions=instructions,
            language=language,
        )

        return {
            "round": round_payload,
            "report": memo,
            "query_suggestions": query_suggestions,
            "documents_used": [doc.get("paper_id") for doc in selected_docs[: self._max_docs]],
        }

    def _collect_documents(self, history: Mapping[str, object], requested_ids: Sequence[str]) -> List[Mapping[str, object]]:
        papers = history.get("papers") or []
        if not isinstance(papers, list):
            return []
        if requested_ids:
            requested_set = [pid for pid in requested_ids if pid]
            docs = [paper for paper in papers if paper.get("paper_id") in requested_set]
        else:
            docs = papers
        return docs

    def _build_document_payload(self, paper: Mapping[str, object]) -> Dict[str, object]:
        paper_id = paper.get("paper_id") or paper.get("id") or ""
        title = paper.get("title") or paper.get("display_name") or "Untitled paper"
        text = self._extract_text(paper)
        url = paper.get("url") or paper.get("link") or paper.get("pdf_url") or ""
        return {
            "id": paper_id,
            "paper_id": paper_id,
            "title": title,
            "full_text": text,
            "summary": text,
            "abstract": paper.get("abstract") or "",
            "link": url,
            "url": url,
        }

    def _extract_text(self, paper: Mapping[str, object]) -> str:
        chunks = paper.get("chunks") or []
        if isinstance(chunks, list) and chunks:
            excerpts: List[str] = []
            remaining = self._max_chars
            for chunk in chunks:
                if not isinstance(chunk, Mapping):
                    continue
                text_part = str(chunk.get("text") or "").strip()
                if not text_part:
                    continue
                if len(text_part) > remaining:
                    text_part = text_part[:remaining]
                excerpts.append(text_part)
                remaining -= len(text_part)
                if remaining <= 0:
                    break
            if excerpts:
                return "\n\n".join(excerpts)

        text = (
            str(paper.get("full_text") or "")
            or str(paper.get("summary") or "")
            or str(paper.get("abstract") or "")
        ).strip()
        if len(text) > self._max_chars:
            text = text[: self._max_chars] + "..."
        return text
