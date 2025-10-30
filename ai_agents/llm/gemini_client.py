# ai_agents/llm/gemini_client.py
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import requests
from requests import Response

logger = logging.getLogger(__name__)


# --------------------------
# REST endpoints (v1beta)
# --------------------------
_GEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_EMB_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"

# Default model names (stable + validated)
_DEFAULT_TEXT_MODEL = "gemini-2.0-flash"
_DEFAULT_EMB_MODEL = "text-embedding-004"


# --------------------------
# Error / retry primitives
# --------------------------
@dataclass
class RetryConfig:
    max_attempts: int = 3
    backoff_factor: float = 1.6
    retry_statuses: Tuple[int, ...] = (408, 429, 500, 502, 503, 504)


class GeminiError(RuntimeError):
    def __init__(self, message: str, *, status_code: Optional[int] = None, payload: Optional[Dict] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


def _default_session_factory() -> requests.Session:
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=0)  # manual retries
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _post(
    url: str,
    api_key: str,
    payload: Dict,
    *,
    timeout: int = 60,
    retry: Optional[RetryConfig] = None,
    session_factory: Callable[[], requests.Session] = _default_session_factory,
) -> Dict:
    """POST to Google Generative Language REST API with retry + richer errors."""

    retry = retry or RetryConfig()
    session = session_factory()
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "x-goog-api-key": api_key,
    }

    attempt = 0
    last_error: Optional[Exception] = None

    while attempt < retry.max_attempts:
        attempt += 1
        try:
            resp: Response = session.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
        except requests.RequestException as exc:
            last_error = exc
            logger.warning("Gemini HTTP error on attempt %s: %s", attempt, exc)
            if attempt >= retry.max_attempts:
                raise GeminiError("Gemini HTTP request failed", payload={"error": str(exc)}) from exc
            sleep_for = retry.backoff_factor ** (attempt - 1)
            time.sleep(sleep_for)
            continue

        if resp.status_code // 100 == 2:
            return resp.json()

        # non-2xx handling
        try:
            data = resp.json()
        except ValueError:
            data = {"error": {"code": resp.status_code, "message": resp.text}}

        if resp.status_code in retry.retry_statuses and attempt < retry.max_attempts:
            sleep_for = retry.backoff_factor ** (attempt - 1)
            logger.info("Retrying Gemini call (%s) after status %s (sleep %.2fs)", attempt, resp.status_code, sleep_for)
            time.sleep(sleep_for)
            last_error = GeminiError("Gemini REST error", status_code=resp.status_code, payload=data)
            continue

        raise GeminiError(
            f"Gemini REST error: {json.dumps(data, ensure_ascii=False)}",
            status_code=resp.status_code,
            payload=data,
        )

    raise GeminiError("Gemini request failed after retries", payload={"last_error": str(last_error) if last_error else None})


# --------------------------
# Text generation client
# --------------------------
@dataclass
class GeminiText:
    """
    Lightweight text-generation client for Gemini REST API.
    """

    api_key: Optional[str] = None
    model: str = _DEFAULT_TEXT_MODEL
    system_prompt: Optional[str] = None
    timeout: int = 60  # seconds
    retry: RetryConfig = field(default_factory=RetryConfig)
    session_factory: Callable[[], requests.Session] = _default_session_factory

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set")

    def _prepare_prompt(self, prompt: str) -> str:
        if not self.system_prompt:
            return prompt
        return f"{self.system_prompt.strip()}\n\nUser:\n{prompt}"

    def chat(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_output_tokens: int = 1024,
        candidate_count: int = 1,
    ) -> str:
        prompt_text = self._prepare_prompt(prompt)
        url = _GEN_URL.format(model=self.model)
        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "candidateCount": candidate_count,
            },
        }
        data = _post(
            url,
            self.api_key,
            payload,
            timeout=self.timeout,
            retry=self.retry,
            session_factory=self.session_factory,
        )

        candidates = data.get("candidates") or []
        if not candidates:
            return ""
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return parts[0].get("text", "") if parts else ""

    def chat_multi_candidate(
        self,
        prompt: str,
        *,
        n: int = 3,
        temperature: float = 0.8,
        max_output_tokens: int = 1024,
    ) -> List[str]:
        prompt_text = self._prepare_prompt(prompt)
        url = _GEN_URL.format(model=self.model)
        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "candidateCount": max(1, int(n)),
            },
        }
        data = _post(
            url,
            self.api_key,
            payload,
            timeout=self.timeout,
            retry=self.retry,
            session_factory=self.session_factory,
        )
        outs: List[str] = []
        for cand in data.get("candidates") or []:
            parts = (cand.get("content") or {}).get("parts") or []
            outs.append(parts[0].get("text", "") if parts else "")
        return outs


# --------------------------
# Embeddings client
# --------------------------
@dataclass
class GeminiEmbeddings:
    """
    Embedding client for Gemini REST API.
    """

    api_key: Optional[str] = None
    model: str = _DEFAULT_EMB_MODEL
    timeout: int = 60  # seconds
    l2_normalize: bool = True
    retry: RetryConfig = field(default_factory=RetryConfig)
    session_factory: Callable[[], requests.Session] = _default_session_factory

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set")

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        vecs: List[np.ndarray] = []
        url = _EMB_URL.format(model=self.model)
        for t in texts:
            payload = {"content": {"parts": [{"text": str(t)}]}}
            data = _post(
                url,
                self.api_key,
                payload,
                timeout=self.timeout,
                retry=self.retry,
                session_factory=self.session_factory,
            )
            emb = (data.get("embedding") or {}).get("values")
            if emb is None:
                emb = (
                    (data.get("embeddings") or [{}])[0].get("values")
                    if data.get("embeddings")
                    else None
                )
            if emb is None:
                raise GeminiError("Invalid embedding response", payload=data)

            v = np.asarray(emb, dtype=np.float32)
            if self.l2_normalize:
                norm = np.linalg.norm(v)
                if norm > 0:
                    v = v / norm
            vecs.append(v)

        return np.vstack(vecs) if vecs else np.zeros((0, 0), dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        matrix = self.embed_texts([text])
        return matrix[0] if matrix.size else matrix


# --------------------------
# Tiny convenience façade
# --------------------------
@dataclass
class GeminiClient:
    """
    Optional façade combining text + embeddings clients with shared configuration.
    """

    api_key: Optional[str] = None
    text_model: str = _DEFAULT_TEXT_MODEL
    emb_model: str = _DEFAULT_EMB_MODEL
    timeout: int = 60
    retry: RetryConfig = field(default_factory=RetryConfig)
    session_factory: Callable[[], requests.Session] = _default_session_factory

    def __post_init__(self) -> None:
        key = self.api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY is not set")
        self.text = GeminiText(
            api_key=key,
            model=self.text_model,
            timeout=self.timeout,
            retry=self.retry,
            session_factory=self.session_factory,
        )
        self.emb = GeminiEmbeddings(
            api_key=key,
            model=self.emb_model,
            timeout=self.timeout,
            retry=self.retry,
            session_factory=self.session_factory,
        )
