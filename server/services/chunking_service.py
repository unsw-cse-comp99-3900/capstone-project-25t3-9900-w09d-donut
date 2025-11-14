from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Sequence

from server.data_access.paper_repository import PaperRepository

logger = logging.getLogger(__name__)


class TextChunkingService:
    """Splits stored article text into manageable chunks for downstream LLM usage."""

    def __init__(
        self,
        *,
        paper_repository: Optional[PaperRepository] = None,
        max_chunk_chars: int = 1800,
        min_chunk_chars: int = 600,
    ) -> None:
        self._repo = paper_repository or PaperRepository()
        self._max_chunk_chars = max(400, max_chunk_chars)
        self._min_chunk_chars = max(200, min_chunk_chars)

    def build_chunks(self, paper_id: str, payload: Dict[str, object]) -> None:
        if not paper_id:
            return
        entries = self._linearize_sections(payload.get("structured_sections"))
        if not entries:
            entries = self._entries_from_plain_text(str(payload.get("plain_text") or ""))
        if not entries:
            logger.debug("No content available to chunk for %s", paper_id)
            self._repo.replace_chunks(paper_id, [])
            return

        normalized: List[Dict[str, object]] = []
        for entry in entries:
            normalized.extend(self._split_entry(entry))

        chunks = self._accumulate(normalized)
        self._repo.replace_chunks(paper_id, chunks)
        logger.info("Stored %s chunk(s) for %s", len(chunks), paper_id)

    def _linearize_sections(self, structured: object) -> List[Dict[str, object]]:
        entries: List[Dict[str, object]] = []
        if not isinstance(structured, dict):
            return entries
        for bucket, sections in structured.items():
            if not isinstance(sections, Sequence):
                continue
            for section in sections:
                text = self._extract_text(section)
                if not text:
                    continue
                entries.append(
                    {
                        "bucket": str(bucket),
                        "heading": self._extract_heading(section),
                        "text": text,
                    }
                )
        return entries

    def _entries_from_plain_text(self, text: str) -> List[Dict[str, object]]:
        text = (text or "").strip()
        if not text:
            return []
        paragraphs = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
        if not paragraphs:
            paragraphs = [text]
        entries = [{"bucket": "plain_text", "heading": None, "text": para} for para in paragraphs]
        return entries

    def _split_entry(self, entry: Dict[str, object]) -> List[Dict[str, object]]:
        text = str(entry.get("text") or "").strip()
        if len(text) <= self._max_chunk_chars:
            return [entry]

        segments: List[Dict[str, object]] = []
        buffer = ""
        for paragraph in [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]:
            candidate = paragraph if not buffer else f"{buffer}\n\n{paragraph}"
            if len(candidate) > self._max_chunk_chars and buffer:
                segments.append({**entry, "text": buffer})
                buffer = paragraph
            else:
                buffer = candidate
        if buffer:
            segments.append({**entry, "text": buffer})
        if not segments:
            segments.append({**entry, "text": text})

        normalized: List[Dict[str, object]] = []
        for segment in segments:
            normalized.extend(self._slice(segment))
        return normalized

    def _slice(self, segment: Dict[str, object]) -> List[Dict[str, object]]:
        text = str(segment.get("text") or "")
        if len(text) <= self._max_chunk_chars:
            return [segment]
        slices: List[Dict[str, object]] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + self._max_chunk_chars)
            slice_text = text[start:end].strip()
            if slice_text:
                slices.append({**segment, "text": slice_text})
            start = end
        return slices or [segment]

    def _accumulate(self, entries: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
        chunks: List[Dict[str, object]] = []
        buffer: List[Dict[str, object]] = []
        buffer_chars = 0
        chunk_index = 0
        for entry in entries:
            text = str(entry.get("text") or "").strip()
            if not text:
                continue
            length = len(text)
            if buffer and buffer_chars + length > self._max_chunk_chars and buffer_chars >= self._min_chunk_chars:
                chunks.append(self._flush(chunk_index, buffer))
                chunk_index += 1
                buffer = []
                buffer_chars = 0
            buffer.append(entry)
            buffer_chars += length
        if buffer:
            chunks.append(self._flush(chunk_index, buffer))
        return chunks

    def _flush(self, chunk_index: int, buffer: Sequence[Dict[str, object]]) -> Dict[str, object]:
        text = "\n\n".join(str(entry.get("text") or "").strip() for entry in buffer if entry.get("text"))
        text = text.strip()
        token_estimate = len(text.split())
        primary = buffer[0] if buffer else {}
        metadata = {
            "sections": [
                {"bucket": entry.get("bucket"), "heading": entry.get("heading")}
                for entry in buffer
            ]
        }
        return {
            "chunk_index": chunk_index,
            "section_label": primary.get("bucket"),
            "heading": primary.get("heading"),
            "text": text,
            "token_estimate": token_estimate,
            "metadata": metadata,
        }

    @staticmethod
    def _extract_text(section: object) -> str:
        if isinstance(section, dict):
            text = section.get("text") or section.get("content") or section.get("raw") or ""
            return str(text).strip()
        return str(section or "").strip()

    @staticmethod
    def _extract_heading(section: object) -> Optional[str]:
        if isinstance(section, dict):
            heading = section.get("title") or section.get("heading") or section.get("label")
            if heading:
                return str(heading).strip()
        return None
