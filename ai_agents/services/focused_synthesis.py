"""
Focused synthesis tool that generates aspect-specific summaries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .models import PaperSummary
from .summarizer import PaperSummarizer, SummarizeRequest
from .tooling import AgentTool, ToolContext, ToolResult


@dataclass
class FocusedSynthesisTool(AgentTool):
    name: str = "focused_synthesis"
    summarizer: PaperSummarizer = field(default_factory=PaperSummarizer)

    def execute(self, context: ToolContext, payload: Mapping[str, object]) -> ToolResult:
        focus = str(payload.get("focus") or payload.get("focus_aspect") or "the requested aspect")
        papers = payload.get("papers") or []
        if not papers:
            return ToolResult(
                text="No papers available for focused synthesis.",
                citations=[],
                selected_ids=payload.get("selected_ids") or [],
            )

        req = SummarizeRequest(
            papers=list(papers),
            user_goal=str(payload.get("user_goal") or f"Synthesize findings focused on: {focus}"),
            style=str(payload.get("style") or "paragraph"),
            include_citations=True,
            mode="focused",
            focus_aspect=focus,
            language=str(payload.get("language") or "en"),
        )
        result = self.summarizer.summarize(req)
        return ToolResult(
            text=result.text,
            citations=result.citations,
            selected_ids=payload.get("selected_ids") or [],
            metadata={
                "used_count": result.used_count,
                "prompt_tokens": result.prompt_tokens_estimate,
                "citations_map": result.citations_map,
            },
        )

    @staticmethod
    def select_papers(target_ids: Sequence[str], catalogue: Mapping[str, PaperSummary]) -> list[PaperSummary]:
        return [catalogue[pid] for pid in target_ids if pid in catalogue]
