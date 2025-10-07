from typing import Any, Dict


class AgentGateway:
    """Thin wrapper that centralizes calls into the LangChain-based agents."""

    def __init__(self, planning_agent: Any, retrieval_agent: Any, doc_processor: Any, rag_agent: Any, refinement_module: Any) -> None:
        self._planning_agent = planning_agent
        self._retrieval_agent = retrieval_agent
        self._doc_processor = doc_processor
        self._rag_agent = rag_agent
        self._refinement_module = refinement_module

    def generate_plan(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: Call planning agent and normalize response structure
        raise NotImplementedError("Planning agent integration pending")

    def execute_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: Sequence retrieval, doc processing, and draft generation agents
        raise NotImplementedError("Execution pipeline integration pending")

    def refine_output(self, request_id: str, refinement_payload: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: Delegate refinement interactions to refinement module
        raise NotImplementedError("Refinement workflow integration pending")
