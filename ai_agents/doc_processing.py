from typing import Any, Dict, Iterable


class DocumentProcessor:
    """Normalizes documents and creates embeddings for downstream retrieval."""

    def __init__(self, embedding_model: Any, vector_store: Any) -> None:
        self._embedding_model = embedding_model
        self._vector_store = vector_store

    def process_documents(self, documents: Iterable[Dict[str, Any]]) -> None:
        # TODO: Chunk documents, compute embeddings, and upsert into ChromaDB
        raise NotImplementedError("Document processing not implemented")
