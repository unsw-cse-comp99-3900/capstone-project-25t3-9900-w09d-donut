import pytest

from ai_agents.services.conversation_agent import ConversationAgent, PaperSummary
from ai_agents.services.tooling import AgentTool, ToolContext, ToolRegistry, ToolResult


class FakeKeywordExpansionTool:
    name = "keyword_expansion"

    def __init__(self) -> None:
        self.calls = []

    def execute(self, context: ToolContext, payload) -> ToolResult:
        self.calls.append((context, payload))
        return ToolResult(
            text="keywords expanded",
            citations=[],
            selected_ids=[],
            metadata={
                "must_terms": ["llm"],
                "should_terms": ["transformer"],
                "filters": {"year_from": "2023"},
                "filters_diff": {"year_from": "2023"},
            },
        )


class FakeQuickSummaryTool:
    name = "quick_summary"

    def __init__(self) -> None:
        self.last_context: ToolContext | None = None
        self.last_payload = None

    def execute(self, context: ToolContext, payload) -> ToolResult:
        self.last_context = context
        self.last_payload = payload
        selected_ids = payload.get("selected_ids") or []
        return ToolResult(
            text="Here is the quick summary.",
            citations=["Test Paper"],
            selected_ids=selected_ids,
            metadata={"used_count": len(payload.get("papers", [])), "prompt_tokens": 128},
        )


@pytest.fixture
def sample_paper() -> PaperSummary:
    return PaperSummary(
        paper_id="P1",
        title="Test Paper",
        abstract="A paper about testing AI agents.",
        authors=["Alice", "Bob"],
        year=2024,
        url="https://example.org/p1",
    )


def test_keyword_expansion_updates_session_filters():
    registry = ToolRegistry()
    keyword_tool = FakeKeywordExpansionTool()
    registry.register(keyword_tool)

    agent = ConversationAgent(tool_registry=registry)
    session = agent.start_session("session-kw")

    reply = agent.handle_message("session-kw", "Please expand keyword LLM transformer.")

    assert "核心词" in reply.text
    assert session.filters["keywords"] == ["llm", "transformer"]
    assert session.filters["search_filters"] == {"year_from": "2023"}
    assert keyword_tool.calls, "keyword expansion tool should be invoked"
    _, payload = keyword_tool.calls[0]
    assert payload["keywords"] == ["LLM transformer"]


def test_quick_summary_invokes_tool_with_selected_papers(sample_paper: PaperSummary):
    registry = ToolRegistry()
    summary_tool = FakeQuickSummaryTool()
    registry.register(summary_tool)

    agent = ConversationAgent(tool_registry=registry)
    agent.ingest_papers([sample_paper])
    agent.start_session("session-summary", initial_selection=["P1"])

    reply = agent.handle_message("session-summary", "Could you summarize these papers?")

    assert reply.text == "Here is the quick summary."
    assert reply.citations == ["Test Paper"]
    assert summary_tool.last_payload is not None
    papers_payload = summary_tool.last_payload["papers"]
    assert len(papers_payload) == 1
    assert papers_payload[0].paper_id == "P1"
