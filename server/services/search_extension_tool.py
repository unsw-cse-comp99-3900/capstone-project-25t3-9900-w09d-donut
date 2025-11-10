from __future__ import annotations

from typing import Iterable, List, Mapping, Optional, Sequence

from ai_agents.services.tooling import AgentTool, ToolContext, ToolResult

from server.services.academic_search import AcademicSearchService


class SearchExtensionTool(AgentTool):
    """
    Tool that performs an additional OpenAlex search and appends the results to the
    existing search history linked to the active conversation.
    """

    name = "search_extension"

    def __init__(self, search_service: AcademicSearchService) -> None:
        self._search_service = search_service

    def execute(self, context: ToolContext, payload: Mapping[str, object]) -> ToolResult:
        keywords = self._coerce_keywords(payload.get("keywords"))
        if not keywords:
            return ToolResult(
                text="No keywords were provided for the search extension.",
                selected_ids=payload.get("selected_ids") or [],
                metadata={"error": "missing_keywords"},
            )

        history_id = payload.get("history_id") or context.extras.get("history_id")
        if history_id is None:
            return ToolResult(
                text="Search extension requires an active search history.",
                selected_ids=payload.get("selected_ids") or [],
                metadata={"error": "missing_history"},
            )
        try:
            history_id_int = int(history_id)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return ToolResult(
                text="Invalid history identifier supplied for search extension.",
                selected_ids=payload.get("selected_ids") or [],
                metadata={"error": "invalid_history_id"},
            )

        limit = self._coerce_limit(payload.get("limit"))
        existing_ids = set(self._coerce_iterable(payload.get("existing_ids")))

        date_range = self._coerce_date_range(payload.get("date_range"))
        concepts = self._coerce_iterable(payload.get("concepts"))

        try:
            new_results = self._search_service.search_and_append(
                history_id_int,
                keywords=keywords,
                date_range=date_range,
                concepts=concepts,
                limit=limit,
            )
        except Exception as exc:  # pragma: no cover - defensive
            return ToolResult(
                text="Search extension failed due to an upstream error.",
                selected_ids=payload.get("selected_ids") or [],
                metadata={"error": "search_failed", "details": str(exc)},
            )

        filtered = [item for item in new_results if (item.get("id") or item.get("paper_id")) not in existing_ids]
        if not filtered:
            return ToolResult(
                text="No additional papers were found for the requested keywords.",
                selected_ids=payload.get("selected_ids") or [],
                metadata={"papers": [], "keywords": keywords, "limit": limit},
            )

        return ToolResult(
            text=f"Retrieved {len(filtered)} additional paper(s) and added them to the selection.",
            selected_ids=payload.get("selected_ids") or [],
            metadata={"papers": filtered, "keywords": keywords, "limit": limit},
        )

    @staticmethod
    def _coerce_keywords(value: object) -> List[str]:
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, Iterable):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @staticmethod
    def _coerce_limit(value: object) -> int:
        try:
            limit = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            limit = 3
        return max(1, min(limit, 25))

    @staticmethod
    def _coerce_iterable(value: object) -> Sequence[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, Iterable):
            return [str(item) for item in value]
        return []

    @staticmethod
    def _coerce_date_range(value: object) -> Optional[tuple[str, str]]:
        if isinstance(value, Mapping):
            start = value.get("start")
            end = value.get("end")
            if start and end:
                return str(start), str(end)
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            start, end = value[0], value[1]
            if start and end:
                return str(start), str(end)
        return None
