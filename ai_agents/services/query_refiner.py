"""
Keyword refinement and expansion tools for search orchestration.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

from ai_agents.llm.gemini_client import GeminiError, GeminiText

from .tooling import AgentTool, ToolContext, ToolExecutionError, ToolResult


@dataclass
class RefineQueryRequest:
    keywords: List[str]
    domain: str = "ml"
    max_terms: int = 8
    language: str = "en"
    conversation_notes: Optional[str] = None
    system_prompt: Optional[str] = None


@dataclass
class RefineQueryResult:
    must_terms: List[str]
    should_terms: List[str]
    filters: Dict[str, str]
    final_query_openalex: str
    rationale: str
    filters_diff: Dict[str, str] = field(default_factory=dict)
    explanations: List[str] = field(default_factory=list)


class QueryRefiner:
    """
    Curate and expand user-provided keywords into a better search query.
    Produces a simple OpenAlex 'search' string.
    """

    def __init__(self, text_client: Optional[GeminiText] = None):
        self.text = text_client or GeminiText()

    def refine(self, req: RefineQueryRequest) -> RefineQueryResult:
        prompt = self._build_prompt(req)

        try:
            raw = self.text.chat(prompt, temperature=0.2, max_output_tokens=512)
            data = _safe_json_parse(raw)
        except GeminiError:
            data = {}

        must_terms = _as_list_str(data.get("must_terms"))
        should_terms = _as_list_str(data.get("should_terms"))
        filters = data.get("filters") or {}
        rationale = (data.get("rationale", "") or "").strip()
        explanations = _as_list_str(data.get("explanations"))
        openalex_query = data.get("openalex_query") or " ".join(must_terms + should_terms)

        if not must_terms and not should_terms:
            fallback_terms = _fallback_keywords(req.keywords)
            must_terms = fallback_terms
            rationale = rationale or "Fallback deterministic keyword curation applied."

        return RefineQueryResult(
            must_terms=must_terms,
            should_terms=should_terms,
            filters=filters,
            final_query_openalex=openalex_query.strip(),
            rationale=rationale,
            filters_diff={},
            explanations=explanations,
        )

    def _build_prompt(self, req: RefineQueryRequest) -> str:
        base_prompt = """
You are a research assistant. Curate and refine the following keywords for literature search.

Input keywords: {req.keywords}
Domain: {req.domain}
Language: {req.language}
Max curated terms: {req.max_terms}

Return only valid JSON with fields:
- must_terms: array of <= {req.max_terms} canonical terms (lowercase, no duplicates)
- should_terms: array of optional booster terms (<= {max(0, req.max_terms - 3)})
- filters: object with optional keys year_from, year_to, venue, concept (strings)
- openalex_query: a single string for the OpenAlex 'search' parameter (space-separated)
- rationale: one concise sentence
- explanations: array of short notes (<= 3 items) for applied changes

Constraints:
- Merge synonyms (e.g., "moe" -> "mixture of experts").
- Prefer terms that reduce ambiguity.
- If no filter is appropriate, return an empty object.
- Keep output deterministic and concise.
        """.strip()

        system_note = f"System: {req.system_prompt.strip()}\n\n" if req.system_prompt else ""
        conversation_note = ""
        if req.conversation_notes:
            conversation_note = f"Recent context: {req.conversation_notes.strip()}\n\n"
        return f"{system_note}{conversation_note}{base_prompt}".strip()


def _fallback_keywords(keywords: List[str]) -> List[str]:
    seen = set()
    results: List[str] = []
    for kw in keywords:
        normalized = kw.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        results.append(normalized)
    return results[:10]


class KeywordExpansionTool(AgentTool):
    name: str = "keyword_expansion"

    def __init__(self, refiner: Optional[QueryRefiner] = None) -> None:
        self._refiner = refiner or QueryRefiner()

    def execute(self, context: ToolContext, payload: Mapping[str, object]) -> ToolResult:
        raw_keywords = payload.get("keywords")
        if not raw_keywords:
            raise ToolExecutionError("No keywords supplied for refinement", code="missing_keywords")

        req = RefineQueryRequest(
            keywords=[str(kw) for kw in raw_keywords if str(kw).strip()],
            domain=str(payload.get("domain") or "ml"),
            max_terms=int(payload.get("max_terms", 8)),
            language=str(payload.get("language") or "en"),
            conversation_notes=context.memory_snapshot.generated_artifacts.get("conversation_summary"),
            system_prompt=payload.get("system_prompt"),
        )
        result = self._refiner.refine(req)

        snapshot = context.memory_snapshot
        previous_filters = snapshot.active_filters.get("search_filters", {})
        if isinstance(previous_filters, dict):
            diff = {
                key: value
                for key, value in result.filters.items()
                if previous_filters.get(key) != value
            }
        else:
            diff = dict(result.filters)
        result.filters_diff = diff

        metadata = {
            "must_terms": result.must_terms,
            "should_terms": result.should_terms,
            "filters": result.filters,
            "filters_diff": result.filters_diff,
            "final_query": result.final_query_openalex,
            "rationale": result.rationale,
            "explanations": result.explanations,
        }

        return ToolResult(
            text="Keywords refined successfully.",
            citations=[],
            selected_ids=[],
            metadata=metadata,
        )


# ---------- small JSON helper ----------
def _safe_json_parse(s: str) -> dict:
    try:
        return json.loads(s)
    except Exception:
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(s[start : end + 1])
            except Exception:
                pass
    return {}


def _as_list_str(x) -> List[str]:
    if not x:
        return []
    if isinstance(x, list):
        return [str(i).strip() for i in x if str(i).strip()]
    return [str(x).strip()]
