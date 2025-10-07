from typing import Any, Dict, Iterable, Optional


class ResearchRepository:
    """Handles persistence for research requests and artifacts."""

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    def create_request(self, payload: Dict[str, Any]) -> str:
        # TODO: Map payload to ORM entity and commit transaction
        raise NotImplementedError("create_request not implemented")

    def save_plan(self, request_id: str, plan: Dict[str, Any]) -> None:
        # TODO: Persist plan structure for auditing and replay
        raise NotImplementedError("save_plan not implemented")

    def save_draft(self, request_id: str, draft: Dict[str, Any]) -> None:
        # TODO: Store generated draft content and metadata
        raise NotImplementedError("save_draft not implemented")

    def list_requests(self) -> Iterable[Dict[str, Any]]:
        # TODO: Yield summarized request records ordered by recency
        raise NotImplementedError("list_requests not implemented")

    def get_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        # TODO: Retrieve full request context for downstream consumption
        raise NotImplementedError("get_request not implemented")
