from typing import Any, Dict, List


class RetrievalService:
    """Collects reference papers from arXiv and uploaded documents."""

    def __init__(self, arxiv_client: Any, document_store: Any) -> None:
        self._arxiv_client = arxiv_client
        self._document_store = document_store

    def fetch_references(self, plan_step: Dict[str, Any]) -> List[Dict[str, Any]]:
        # TODO: Query arXiv API and ingest uploaded PDFs
        raise NotImplementedError("Retrieval service integration pending")
