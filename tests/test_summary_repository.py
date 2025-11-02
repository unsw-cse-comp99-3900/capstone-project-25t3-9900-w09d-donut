from server.data_access.summary_repository import SummaryRepository


def test_summary_repository_cycle(temp_db):
    repo = SummaryRepository()
    summary_id = repo.create_summary(
        history_id=1,
        session_id="session-123",
        summary_type="comprehensive",
        summary_text="Detailed summary text.",
        pdf_path="storage/summary_pdfs/test.pdf",
        focus_aspect="methodology",
    )

    stored = repo.get_summary(summary_id)
    assert stored is not None
    assert stored["session_id"] == "session-123"
    assert stored["summary_type"] == "comprehensive"

    listing = repo.list_by_session("session-123")
    assert listing and listing[0]["id"] == summary_id
