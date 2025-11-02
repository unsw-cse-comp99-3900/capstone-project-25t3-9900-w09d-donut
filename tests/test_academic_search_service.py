from ai_agents.services.tooling import ToolContext
from server.data_access.paper_repository import PaperRepository
from server.data_access.search_history_repository import SearchHistoryRepository
from server.services.academic_search import AcademicSearchService
from server.services.search_extension_tool import SearchExtensionTool


def sample_openalex_results():
    return [
        {
            "id": "https://openalex.org/W100",
            "title": "Benchmarking Retrieval Augmented Generation",
            "authors": ["Alice Tester"],
            "summary": "Discusses evaluation pipelines.",
            "publication_date": "2024-05-01",
            "publication_year": 2024,
            "source": "AI Journal",
            "cited_by_count": 12,
            "link": "https://openalex.org/W100",
            "pdf_url": "https://example.org/w100.pdf",
        },
        {
            "id": "https://openalex.org/W101",
            "title": "Advances in Long-Context Retrieval",
            "authors": ["Bob Researcher"],
            "summary": "Explores long-document retrieval.",
            "publication_date": "2023-08-15",
            "publication_year": 2023,
            "source": "ML Proceedings",
            "cited_by_count": 7,
            "link": "https://openalex.org/W101",
            "pdf_url": "https://example.org/w101.pdf",
        },
    ]


def test_search_and_append_appends_new_papers(temp_db, monkeypatch):
    paper_repo = PaperRepository()
    history_repo = SearchHistoryRepository()
    service = AcademicSearchService(paper_repository=paper_repo, history_repository=history_repo)

    history_id = history_repo.create_history(
        user_id=1,
        query="initial",
        filters={},
        papers=[],
        session_id="session-base",
    )

    monkeypatch.setattr(
        "server.services.academic_search.search_openalex_papers",
        lambda *args, **kwargs: sample_openalex_results(),
    )

    appended = service.search_and_append(history_id, keywords=["rag"], limit=2)
    assert len(appended) == 2

    stored = history_repo.get_history_with_papers(history_id)
    assert stored["result_count"] == 2
    stored_ids = {item["paper_id"] for item in stored["papers"]}
    assert "https://openalex.org/W100" in stored_ids
    assert "https://openalex.org/W101" in stored_ids


def test_search_extension_tool_uses_service():
    history_id = 7

    class DummyService:
        def __init__(self):
            self.calls = []

        def search_and_append(self, history_id: int, *, keywords, date_range=None, concepts=None, limit: int = 5):
            self.calls.append((history_id, tuple(keywords), limit))
            return [
                {
                    "id": "https://openalex.org/W200",
                    "title": "Extra Paper",
                    "authors": ["Eve"],
                    "summary": "Extra details.",
                    "publication_year": 2024,
                    "link": "https://openalex.org/W200",
                    "pdf_url": "https://example.org/w200.pdf",
                }
            ]

    dummy_service = DummyService()
    tool = SearchExtensionTool(dummy_service)  # type: ignore[arg-type]

    context = ToolContext(session_id="session-base", memory_snapshot=None, extras={"history_id": history_id})
    result = tool.execute(
        context,
        {
            "keywords": ["retrieval augmented generation"],
            "history_id": history_id,
            "limit": 2,
            "existing_ids": [],
        },
    )

    assert result.metadata["papers"][0]["id"] == "https://openalex.org/W200"
    assert dummy_service.calls == [(history_id, ("retrieval augmented generation",), 2)]
