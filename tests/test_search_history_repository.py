import pytest

from server.data_access.paper_repository import PaperRepository
from server.data_access.search_history_repository import SearchHistoryRepository


def sample_papers():
    return [
        {
            "id": "https://openalex.org/W1",
            "title": "Sample Paper One",
            "authors": ["Alice", "Bob"],
            "summary": "Explores testing patterns for AI agents.",
            "publication_date": "2024-03-01",
            "publication_year": 2024,
            "source": "Journal of Testing",
            "cited_by_count": 42,
            "link": "https://openalex.org/W1",
            "pdf_url": "https://example.org/paper1.pdf",
        },
        {
            "id": "https://openalex.org/W2",
            "title": "Sample Paper Two",
            "authors": ["Carol"],
            "summary": "Discusses retrieval augmented generation.",
            "publication_date": "2023-11-12",
            "publication_year": 2023,
            "source": "AI Letters",
            "cited_by_count": 10,
            "link": "https://openalex.org/W2",
            "pdf_url": "https://example.org/paper2.pdf",
        },
    ]


def test_search_history_persistence(temp_db):
    paper_repo = PaperRepository()
    history_repo = SearchHistoryRepository()

    data = sample_papers()
    paper_repo.upsert_many(data)

    history_id = history_repo.create_history(
        user_id=1,
        query="sample query",
        filters={"keywords": ["sample", "ai"]},
        papers=data,
        session_id="session-1",
    )

    stored = history_repo.get_history_with_papers(history_id)
    assert stored is not None
    assert stored["query"] == "sample query"
    assert stored["result_count"] == 2
    assert len(stored["papers"]) == 2
    first = stored["papers"][0]
    assert first["paper_id"] == "https://openalex.org/W1"
    assert first["authors"] == ["Alice", "Bob"]

    history_repo.update_selection(history_id, ["https://openalex.org/W2"])
    updated = history_repo.get_history_with_papers(history_id)
    selected_flags = {item["paper_id"]: item["selected"] for item in updated["papers"]}
    assert selected_flags["https://openalex.org/W1"] == 0
    assert selected_flags["https://openalex.org/W2"] == 1


def test_append_new_papers(temp_db):
    paper_repo = PaperRepository()
    history_repo = SearchHistoryRepository()

    data = sample_papers()
    paper_repo.upsert_many(data)
    history_id = history_repo.create_history(
        user_id=1,
        query="sample query",
        filters={"keywords": ["sample", "ai"]},
        papers=data[:1],
        session_id="session-append",
    )

    additional = [
        {
            "id": "https://openalex.org/W3",
            "title": "Third Sample Paper",
            "authors": ["Dana"],
            "summary": "Adds more context.",
            "publication_date": "2024-07-10",
            "publication_year": 2024,
            "source": "AI Letters",
            "cited_by_count": 5,
            "link": "https://openalex.org/W3",
            "pdf_url": "https://example.org/paper3.pdf",
        },
        {
            "id": "https://openalex.org/W1",  # duplicate should be ignored
            "title": "Duplicate",
            "authors": [],
            "summary": "",
            "publication_date": "2024-01-01",
            "publication_year": 2024,
            "source": "",
            "cited_by_count": 0,
            "link": "https://openalex.org/W1",
            "pdf_url": "https://example.org/paper1.pdf",
        },
    ]
    paper_repo.upsert_many(additional)

    inserted_ids = history_repo.append_papers(history_id, additional, selected=True)
    assert inserted_ids == ["https://openalex.org/W3"]

    stored = history_repo.get_history_with_papers(history_id)
    assert stored["result_count"] == 2
    stored_ids = [item["paper_id"] for item in stored["papers"]]
    assert "https://openalex.org/W3" in stored_ids
    selected_flags = {item["paper_id"]: item["selected"] for item in stored["papers"]}
    assert selected_flags["https://openalex.org/W3"] == 1
