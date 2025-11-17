from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from ai_agents.llm.gemini_client import GeminiClient, GeminiText


@dataclass
class GeneratedQuery:
    query: str
    focus: Optional[str] = None
    rationale: Optional[str] = None
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "focus": self.focus,
            "rationale": self.rationale,
            "keywords": list(self.keywords),
        }


@dataclass
class DeepResearchRound:
    round_index: int
    queries: List[Dict[str, Any]]
    findings: List[str]
    missing: List[str]
    sources: List[Dict[str, Any]]
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "round_index": self.round_index,
            "queries": self.queries,
            "findings": self.findings,
            "missing": self.missing,
            "sources": self.sources,
        }
        if self.notes:
            payload["notes"] = self.notes
        return payload

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "DeepResearchRound":
        return DeepResearchRound(
            round_index=int(data.get("round_index", 0)),
            queries=list(data.get("queries") or []),
            findings=list(data.get("findings") or []),
            missing=list(data.get("missing") or []),
            sources=list(data.get("sources") or []),
            notes=data.get("notes"),
        )


class DeepResearchAgent:
    """
    Lightweight controller that uses an LLM to manage deep research loops.
    It produces search queries, synthesizes round summaries, and builds final reports.
    """

    def __init__(
        self,
        llm: Optional[GeminiText] = None,
        *,
        max_docs_per_round: int = 8,
        max_chars_per_doc: int = 40000,
    ) -> None:
        self._llm = llm or GeminiClient().text
        self._max_docs = max_docs_per_round
        self._max_chars = max_chars_per_doc
        self._max_section_chars = max(600, max_chars_per_doc // 2)
        self._planning_tokens = 32768
        self._round_tokens = 32768
        self._report_tokens = 32768

    # ------------------------------------------------------------------ #
    # Query generation
    # ------------------------------------------------------------------ #
    def generate_queries(
        self,
        *,
        user_query: str,
        context: Sequence[Mapping[str, Any]],
        breadth: int = 3,
        language: str = "en",
        extra_instructions: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        breadth = max(1, min(int(breadth or 1), 6))
        context_text = _format_context(context)
        instruction_block = f"Additional guidance: {extra_instructions}" if extra_instructions else ""

        prompt = textwrap.dedent(
            f"""
            You are planning the next search round for a deep research investigation.

            Research question: {user_query.strip()}
            Prior findings and gaps:
            {context_text or 'No prior context available.'}

            Produce {breadth} diverse search ideas that build directly on the findings and missing knowledge above.
            Each idea should include the concrete query to run and the angle or hypothesis it addresses.
            Return strict JSON using this schema:
            {{
              "queries": [
                {{"query": "...", "focus": "...", "rationale": "...", "keywords": ["optional","tokens"]}}
              ],
              "notes": "optional planning comment"
            }}

            {instruction_block}
            Respond in {language}.
            """
        ).strip()

        raw = self._llm.chat(
            prompt,
            temperature=0.35,
            max_output_tokens=self._planning_tokens,
        )
        parsed = _extract_json_object(raw)
        queries_raw = parsed.get("queries") if isinstance(parsed, dict) else None

        queries: List[GeneratedQuery] = []
        if isinstance(queries_raw, list):
            for entry in queries_raw:
                query_text = str(entry.get("query") or "").strip()
                if not query_text:
                    continue
                keywords = entry.get("keywords") or []
                if isinstance(keywords, str):
                    keywords = [keywords]
                queries.append(
                    GeneratedQuery(
                        query=query_text,
                        focus=_maybe(entry.get("focus")),
                        rationale=_maybe(entry.get("rationale") or entry.get("reason")),
                        keywords=[str(k).strip() for k in keywords if str(k).strip()],
                    )
                )

        if not queries:
            fallback_lines = [
                line.strip(" -•\t")
                for line in (raw or "").splitlines()
                if line.strip(" -•\t")
            ]
            for line in fallback_lines[:breadth]:
                if not line:
                    continue
                queries.append(GeneratedQuery(query=line, keywords=[line]))

        return [q.to_dict() for q in queries[:breadth]]

    # ------------------------------------------------------------------ #
    # Round synthesis
    # ------------------------------------------------------------------ #
    def summarize_round(
        self,
        *,
        user_query: str,
        round_index: int,
        documents: Sequence[Mapping[str, Any]],
        queries: Sequence[Mapping[str, Any]],
        context: Sequence[Mapping[str, Any]],
        language: str = "en",
        instructions: Optional[str] = None,
    ) -> DeepResearchRound:
        if not documents:
            return DeepResearchRound(
                round_index=round_index,
                queries=[dict(q) for q in queries],
                findings=[],
                missing=["No documents were retrieved for this round."],
                sources=[],
                notes="Empty result set",
            )

        doc_blocks: List[str] = []
        doc_catalog: Dict[str, Dict[str, str]] = {}
        for idx, doc in enumerate(documents[: self._max_docs], start=1):
            doc_id = str(doc.get("id") or doc.get("paper_id") or idx)
            title = (doc.get("title") or doc.get("display_name") or f"Document {idx}").strip()
            snippet = (
                doc.get("full_text")
                or doc.get("summary")
                or doc.get("abstract")
                or ""
            ).strip()
            if len(snippet) > self._max_chars:
                snippet = snippet[: self._max_chars] + "..."
            url = (doc.get("link") or doc.get("url") or doc.get("pdf_url") or "").strip()
            doc_catalog[doc_id] = {"id": doc_id, "title": title, "url": url or ""}
            section_lines = _extract_section_lines(doc, self._max_section_chars)
            table_lines = _extract_table_lines(doc)
            block_lines = [
                f"[{doc_id}] Title: {title}",
                f"URL: {url or 'n/a'}",
                f"Summary: {snippet}",
            ]
            if section_lines:
                block_lines.append("Sections:")
                block_lines.extend(section_lines)
            if table_lines:
                block_lines.append("Tables:")
                block_lines.extend(table_lines)
            doc_blocks.append("\n".join(block_lines) + "\n")

        doc_section = "\n".join(doc_blocks)
        query_lines = [
            f"- {item.get('query')} ({item.get('focus') or 'general'})"
            for item in queries
        ]
        context_text = _format_context(context)
        instruction_block = f"User emphasis: {instructions}" if instructions else ""

        prompt = textwrap.dedent(
            f"""
            You just reviewed a batch of documents for a deep research investigation.
            Research question: {user_query.strip()}

            Recent search queries:
            {chr(10).join(query_lines) if query_lines else 'n/a'}

            Prior rounds summary:
            {context_text or 'This is the first round.'}

            Documents:
            {doc_section}

            Analyze the evidence and respond with JSON:
            {{
              "findings": [{{"statement": "...", "sources": ["doc_id"]}}],
              "missing": ["question we still need to investigate"],
              "sources": [{{"id": "doc_id", "title": "...", "url": "...", "reason": "why it matters"}}],
              "notes": "optional reflection"
            }}

            Requirements:
            - Findings must be grounded in the provided documents.
            - Include at least one gap or open question.
            - Prefer concise language.
            {instruction_block}
            Respond in {language}.
            """
        ).strip()

        raw = self._llm.chat(
            prompt,
            temperature=0.3,
            max_output_tokens=self._round_tokens,
        )
        parsed = _extract_json_object(raw)

        findings_payload = []
        for item in (parsed.get("findings") or []) if isinstance(parsed, dict) else []:
            if isinstance(item, str):
                findings_payload.append(item.strip())
            elif isinstance(item, Mapping):
                statement = str(item.get("statement") or item.get("summary") or "").strip()
                if statement:
                    findings_payload.append(statement)

        missing_payload = []
        for item in (parsed.get("missing") or []) if isinstance(parsed, dict) else []:
            if isinstance(item, str):
                missing_payload.append(item.strip())
            elif isinstance(item, Mapping):
                text = str(item.get("question") or item.get("gap") or "").strip()
                if text:
                    missing_payload.append(text)

        source_entries: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()

        if isinstance(parsed, dict):
            for item in parsed.get("sources") or []:
                if not isinstance(item, Mapping):
                    continue
                doc_id = str(item.get("id") or item.get("paper_id") or "").strip()
                if not doc_id:
                    continue
                meta = doc_catalog.get(doc_id)
                if not meta:
                    continue
                if doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)
                source_entries.append(
                    {
                        "id": doc_id,
                        "title": meta["title"],
                        "url": meta["url"],
                        "reason": _maybe(item.get("reason") or item.get("focus")),
                    }
                )

        if not source_entries:
            for doc_id, meta in list(doc_catalog.items())[:3]:
                if doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)
                source_entries.append(meta)

        notes = parsed.get("notes") if isinstance(parsed, dict) else None

        return DeepResearchRound(
            round_index=round_index,
            queries=[dict(q) for q in queries],
            findings=findings_payload,
            missing=missing_payload,
            sources=source_entries,
            notes=_maybe(notes),
        )

    # ------------------------------------------------------------------ #
    # Final report
    # ------------------------------------------------------------------ #
    def build_report(
        self,
        *,
        user_query: str,
        rounds: Sequence[Mapping[str, Any]],
        instructions: Optional[str] = None,
        language: str = "en",
    ) -> Dict[str, Any]:
        context_text = _format_context(rounds, include_sources=True)
        instruction_block = f"User preferences: {instructions}" if instructions else ""

        prompt = textwrap.dedent(
            f"""
            Produce a final research memo synthesizing the investigation below.

            Research question: {user_query.strip()}
            Investigation rounds:
            {context_text or 'Only a single round of context is available.'}

            Respond with JSON only using this schema:
            {{
              "title": "Research Memo: ...",
              "overview": "Summary paragraph",
              "refinement": "optional clarification of how the question evolved",
              "key_findings": [
                {{"statement": "...", "insight": "optional elaboration", "sources": ["id"]}}
              ],
              "evidence": [
                {{"finding": "...", "implication": "...", "sources": ["id"]}}
              ],
              "open_questions": ["question..."],
              "next_steps": ["recommended action..."],
              "notes": "optional commentary"
            }}

            Requirements:
            - Draw on the round summaries and cite sources using their IDs.
            - Keep prose concise but informative.
            {instruction_block}

            Respond in {language}.
            """
        ).strip()

        result = self._llm.chat(
            prompt,
            temperature=0.35,
            max_output_tokens=self._report_tokens,
        )
        parsed = _extract_json_object(result)
        if not isinstance(parsed, Mapping):
            return {
                "title": "Research Memo",
                "overview": result.strip() or "No summary was generated.",
                "refinement": None,
                "key_findings": [],
                "evidence": [],
                "open_questions": [],
                "next_steps": [],
                "notes": None,
            }

        def _as_list(value: Any) -> List[Any]:
            if isinstance(value, list):
                return value
            if value is None:
                return []
            return [value]

        key_findings: List[Dict[str, Any]] = []
        for entry in _as_list(parsed.get("key_findings")):
            if not isinstance(entry, Mapping):
                continue
            statement = _maybe(entry.get("statement"))
            if not statement:
                continue
            key_findings.append(
                {
                    "statement": statement,
                    "insight": _maybe(entry.get("insight") or entry.get("details")),
                    "sources": [
                        str(src).strip()
                        for src in _as_list(entry.get("sources"))
                        if str(src).strip()
                    ],
                }
            )

        evidence_rows: List[Dict[str, Any]] = []
        for entry in _as_list(parsed.get("evidence")):
            if not isinstance(entry, Mapping):
                continue
            finding = _maybe(entry.get("finding"))
            implication = _maybe(entry.get("implication") or entry.get("impact"))
            if not finding and not implication:
                continue
            evidence_rows.append(
                {
                    "finding": finding,
                    "implication": implication,
                    "sources": [
                        str(src).strip()
                        for src in _as_list(entry.get("sources"))
                        if str(src).strip()
                    ],
                }
            )

        return {
            "title": _maybe(parsed.get("title")) or "Research Memo",
            "overview": _maybe(parsed.get("overview")) or "",
            "refinement": _maybe(parsed.get("refinement")),
            "key_findings": key_findings,
            "evidence": evidence_rows,
            "open_questions": [
                str(item).strip()
                for item in _as_list(parsed.get("open_questions"))
                if str(item).strip()
            ],
            "next_steps": [
                str(item).strip()
                for item in _as_list(parsed.get("next_steps"))
                if str(item).strip()
            ],
            "notes": _maybe(parsed.get("notes")),
        }


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
def _extract_json_object(payload: str) -> Dict[str, Any]:
    payload = (payload or "").strip()
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        pass

    start = payload.find("{")
    end = payload.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = payload[start : end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            return {}
    return {}


def _format_context(context: Sequence[Mapping[str, Any]], *, include_sources: bool = False) -> str:
    if not context:
        return ""
    lines: List[str] = []
    for item in context:
        round_label = item.get("round_index") or len(lines) + 1
        findings = item.get("findings") or []
        missing = item.get("missing") or []
        lines.append(f"Round {round_label}:")
        for entry in findings:
            lines.append(f"  - Finding: {entry}")
        for gap in missing:
            lines.append(f"  - Gap: {gap}")
        if include_sources and item.get("sources"):
            src_lines = ", ".join(
                f"[{src.get('id')}] {src.get('title')}"
                for src in item["sources"][:5]
            )
            if src_lines:
                lines.append(f"  - Sources: {src_lines}")
    return "\n".join(lines)


def _maybe(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _extract_section_lines(doc: Mapping[str, Any], limit: int) -> List[str]:
    sections = doc.get("sections") or doc.get("structured_sections") or []
    if isinstance(sections, Mapping):
        sections = list(sections.values())
    lines: List[str] = []
    if not isinstance(sections, Sequence):
        return lines
    for section in sections[:2]:
        if not isinstance(section, Mapping):
            continue
        heading = (
            section.get("heading")
            or section.get("title")
            or section.get("name")
            or "Section"
        )
        text = (
            section.get("text")
            or section.get("content")
            or section.get("body")
            or ""
        )
        text_str = str(text).strip()
        if not text_str:
            continue
        if len(text_str) > limit:
            text_str = text_str[:limit] + "..."
        lines.append(f"  - {heading}: {text_str}")
    return lines


def _extract_table_lines(doc: Mapping[str, Any]) -> List[str]:
    tables = doc.get("tables") or []
    if isinstance(tables, Mapping):
        tables = list(tables.values())
    lines: List[str] = []
    if not isinstance(tables, Sequence):
        return lines
    for table in tables[:2]:
        if not isinstance(table, Mapping):
            continue
        caption = (
            table.get("caption")
            or table.get("title")
            or table.get("name")
            or "Table"
        )
        lines.append(f"  - {caption}")
    return lines
