from __future__ import annotations

import concurrent.futures
import logging
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence
from urllib.parse import urlparse

import requests

try:  # pragma: no cover - optional fallback dependency
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None

try:  # pragma: no cover - prefer new API
    from docling.document_converter import DocumentConverter  # type: ignore
except ModuleNotFoundError:
    try:
        from docling.document import DocumentConverter  # type: ignore
    except ModuleNotFoundError:
        DocumentConverter = None  # type: ignore

from server.data_access.paper_repository import PaperRepository
from .chunking_service import TextChunkingService

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
        enable_docling: bool = True,
        chunking_service: Optional["TextChunkingService"] = None,
    ) -> None:
        self._paper_repository = paper_repository or PaperRepository()
        self._converter = None
        if converter is not None:
            self._converter = converter
            self._enable_docling = True
        else:
            self._enable_docling = enable_docling and DocumentConverter is not None
            if self._enable_docling:
                try:
                    self._converter = DocumentConverter()  # type: ignore[call-arg]
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("Docling converter unavailable (%s); falling back to PyMuPDF only.", exc)
                    self._converter = None
                    self._enable_docling = False
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._max_pdf_bytes = max_pdf_bytes
        self._downloader = downloader or self._download_pdf
        self._chunking_service = chunking_service
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
            if self._chunking_service:
                try:
                    self._chunking_service.build_chunks(paper_id, payload)
                except Exception as chunk_exc:  # pragma: no cover
                    logger.warning("Chunking failed for %s: %s", paper_id, chunk_exc)
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
        if not self._enable_docling or not self._converter:
            return self._extract_plain_payload(file_path)

        conversion = self._converter.convert(str(file_path))
        document = getattr(conversion, "document", None)
        if document is None:
            documents = getattr(conversion, "documents", None) or []
            if documents:
                document = documents[0]
        if document is None:
            logger.warning("Docling conversion produced no document, using PyMuPDF fallback.")
            return self._extract_plain_payload(file_path)

        sections_serialized, section_chunks = self._serialize_sections(document)
        structured_sections = self._structure_sections(sections_serialized)
        tables_serialized = self._serialize_tables(document)
        metadata = _serialize_component(getattr(document, "metadata", {})) or {}

        plain_text = getattr(document, "plain_text", "") or ""
        fallback_used: List[str] = []
        if not plain_text and section_chunks:
            plain_text = "\n\n".join(section_chunks)
            fallback_used.append("sections")

        if not plain_text:
            plain_text = self._collect_block_text(document)
            if plain_text:
                fallback_used.append("blocks")

        if not plain_text:
            plain_text = self._extract_with_pymupdf(file_path)
            if plain_text:
                fallback_used.append("pymupdf")

        if fallback_used:
            metadata = dict(metadata)
            metadata["extraction_fallback"] = fallback_used

        return {
            "plain_text": plain_text or "",
            "sections": sections_serialized,
            "tables": tables_serialized,
            "metadata": metadata,
            "structured_sections": structured_sections,
        }

    def _extract_plain_payload(self, file_path: Path) -> Dict[str, object]:
        plain_text = self._extract_with_pymupdf(file_path)
        metadata = {"extraction_mode": "pymupdf"}
        if not plain_text:
            raise ValueError("Unable to extract text via PyMuPDF")
        return {
            "plain_text": plain_text,
            "sections": [],
            "tables": [],
            "metadata": metadata,
            "structured_sections": {},
        }

    def _serialize_sections(self, document) -> tuple[List[object], List[str]]:
        serialized: List[object] = []
        chunks: List[str] = []
        for section in getattr(document, "sections", []) or []:
            payload = _serialize_component(section)
            if payload is None:
                continue
            serialized.append(payload)
            text = ""
            if isinstance(payload, dict):
                text = str(payload.get("text") or payload.get("content") or "")
            else:
                text = str(payload)
            text = text.strip()
            if text:
                chunks.append(text)
        return serialized, chunks

    def _serialize_tables(self, document) -> List[object]:
        serialized: List[object] = []
        for table in getattr(document, "tables", []) or []:
            payload = _serialize_component(table)
            if payload:
                serialized.append(payload)
        return serialized

    def _structure_sections(self, sections: List[object]) -> Dict[str, List[Dict[str, object]]]:
        buckets: Dict[str, List[Dict[str, object]]] = OrderedDict(
            [
                ("abstract", []),
                ("introduction", []),
                ("methods", []),
                ("results", []),
                ("discussion", []),
                ("conclusion", []),
                ("references", []),
                ("other", []),
            ]
        )
        current_key = "other"
        KEYWORDS = OrderedDict(
            [
                ("abstract", ("abstract", "summary")),
                ("introduction", ("introduction", "background")),
                ("methods", ("method", "approach", "experimental", "materials")),
                ("results", ("result", "finding", "analysis")),
                ("discussion", ("discussion", "insight")),
                ("conclusion", ("conclusion", "future work")),
                ("references", ("reference", "bibliography", "citation")),
            ]
        )

        for section in sections:
            if isinstance(section, dict):
                title = (section.get("title") or section.get("heading") or "").lower()
            else:
                title = str(section).lower()
            matched = next((key for key, kws in KEYWORDS.items() if any(kw in title for kw in kws)), None)
            if matched:
                current_key = matched
            buckets[current_key].append(section if isinstance(section, dict) else {"raw": section})
        return buckets

    def _collect_block_text(self, document) -> str:
        chunks: List[str] = []
        for page in getattr(document, "pages", []) or []:
            for block in getattr(page, "blocks", []) or []:
                text = getattr(block, "text", "") or ""
                text = text.strip()
                if text:
                    chunks.append(text)
        return "\n\n".join(chunks)

    def _extract_with_pymupdf(self, file_path: Path) -> str:
        if fitz is None:
            return ""
        try:
            doc = fitz.open(str(file_path))
        except Exception:  # pragma: no cover - file issues
            return ""
        chunks: List[str] = []
        for page in doc:
            text = page.get_text("text") or ""
            text = text.strip()
            if text:
                chunks.append(text)
        doc.close()
        return "\n\n".join(chunks)
