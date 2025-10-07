from typing import Any, Dict


class RAGAgent:
    """Generates drafts by combining vector search results with an LLM."""

    def __init__(self, llm_chain: Any, vector_store: Any) -> None:
        self._llm_chain = llm_chain
        self._vector_store = vector_store

    def generate_draft(self, request_context: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: Retrieve relevant chunks and produce structured draft output
        raise NotImplementedError("RAG pipeline not implemented")
