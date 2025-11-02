import json
import tempfile
from pathlib import Path

import pytest

from server import create_app
from ai_agents.services.models import AgentReply
from ai_agents.services.pdf_builder import SummaryPdfBuilder
from server.data_access import (
    ConversationRepository,
    PaperRepository,
    SearchHistoryRepository,
    SummaryRepository,
    ensure_conversation_tables,
    ensure_papers_table,
    ensure_search_history_tables,
    ensure_summary_tables,
)
from server.services.academic_search import AcademicSearchService
from server.services.ai_conversation_service import AIConversationService
from server.services.search_extension_tool import SearchExtensionTool
from server.controllers import api_controller as api
from server.data_access.user_repository import ensure_users_table, create_user


@pytest.fixture
def client(temp_db, monkeypatch):
    # reinitialize repositories against the temp database
    ensure_users_table()
    ensure_papers_table()
    ensure_search_history_tables()
    ensure_conversation_tables()
    ensure_summary_tables()

    api.paper_repository = PaperRepository()
    api.search_history_repository = SearchHistoryRepository()
    api.conversation_repository = ConversationRepository()
    api.summary_repository = SummaryRepository()
    api.academic_search_service = AcademicSearchService(
        paper_repository=api.paper_repository,
        history_repository=api.search_history_repository,
    )
    api.conversation_service = AIConversationService(
        paper_repository=api.paper_repository,
        history_repository=api.search_history_repository,
    )
    api.conversation_service.register_tool(SearchExtensionTool(api.academic_search_service))
    api.summary_pdf_builder = SummaryPdfBuilder(output_dir=Path(tempfile.mkdtemp()))

    app = create_app("development")
    app.testing = True
    with app.test_client() as client:
        yield client


def test_summary_generation_flow(client, monkeypatch):
    # Prepare user and history records
    ensure_users_table()
    user_id = create_user("Tester", "tester@example.com", "hash")

    paper_payload = {
        "id": "P1",
        "title": "Paper One",
        "authors": ["Alice"],
        "summary": "Detailed abstract.",
        "publication_year": 2025,
        "publication_date": "2025-01-01",
        "source": "Test Source",
        "cited_by_count": 1,
        "link": "https://example.org/p1",
        "pdf_url": "https://example.org/p1.pdf",
    }
    api.paper_repository.upsert_many([paper_payload])
    history_id = api.search_history_repository.create_history(
        user_id=user_id,
        query="test",
        filters={},
        papers=[paper_payload],
        session_id=None,
    )

    session_id = "session-test"
    api.conversation_repository.upsert_session(session_id, history_id=history_id, user_id=user_id, selected_ids=["P1"])
    api.conversation_service.load_history_into_session(history_id, session_id=session_id)

    api.conversation_service.handle_message = lambda sid, msg, history_id=None: AgentReply(
        text="Comprehensive summary text.",
        selected_ids=["P1"],
        citations=["Paper One"],
        metadata={"summary_type": "comprehensive"},
    )

    headers = {
        "Content-Type": "application/json",
        "X-User-Email": "tester@example.com",
    }

    resp = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        data=json.dumps({"message": "Generate a comprehensive summary."}),
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["pdf_url"]
    assert data["summary_id"] is not None

    download_resp = client.get(f"/api/chat/sessions/{session_id}/summaries/{data['summary_id']}/download", headers=headers)
    assert download_resp.status_code == 200
    assert download_resp.data  # PDF bytes
