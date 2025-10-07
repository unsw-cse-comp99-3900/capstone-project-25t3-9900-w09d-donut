from typing import Any, Dict


class PlanningAgent:
    """Produces a step-by-step execution outline for a research request."""

    def __init__(self, llm_client: Any) -> None:
        self._llm_client = llm_client

    def generate_plan(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: Implement structured prompt and call LangChain pipeline
        raise NotImplementedError("Planning agent integration pending")
