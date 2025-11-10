from __future__ import annotations

import concurrent.futures
import logging
import tempfile
import threading
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence
from urllib.parse import urlparse

import requests

try:  # pragma: no cover - optional dependency shim for local testing
    from docling.document import DocumentConverter
except ModuleNotFoundError:  # pragma: no cover
    class DocumentConverter:  # type: ignore
        def convert(self, path: str):  # pylint: disable=unused-argument
            raise ModuleNotFoundError(
                "Docling is not installed. Install it via requirements to enable PDF ingestion."
            )

from server.data_access.paper_repository import PaperRepository

logger = logging.getLogger(__name__)


def is_probably_pdf_url(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    path = (parsed.path or "").lower()
    host = (parsed.netloc or "").lower()
    if path.endswith(".pdf"):
        return True
    if host.endswith("arxiv.org") and "/pdf/" in path:
        return True
    return False


def _serialize_component(component) -> object:
    if component is None:
        return None
    if hasattr(component, "model_dump"):
        try:
            return component.model_dump()
        except Exception:  # pragma: no cover - defensive
            return str(component)
    if isinstance(component, dict):
        return component
    if hasattr(component, "__dict__"):
        try:
            return dict(component.__dict__)
        except Exception:  # pragma: no cover - defensive
            return str(component)
    return str(component)


class DoclingIngestionService:
    """
    Downloads PDFs and converts them to structured text using Docling.
    Results are stored via PaperRepository for downstream AI consumption.
    """

    def __init__(
        self,
        paper_repository: Optional[PaperRepository] = None,
        *,
        converter: Optional[DocumentConverter] = None,
        max_workers: int = 2,
        max_pdf_bytes: int = 25 * 1024 * 1024,
        downloader: Optional[Callable[[str], bytes]] = None,
    ) -> None:
        self._paper_repository = paper_repository or PaperRepository()
        self._converter = converter or DocumentConverter()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._max_pdf_bytes = max_pdf_bytes
        self._downloader = downloader or self._download_pdf
        self._inflight: set[str] = set()
        self._lock = threading.Lock()

    def enqueue_many(self, papers: Sequence[Dict]) -> None:
        for paper in papers:
            paper_id = paper.get("id") or paper.get("paper_id")
            pdf_url = paper.get("pdf_url")
            file_path = paper.get("cached_pdf_path")
            if not paper_id:
                continue
            self.enqueue(str(paper_id), pdf_url=str(pdf_url) if pdf_url else None, file_path=file_path)

    def enqueue(self, paper_id: str, pdf_url: Optional[str] = None, file_path: Optional[str] = None) -> None:
        if not file_path and not (pdf_url and is_probably_pdf_url(pdf_url)):
            logger.debug("Skipping ingestion for %s; invalid source", paper_id)
            return
        with self._lock:
            if paper_id in self._inflight:
                return
            self._inflight.add(paper_id)
        self._executor.submit(self._ingest_wrapper, paper_id, pdf_url, file_path)

    def ingest_pdf_now(self, paper_id: str, pdf_url: Optional[str] = None, file_path: Optional[str] = None) -> None:
        """Synchronous ingestion helper (useful for tests)."""
        self._ingest(paper_id, pdf_url, file_path)

    def _ingest_wrapper(self, paper_id: str, pdf_url: Optional[str], file_path: Optional[str]) -> None:
        try:
            self._ingest(paper_id, pdf_url, file_path)
        finally:
            with self._lock:
                self._inflight.discard(paper_id)

    def _ingest(self, paper_id: str, pdf_url: Optional[str], file_path: Optional[str]) -> None:
        try:
            if file_path and Path(file_path).exists():
                payload = self._convert_file(Path(file_path))
            elif pdf_url:
                pdf_bytes = self._downloader(pdf_url)
                payload = self._convert_bytes(pdf_bytes)
            else:
                logger.debug("No valid source for %s", paper_id)
                return
            self._paper_repository.upsert_fulltext(paper_id, payload)
            logger.info("Docling stored full text for %s", paper_id)
        except Exception as exc:  # pragma: no cover - failures logged for observability
            logger.warning("Docling ingestion failed for %s: %s", paper_id, exc)

    def _download_pdf(self, pdf_url: str) -> bytes:
        with requests.get(pdf_url, timeout=60, stream=True) as response:
            response.raise_for_status()
            content_type = (response.headers.get("Content-Type") or "").lower()
            if "pdf" not in content_type and not pdf_url.lower().endswith(".pdf"):
                raise ValueError(f"URL did not return a PDF (content-type={content_type})")
            data = bytearray()
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if not chunk:
                    continue
                data.extend(chunk)
                if len(data) > self._max_pdf_bytes:
                    raise ValueError(f"PDF exceeds {self._max_pdf_bytes // (1024 * 1024)}MB limit")
        return bytes(data)

    def _convert_bytes(self, pdf_bytes: bytes) -> Dict[str, object]:
        if not pdf_bytes:
            raise ValueError("Empty PDF payload")
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp.flush()
            temp_path = Path(tmp.name)
        try:
            return self._convert_file(temp_path)
        finally:
            try:
                temp_path.unlink()
            except OSError:
                pass

    def _convert_file(self, file_path: Path) -> Dict[str, object]:
        document = self._converter.convert(str(file_path))
        plain_text = getattr(document, "plain_text", "") or ""
        sections = []
        tables = []
        metadata = _serialize_component(getattr(document, "metadata", {})) or {}
        for section in getattr(document, "sections", []) or []:
            serialized = _serialize_component(section)
            if serialized:
                sections.append(serialized)
        for table in getattr(document, "tables", []) or []:
            serialized = _serialize_component(table)
            if serialized:
                tables.append(serialized)
        return {
            "plain_text": plain_text,
            "sections": sections,
            "tables": tables,
            "metadata": metadata,
        }
