"""Minimal PDF builder for summary exports."""
from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_paragraphs(text: str, width: int = 90) -> List[str]:
    lines: List[str] = []
    for paragraph in text.splitlines():
        paragraph = paragraph.rstrip()
        if not paragraph:
            lines.append("")
            continue
        wrapped = textwrap.wrap(paragraph, width=width) or [paragraph]
        lines.extend(wrapped)
    if not lines:
        lines.append("")
    return lines


@dataclass
class SummaryPdfBuilder:
    output_dir: Path = Path("storage/summary_pdfs")

    def __post_init__(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_pdf(
        self,
        *,
        summary_text: str,
        citations: Iterable[str],
        session_id: str,
        summary_type: str,
        focus_aspect: Optional[str] = None,
    ) -> Path:
        filename = f"summary_{session_id}_{summary_type}"
        if focus_aspect:
            safe_focus = focus_aspect.replace(" ", "_")[:40]
            filename += f"_{safe_focus}"
        pdf_path = self.output_dir / f"{filename}.pdf"

        lines = ["Summary"]
        if focus_aspect:
            lines[0] = f"Summary - Focus: {focus_aspect}"
        lines.append("")
        lines.extend(_wrap_paragraphs(summary_text))

        citation_list = list(citations)
        if citation_list:
            lines.append("")
            lines.append("References:")
            for idx, cite in enumerate(citation_list, start=1):
                lines.extend(_wrap_paragraphs(f"{idx}. {cite}"))

        content_stream = self._build_stream(lines)
        pdf_bytes = self._compose_pdf(content_stream)
        pdf_path.write_bytes(pdf_bytes)
        return pdf_path

    def _build_stream(self, lines: List[str]) -> bytes:
        y = 760
        line_height = 14
        parts = ["BT", "/F1 12 Tf"]
        for line in lines:
            escaped = _escape(line)
            parts.append(f"1 0 0 1 50 {y} Tm ({escaped}) Tj")
            y -= line_height
            if y < 60:
                y = 760  # simple handling; overwrite if too long
        parts.append("ET")
        stream_text = "\n".join(parts) + "\n"
        return stream_text.encode("utf-8")

    def _compose_pdf(self, stream: bytes) -> bytes:
        objects = []

        def add(obj: str) -> None:
            if not obj.endswith("\n"):
                obj += "\n"
            objects.append(obj.encode("utf-8"))

        add("1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj")
        add("2 0 obj << /Type /Pages /Count 1 /Kids [3 0 R] >> endobj")
        add(
            "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj"
        )
        add("4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj")
        add(f"5 0 obj << /Length {len(stream)} >> stream\n" + stream.decode("utf-8") + "endstream endobj")

        pdf = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for obj in objects:
            offsets.append(len(pdf))
            pdf.extend(obj)

        xref_offset = len(pdf)
        pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode())
        pdf.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010d} 00000 n \n".encode())
        pdf.extend(b"trailer\n")
        pdf.extend(f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode())
        pdf.extend(f"startxref\n{xref_offset}\n%%EOF".encode())
        return bytes(pdf)
