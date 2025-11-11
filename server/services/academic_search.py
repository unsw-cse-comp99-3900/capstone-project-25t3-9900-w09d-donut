from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

import requests

from server.data_access.paper_repository import PaperRepository
from server.data_access.search_history_repository import SearchHistoryRepository

if TYPE_CHECKING:
    from .docling_service import DoclingIngestionService
    from .pdf_cache_service import PDFCacheService

def search_openalex_papers(
    keywords: List[str],
    date_range: Optional[Tuple[str, str]] = None,
    concepts: Optional[List[str]] = None,
    limit: int = 50,
) -> List[dict]:
    """Call OpenAlex works endpoint and return simplified paper dicts."""

    base_url = "https://api.openalex.org/works"
    headers = {"User-Agent": "ai-research-companion/1.0 (mailto:2126546982@qq.com)"}

    query = " ".join(keywords)

    filters: List[str] = []
    if date_range:
        start, end = date_range
        filters.append(f"from_publication_date:{start}")
        filters.append(f"to_publication_date:{end}")
    if concepts:
        for cid in concepts:
            filters.append(f"concepts.id:{cid}")
    filters.append("is_oa:true")
    filter_str = ",".join(filters)

    params = {
        "search": query,
        "filter": filter_str,
        "sort": "relevance_score:desc",
        "per_page": limit,
        "mailto": "2126546982@qq.com",
        "select": (
            "id,display_name,authorships,publication_date,publication_year,"
            "cited_by_count,locations,best_oa_location,abstract_inverted_index,primary_location"
        ),
    }

    from urllib.parse import urlencode

    encoded = urlencode(params, doseq=True).replace("%40", "@")
    url = f"{base_url}?{encoded}"

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json().get("results", [])

    papers: List[dict] = []
    for item in data:
        pdf_url = (item.get("best_oa_location") or {}).get("pdf_url")
        if not pdf_url:
            continue

        summary = ""
        inverted = item.get("abstract_inverted_index")
        if inverted:
            words = sorted((pos, word) for word, positions in inverted.items() for pos in positions)
            summary = " ".join(word for _, word in words).strip()

        authors = [
            a["author"]["display_name"].strip()
            for a in item.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ]

        papers.append(
            {
                "id": item.get("id"),
                "title": (item.get("display_name") or "").strip(),
                "authors": authors,
                "summary": summary,
                "publication_date": item.get("publication_date") or str(item.get("publication_year")),
                "publication_year": item.get("publication_year"),
                "source": ((item.get("primary_location") or {}).get("source") or {}).get("display_name", ""),
                "cited_by_count": item.get("cited_by_count", 0),
                "link": item.get("id"),
                "pdf_url": pdf_url,
                "raw": item,
            }
        )

    return papers


@dataclass
class AcademicSearchService:
    paper_repository: PaperRepository
    history_repository: SearchHistoryRepository
    docling_service: Optional["DoclingIngestionService"]
    pdf_cache_service: Optional["PDFCacheService"]

    def __init__(
        self,
        paper_repository: Optional[PaperRepository] = None,
        history_repository: Optional[SearchHistoryRepository] = None,
        docling_service: Optional["DoclingIngestionService"] = None,
        pdf_cache_service: Optional["PDFCacheService"] = None,
    ) -> None:
        self.paper_repository = paper_repository or PaperRepository()
        self.history_repository = history_repository or SearchHistoryRepository()
        self.docling_service = docling_service
        self.pdf_cache_service = pdf_cache_service

    def search_and_store(
        self,
        *,
        user_id: Optional[int],
        keywords: Sequence[str],
        date_range: Optional[Tuple[str, str]] = None,
        concepts: Optional[Sequence[str]] = None,
        limit: int = 50,
        session_id: Optional[str] = None,
    ) -> Tuple[int, List[dict]]:
        results = search_openalex_papers(
            list(keywords),
            date_range=date_range,
            concepts=list(concepts) if concepts else None,
            limit=limit,
        )
        self.paper_repository.upsert_many(results)
        cached_paths = self._cache_pdfs(results)
        self._attach_cached_paths(results, cached_paths)

        filters_payload = {
            "keywords": list(keywords),
            "date_range": list(date_range) if date_range else None,
            "concepts": list(concepts) if concepts else None,
            "limit": limit,
        }

        history_id = self.history_repository.create_history(
            user_id=user_id,
            query=" ".join(keywords),
            filters=filters_payload,
            papers=results,
            session_id=session_id,
        )
        if self.docling_service:
            self.docling_service.enqueue_many(results)
        return history_id, results

    def load_history(self, history_id: int) -> Optional[dict]:
        return self.history_repository.get_history_with_papers(history_id)

    def list_user_history(self, user_id: int, limit: int = 20, offset: int = 0) -> List[dict]:
        return self.history_repository.list_by_user(user_id, limit=limit, offset=offset)

    def search_and_append(
        self,
        history_id: int,
        *,
        keywords: Sequence[str],
        date_range: Optional[Tuple[str, str]] = None,
        concepts: Optional[Sequence[str]] = None,
        limit: int = 5,
    ) -> List[dict]:
        results = search_openalex_papers(
            list(keywords),
            date_range=date_range,
            concepts=list(concepts) if concepts else None,
            limit=limit,
        )
        if not results:
            return []

        self.paper_repository.upsert_many(results)
        cached_paths = self._cache_pdfs(results)
        self._attach_cached_paths(results, cached_paths)
        if self.docling_service:
            self.docling_service.enqueue_many(results)
        appended_ids = self.history_repository.append_papers(history_id, results, selected=True)
        appended_set = set(appended_ids)
        return [item for item in results if (item.get("id") or item.get("paper_id")) in appended_set]

    def _cache_pdfs(self, papers: Sequence[dict]) -> dict:
        if not self.pdf_cache_service:
            return {}
        return self.pdf_cache_service.cache_many(papers)

    @staticmethod
    def _attach_cached_paths(papers: Sequence[dict], cached_paths: dict) -> None:
        if not cached_paths:
            return
        for paper in papers:
            paper_id = paper.get("id") or paper.get("paper_id")
            if paper_id and paper_id in cached_paths:
                paper["cached_pdf_path"] = cached_paths[paper_id]
