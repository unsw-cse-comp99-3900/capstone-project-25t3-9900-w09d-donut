from typing import Optional

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
        self.last_context: Optional[ToolContext] = None
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


class FakeGlobalSummaryTool:
    name = "global_summary"

    def __init__(self) -> None:
        self.last_payload = None

    def execute(self, context: ToolContext, payload) -> ToolResult:
        self.last_payload = payload
        return ToolResult(
            text="Comprehensive synthesis covering methods, findings, and limitations.",
            citations=["Paper Alpha", "Paper Beta"],
            selected_ids=payload.get("selected_ids") or [],
            metadata={"summary_type": "comprehensive"},
        )


class FakeFocusedSynthesisTool:
    name = "focused_synthesis"

    def __init__(self) -> None:
        self.calls = []

    def execute(self, context: ToolContext, payload) -> ToolResult:
        self.calls.append((context, payload))
        aspect = payload.get("focus_aspect") or "unspecified focus"
        selected_ids = payload.get("selected_ids") or []
        return ToolResult(
            text=f"Focused insight about {aspect}.",
            citations=["Focused Paper"],
            selected_ids=selected_ids,
            metadata={"focus_aspect": aspect, "count": len(payload.get("papers", []))},
        )


class FakeSearchExtensionTool:
    name = "search_extension"

    def execute(self, context: ToolContext, payload) -> ToolResult:
        return ToolResult(
            text="Retrieved 1 additional paper and updated the selection.",
            citations=[],
            selected_ids=payload.get("selected_ids") or [],
            metadata={
                "papers": [
                    {
                        "id": "P2",
                        "title": "Evaluation Benchmarks",
                        "summary": "Detailed exploration of evaluation strategies.",
                        "authors": ["Dana"],
                        "publication_year": 2024,
                        "link": "https://example.org/p2",
                    }
                ]
            },
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

    assert "Core terms" in reply.text
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


def test_focus_summary_after_selection_changes(sample_paper: PaperSummary):
    second_paper = PaperSummary(
        paper_id="P2",
        title="Another Paper",
        abstract="Explores focus testing.",
        authors=["Carol"],
        year=2023,
        url="https://example.org/p2",
    )

    registry = ToolRegistry()
    focus_tool = FakeFocusedSynthesisTool()
    registry.register(focus_tool)

    agent = ConversationAgent(tool_registry=registry)
    agent.ingest_papers([sample_paper, second_paper])
    session = agent.start_session("session-focus", initial_selection=["P1", "P2"])

    remove_reply = agent.handle_message("session-focus", "Please remove paper P2 from the list.")
    assert "Removed" in remove_reply.text
    assert session.selected_ids == ["P1"], "Expected only first paper to remain selected"

    focus_reply = agent.handle_message("session-focus", "Focus on the methodology of the remaining papers.")
    assert "Focused insight" in focus_reply.text
    assert focus_reply.citations == ["Focused Paper"]
    assert session.selected_ids == ["P1"]

    assert len(focus_tool.calls) == 1
    _, payload = focus_tool.calls[0]
    assert payload["focus_aspect"].lower().startswith("the methodology")
    assert len(payload["papers"]) == 1
    assert payload["papers"][0].paper_id == "P1"


def test_multi_step_conversation_flow_returns_expected_responses(sample_paper: PaperSummary):
    second_paper = PaperSummary(
        paper_id="P2",
        title="Another Paper",
        abstract="Focuses on retrieval augmented generation.",
        authors=["Bob"],
        year=2023,
        url="https://example.org/p2",
    )

    registry = ToolRegistry()
    registry.register(FakeKeywordExpansionTool())
    registry.register(FakeQuickSummaryTool())
    registry.register(FakeGlobalSummaryTool())
    registry.register(FakeFocusedSynthesisTool())

    agent = ConversationAgent(tool_registry=registry)
    agent.ingest_papers([sample_paper, second_paper])
    agent.start_session("session-workflow", initial_selection=["P1", "P2"])

    reply1 = agent.handle_message("session-workflow", "Please expand keyword LLM transformer.")
    reply2 = agent.handle_message("session-workflow", "Remove paper P2 from the list.")
    reply3 = agent.handle_message("session-workflow", "Could you summarize these papers?")
    reply4 = agent.handle_message("session-workflow", "Provide an overall summary of the selection.")
    reply5 = agent.handle_message("session-workflow", "Focus on the methodology of the remaining papers.")

    assert "Core terms" in reply1.text
    assert "Removed requested papers" in reply2.text
    assert reply3.text == "Here is the quick summary."
    assert reply4.text.startswith("Comprehensive synthesis")
    assert reply5.text.startswith("Focused insight about")
def test_search_extension_adds_new_papers(sample_paper: PaperSummary):
    registry = ToolRegistry()
    registry.register(FakeSearchExtensionTool())

    agent = ConversationAgent(tool_registry=registry)
    agent.ingest_papers([sample_paper])
    session = agent.start_session("session-search", initial_selection=["P1"], metadata={"history_id": 42})

    reply = agent.handle_message("session-search", "Please search for two more papers about evaluation.")

    assert "Retrieved" in reply.text
    assert session.selected_ids == ["P1", "P2"]
    assert reply.metadata.get("added_ids") == ["P2"]
