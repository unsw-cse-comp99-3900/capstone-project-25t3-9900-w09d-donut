from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, Iterable, Optional

import requests

logger = logging.getLogger(__name__)


class PDFCacheService:
    """Downloads PDF files and stores them under storage/pdf_cache."""

    def __init__(
        self,
        base_dir: str | Path = "storage/pdf_cache",
        *,
        session: Optional[requests.Session] = None,
        max_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._session = session or requests.Session()
        self._max_bytes = max_bytes

    def cache_many(self, papers: Iterable[Dict]) -> Dict[str, str]:
        cached: Dict[str, str] = {}
        for paper in papers:
            paper_id = paper.get("id") or paper.get("paper_id")
            pdf_url = paper.get("pdf_url")
            if not paper_id or not pdf_url:
                continue
            path = self.cache_pdf(str(paper_id), str(pdf_url))
            if path:
                cached[str(paper_id)] = path
        return cached

    def cache_pdf(self, paper_id: str, pdf_url: str) -> Optional[str]:
        safe_id = self._sanitize(paper_id)
        target = self._base_dir / f"{safe_id}.pdf"
        try:
            logger.debug("Caching PDF for %s from %s", paper_id, pdf_url)
            with self._session.get(pdf_url, timeout=60, stream=True) as response:
                response.raise_for_status()
                content_type = (response.headers.get("Content-Type") or "").lower()
                if "pdf" not in content_type and not pdf_url.lower().endswith(".pdf"):
                    logger.debug("Skipping non-PDF response for %s (content-type=%s)", paper_id, content_type)
                    return None
                with open(target, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 64):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        if handle.tell() > self._max_bytes:
                            raise ValueError("PDF exceeds cache size limit")
        except Exception as exc:  # pragma: no cover - networking
            logger.warning("Failed to cache PDF for %s: %s", paper_id, exc)
            if target.exists():
                try:
                    target.unlink()
                except OSError:
                    pass
            return None
        return str(target)

    @staticmethod
    def _sanitize(name: str) -> str:
        return "".join(ch for ch in name if ch.isalnum() or ch in ("-", "_")) or "paper"

