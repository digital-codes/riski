"""Ollama-bounded model client for the kg pipeline.

Deliberately ignores the endpoint configuration from ``src/private.py``
(model endpoints section) — the spec pins version 1 of the prototype to
the local ollama instance. ``--endpoint`` (default ``"ollama"``) keeps
the door open for future named endpoints without touching code.

Models (docs/kg_building.md):
* language models: ``granite4.2:8b``, ``qwen3.5:4b``, ``mistral:latest``
* embedding model: ``bge-m3:latest``
* decision model:  ``d3:2b``
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import requests

ENDPOINTS: dict[str, str] = {
    "ollama": "http://localhost:11434/v1",
}

# context budget per chat call — ollama keeps the whole KV cache in VRAM
# while the model is hot; a full-80k default crowd-outs smaller models.
# 16384 is enough for the ≤-12k-char document bodies of kgStatements
# (task 5). Override per call via num_ctx.
DEFAULT_NUM_CTX = 16384

LANGUAGE_MODELS = ["granite4.2:8b", "qwen3.5:4b", "mistral:latest"]
EMBEDDING_MODEL = "bge-m3:latest"
DECISION_MODEL = "d3:2b"


class KgRemote:
    """Minimal OpenAI-compatible chat/embed client for one endpoint."""

    def __init__(
        self,
        endpoint: str = "ollama",
        timeout: float = 120.0,
        num_ctx: int = DEFAULT_NUM_CTX,
    ):
        if endpoint not in ENDPOINTS:
            raise ValueError(
                f"unknown endpoint '{endpoint}'; known: {sorted(ENDPOINTS)}"
            )
        self.base_url = ENDPOINTS[endpoint]
        # native (non-OpenAI) root for /api/chat with options
        self.native_base = self.base_url[:-len("/v1")] if self.base_url.endswith("/v1") else self.base_url
        self.endpoint_name = endpoint
        self.timeout = timeout
        self.num_ctx = num_ctx
        self._available_models: list[str] | None = None

    # ------------------------------------------------------------------
    def available_models(self) -> list[str]:
        """List models the endpoint reports (cached per instance)."""
        if self._available_models is None:
            r = requests.get(f"{self.base_url}/models", timeout=self.timeout)
            r.raise_for_status()
            self._available_models = [
                m["id"] for m in r.json().get("data", [])
            ]
        return self._available_models

    def check_models(self, models: list[str]) -> dict[str, bool]:
        """Return which of *models* are available (accessibility check)."""
        have = set(self.available_models())
        return {m: m in have for m in models}

    # ------------------------------------------------------------------
    def native_chat(
        self,
        messages: list[dict[str, str]],
        model: str = DECISION_MODEL,
        temperature: float = 0.0,
        num_ctx: int | None = None,
        json_mode: bool = False,
        retries: int = 3,
    ) -> str:
        """Chat via ollama's native /api/chat (options.num_ctx bounded).

        The OpenAI-compatible v1 endpoint does not accept ``options``,
        which is why the timestamped KV-runner would keep a giant
        context in VRAM; the native call carries
        ``options: {num_ctx}`` explicitly.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_ctx": num_ctx or self.num_ctx,
                "temperature": temperature,
            },
        }
        if json_mode:
            payload["format"] = "json"
        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                r = requests.post(
                    f"{self.native_base}/api/chat",
                    json=payload,
                    timeout=self.timeout,
                )
                if r.status_code == 429:
                    time.sleep(int(r.headers.get("Retry-After", 5)))
                    last_err = RuntimeError("429 rate limited")
                    continue
                r.raise_for_status()
                return r.json()["message"]["content"]
            except (requests.RequestException, KeyError) as exc:  # noqa: PERF203
                last_err = exc
                time.sleep(2 * attempt)
        raise RuntimeError(
            f"native_chat failed after {retries} attempts: {last_err}"
        )

    def unload(self, model: str) -> None:
        """Free the KV-runner (keep_alive=0) — fixes a stuck huge ctx."""
        try:
            requests.post(
                f"{self.native_base}/api/generate",
                json={"model": model, "keep_alive": 0},
                timeout=self.timeout,
            )
        except requests.RequestException:
            pass

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str = DECISION_MODEL,
        temperature: float = 0.0,
        retries: int = 3,
    ) -> str:
        """Send a chat completion and return the assistant text."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                r = requests.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=self.timeout,
                )
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", 5))
                    time.sleep(wait)
                    last_err = RuntimeError("429 rate limited")
                    continue
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            except (requests.RequestException, KeyError) as exc:  # noqa: PERF203
                last_err = exc
                time.sleep(2 * attempt)
        raise RuntimeError(f"chat failed after {retries} attempts: {last_err}")

    def embed(self, text: str, model: str = EMBEDDING_MODEL) -> list[float]:
        """Embed one text; returns the model's default-dim vector."""
        r = requests.post(
            f"{self.base_url}/embeddings",
            json={"model": model, "input": text},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]

    # ------------------------------------------------------------------
    def chat_json(
        self,
        messages: list[dict[str, str]],
        model: str = DECISION_MODEL,
        temperature: float = 0.0,
        num_ctx: int | None = None,
    ) -> dict[str, Any]:
        """Native chat with format=json; falls back to brace extraction."""
        raw = self.native_chat(
            messages,
            model=model,
            temperature=temperature,
            num_ctx=num_ctx,
            json_mode=True,
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"model did not return JSON: {raw[:200]}")
