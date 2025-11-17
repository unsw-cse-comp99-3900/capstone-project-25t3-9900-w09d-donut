from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from ai_agents.services.deep_research import DeepResearchAgent
from server.data_access.search_history_repository import SearchHistoryRepository
from server.data_access.paper_repository import PaperRepository
from server.services.academic_search import search_openalex_papers

logger = logging.getLogger(__name__)


class DeepResearchService:
    """
    Coordinates multi-round deep research workflows by combining the existing
    search history, targeted follow-up searches, and the DeepResearchAgent.
    """

    def __init__(
        self,
        *,
        history_repository: Optional[SearchHistoryRepository] = None,
        agent: Optional[DeepResearchAgent] = None,
        paper_repository: Optional[PaperRepository] = None,
    ) -> None:
        self._history_repository = history_repository or SearchHistoryRepository()
        self._agent = agent or DeepResearchAgent()
        self._paper_repository = paper_repository

    def run_deep_research(
        self,
        *,
        history_id: int,
        selected_ids: Optional[Sequence[str]],
        question: str,
        instructions: Optional[str] = None,
        language: str = "en",
        rounds: int = 2,
        breadth: int = 3,
        per_query_limit: int = 3,
        seed_limit: int = 12,
    ) -> Dict[str, object]:
        record = self._history_repository.get_history_with_papers(history_id)
        if not record:
            raise ValueError("History not found")

        cleaned_selected = _unique_nonempty(selected_ids or [])
        seed_papers = self._collect_seed_documents(record.get("papers") or [], cleaned_selected, limit=seed_limit)
        if not seed_papers:
            raise ValueError("No papers available for deep research")

        question_text = str(question or "").strip() or str(record.get("query") or "Deep research investigation")
        instruction_block = instructions.strip() if isinstance(instructions, str) else None

        rounds_cap = max(1, min(int(rounds), 4))
        breadth_cap = max(1, min(int(breadth), 5))
        per_query_cap = max(1, min(int(per_query_limit), 5))

        context_rounds: List[Mapping[str, object]] = []
        collected_rounds: List[Mapping[str, object]] = []
        search_iterations: List[Dict[str, object]] = []
        appended_docs: List[Dict[str, object]] = []

        round_documents = seed_papers
        round_queries: List[Dict[str, object]] = [
            {
                "query": question_text,
                "focus": "Seed selection review",
                "rationale": instruction_block or "User-selected corpus",
                "keywords": record.get("filters", {}).get("keywords") or [],
            }
        ]

        search_iterations.append(
            {
                "round_index": 1,
                "queries": round_queries,
                "documents": [self._summarize_document(doc) for doc in round_documents],
            }
        )

        for round_index in range(1, rounds_cap + 1):
            if not round_documents:
                break

            round_result = self._agent.summarize_round(
                user_query=question_text,
                round_index=round_index,
                documents=round_documents,
                queries=round_queries,
                context=context_rounds,
                language=language,
                instructions=instruction_block or question_text,
            )
            round_payload = round_result.to_dict()
            collected_rounds.append(round_payload)
            context_rounds.append(round_payload)

            if round_index >= rounds_cap:
                break

            generated_queries = self._agent.generate_queries(
                user_query=question_text,
                context=context_rounds,
                breadth=breadth_cap,
                language=language,
                extra_instructions=instruction_block,
            )
            if not generated_queries:
                break

            followup_docs = self._collect_followup_documents(generated_queries, limit=per_query_cap)
            if not followup_docs:
                break

            round_documents = followup_docs
            round_queries = generated_queries
            appended_docs.extend(followup_docs)
            search_iterations.append(
                {
                    "round_index": round_index + 1,
                    "queries": round_queries,
                    "documents": [self._summarize_document(doc) for doc in round_documents],
                }
            )

        if not collected_rounds:
            raise ValueError("Unable to build any deep research rounds")

        report = self._agent.build_report(
            user_query=question_text,
            rounds=collected_rounds,
            instructions=instruction_block,
            language=language,
        )

        return {
            "history_id": history_id,
            "rounds": collected_rounds,
            "report": report,
            "metadata": {
                "seed_paper_ids": [doc.get("id") for doc in seed_papers],
                "search_iterations": search_iterations,
                "language": language,
                "new_papers": appended_docs,
            },
        }

    def _collect_seed_documents(
        self,
        papers: Sequence[Mapping[str, object]],
        selected_ids: Sequence[str],
        *,
        limit: int,
    ) -> List[Dict[str, object]]:
        chosen = set(selected_ids)
        staged: List[tuple[Mapping[str, object], str]] = []
        for paper in papers:
            paper_id = str(paper.get("paper_id") or paper.get("id") or "").strip()
            if not paper_id:
                continue
            if chosen and paper_id not in chosen:
                continue
            if not chosen:
                selected_flag = paper.get("selected")
                if selected_flag in (0, "0", False, None):
                    continue
            staged.append((paper, paper_id))

        fulltext_map: Dict[str, Dict[str, object]] = {}
        if self._paper_repository and staged:
            try:
                fulltext_map = self._paper_repository.fetch_fulltext_map([pid for _, pid in staged])
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to fetch fulltext map for deep research: %s", exc)

        payloads: List[Dict[str, object]] = []
        for paper, paper_id in staged:
            serialized = self._serialize_paper(paper, fulltext_map.get(paper_id))
            if not serialized:
                continue
            payloads.append(serialized)
            if len(payloads) >= limit:
                break
        return payloads

    def _collect_followup_documents(self, queries: Sequence[Mapping[str, object]], limit: int) -> List[Dict[str, object]]:
        docs: List[Dict[str, object]] = []
        seen: set[str] = set()
        for entry in queries:
            query_text = str(entry.get("query") or "").strip()
            if not query_text:
                continue
            try:
                results = search_openalex_papers([query_text], limit=limit)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Deep research query failed: %s", exc)
                continue
            for item in results:
                serialized = self._serialize_search_result(item)
                if not serialized:
                    continue
                doc_id = serialized.get("id")
                if not doc_id or doc_id in seen:
                    continue
                seen.add(doc_id)
                docs.append(serialized)
        return docs

    @staticmethod
    def _serialize_paper(
        paper: Mapping[str, object],
        fulltext_payload: Optional[Mapping[str, object]] = None,
    ) -> Optional[Dict[str, object]]:
        paper_id = str(paper.get("paper_id") or paper.get("id") or "").strip()
        if not paper_id:
            return None
        title = str(paper.get("title") or paper.get("display_name") or "Untitled").strip()
        best_oa = paper.get("best_oa_location")
        if isinstance(best_oa, Mapping):
            candidate_link = best_oa.get("pdf_url") or best_oa.get("url")
        else:
            candidate_link = ""
        link = str(
            paper.get("url")
            or paper.get("link")
            or paper.get("pdf_url")
            or candidate_link
            or ""
        ).strip()
        summary_text = str(paper.get("summary") or paper.get("abstract") or "").strip()
        fulltext_text = str(
            paper.get("full_text")
            or (fulltext_payload or {}).get("plain_text")
            or paper.get("plain_text")
            or ""
        ).strip()
        if not summary_text and fulltext_text:
            summary_text = fulltext_text[:600]
        sections = (
            paper.get("sections")
            or (fulltext_payload or {}).get("sections")
            or paper.get("structured_sections")
            or (fulltext_payload or {}).get("structured_sections")
            or []
        )
        tables = (paper.get("tables") or (fulltext_payload or {}).get("tables") or [])
        metadata = (fulltext_payload or {}).get("metadata") or paper.get("fulltext_metadata") or {}
        return {
            "id": paper_id,
            "paper_id": paper_id,
            "title": title or f"Paper {paper_id}",
            "summary": summary_text,
            "abstract": str(paper.get("abstract") or "").strip(),
            "full_text": fulltext_text or summary_text,
            "link": link,
            "sections": sections,
            "tables": tables,
            "metadata": metadata,
        }

    @staticmethod
    def _serialize_search_result(item: Mapping[str, object]) -> Optional[Dict[str, object]]:
        paper_id = str(item.get("id") or item.get("paper_id") or "").strip()
        if not paper_id:
            return None
        title = str(item.get("title") or item.get("display_name") or "Untitled").strip()
        summary = str(item.get("summary") or item.get("abstract") or "").strip()
        return {
            "id": paper_id,
            "paper_id": paper_id,
            "title": title or f"Paper {paper_id}",
            "summary": summary,
            "abstract": summary,
            "full_text": summary,
            "link": str(item.get("link") or item.get("url") or item.get("pdf_url") or "").strip(),
        }

    @staticmethod
    def _summarize_document(doc: Mapping[str, object]) -> Dict[str, object]:
        return {
            "id": doc.get("id"),
            "title": doc.get("title"),
            "snippet": (doc.get("summary") or doc.get("abstract") or "")[:240],
        }


def _unique_nonempty(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered
