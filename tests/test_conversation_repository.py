from server.data_access.conversation_repository import ConversationRepository


def test_conversation_repository_persists_sessions_and_messages(temp_db):
    repo = ConversationRepository()

    repo.upsert_session("session-1", history_id=5, user_id=10, selected_ids=["P1", "P2"])
    session = repo.get_session("session-1")
    assert session is not None
    assert session["history_id"] == 5
    assert session["selected_ids"] == ["P1", "P2"]

    repo.append_messages(
        "session-1",
        [
            {"role": "user", "content": "Hello", "metadata": {"foo": "bar"}},
            {"role": "assistant", "content": "Hi there", "metadata": {"citations": ["Paper"]}},
        ],
    )

    messages = repo.list_messages("session-1")
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["metadata"]["foo"] == "bar"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["metadata"]["citations"] == ["Paper"]

    repo.upsert_session("session-1", history_id=5, user_id=10, selected_ids=["P2"])
    updated = repo.get_session("session-1")
    assert updated["selected_ids"] == ["P2"]
