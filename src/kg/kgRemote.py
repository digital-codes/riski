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

from src.remote import log_llm_call, validate_call_ids

ENDPOINTS: dict[str, str] = {
    "ollama": "http://localhost:11434/v1",
    # ollama cloud (OLC_* in src/private.py): OpenAI-compatible chat for
    # extraction, SystemOne route for decision verdicts
    "olc": "https://ollama.com/v1",
}

CLOUD_CONFIG_ATTRS = {
    "olc": {
        "base_url": "OLC_SUMMARY_URL",
        "chat_key": "OLC_SUMMARY_KEY",
        "chat_model": "OLC_SUMMARY_MDL",     # cheaper than OLC_LLM (user decision 2026-11-18)
        "summary_url": "OLC_SUMMARY_URL",
        "summary_model": "OLC_SUMMARY_MDL",
        "summary_key": "OLC_SUMMARY_KEY",
        # decision verdicts: greenpt metis (SYSONE_* in private.py) —
        # same protocol, half the OLC_SYSONE cost, verified equal
        # direction behaviour on live pairs (2026-11-18)
        "sysone_url": "SYSONE_URL",
        "sysone_model": "SYSONE_MDL",
        "sysone_key": "SYSONE_KEY",
    },
    # dedicated cross-check/failure-diagnose model (CCLLM_* in
    # private.py; operator-added 2026-11-19) — deliberately separate
    # from the extraction chat model: the diagnose call needs a
    # reason-generating discriminator, not the extractor.
    "ccllm": {
        "base_url": "CCLLM_URL",
        "chat_key": "CCLLM_KEY",
        # accept both spellings (the attribute was renamed once)
        "chat_model": "CCLLM_MDL",
    },
    "hf": {
        "base_url": "HF_SUMMARY_URL",
        "chat_key": "HF_SUMMARY_KEY",
        "chat_model": "HF_SUMMARY_MDL",
    },
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
        chat_model: str | None = None,
    ):
        if endpoint not in ENDPOINTS and endpoint not in CLOUD_CONFIG_ATTRS:
            raise ValueError(
                f"unknown endpoint '{endpoint}'; known: "
                f"{sorted(set(ENDPOINTS) | set(CLOUD_CONFIG_ATTRS))}"
            )
        self.endpoint_name = endpoint
        self._cloud = CLOUD_CONFIG_ATTRS.get(endpoint)
        if self._cloud:
            import src.private as pr

            self.base_url = getattr(pr, self._cloud["base_url"], "")
            # OpenAI-compatible base (strip trailing route)
            self._chat_url = self.base_url
            self._chat_key = getattr(pr, self._cloud["chat_key"], "") or ""
            self._chat_model = chat_model or getattr(
                pr, self._cloud["chat_model"], ""
            )
            self._sysone_url = getattr(pr, self._cloud.get("sysone_url", ""), None) if self._cloud.get("sysone_url") else None
            self._sysone_model = getattr(pr, self._cloud.get("sysone_model", ""), None) if self._cloud.get("sysone_model") else None
            self._sysone_key = getattr(pr, self._cloud.get("sysone_key", ""), "") or ""
            self.native_base = None
        else:
            self.base_url = ENDPOINTS[endpoint]
            self.native_base = (
                self.base_url[:-len("/v1")] if self.base_url.endswith("/v1") else self.base_url
            )
            self._chat_url = None
            self._chat_key = ""
            self._chat_model = chat_model
            self._sysone_url = None
            self._sysone_model = None
            self._sysone_key = ""
        self.timeout = timeout
        self.num_ctx = num_ctx
        self._available_models: list[str] | None = None

    @classmethod
    def for_diagnose(cls, override_model: str | None = None) -> "KgRemote | None":
        """Dedicated diagnose client — reads CCLLM_* (operator session).

        Returns None while the private attributes are absent, so the
        callers can fall back to the generic cloud chat.
        """
        import src.private as pr

        if not getattr(pr, "CCLLM_URL", None):
            return None
        r = cls("ccllm")
        if override_model:
            r._chat_model = override_model
        return r

    # ------------------------------------------------------------------
    def available_models(self) -> list[str]:
        """List models the endpoint reports (cached per instance).

        Cloud endpoints: the chat endpoint URL already carries the route
        (…/chat/completions) → ask /models at the origin with auth.
        """
        if self._available_models is None:
            if self._cloud:
                origin = self.base_url.split("/v1")[0] or "https://ollama.com"
                r = requests.get(
                    f"{origin}/v1/models",
                    headers={"Authorization": f"Bearer {self._chat_key}"} if self._chat_key else {},
                    timeout=self.timeout,
                )
                r.raise_for_status()
            else:
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
        prompt_id: str | None = None,
        call_id: str | None = None,
    ) -> str:
        """Chat via ollama's native /api/chat (options.num_ctx bounded).

        The OpenAI-compatible v1 endpoint does not accept ``options``,
        which is why the timestamped KV-runner would keep a giant
        context in VRAM; the native call carries
        ``options: {num_ctx}`` explicitly.

        Identifying calls are recorded in ``log/llm_debug.log`` for log
        continuity with the OpenAI-compatible route — no enforcement of
        the registry ids here (the /api/chat route is outside the
        prompt-registry scope)."""
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
        t0 = time.perf_counter()
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
                data = r.json()
                if prompt_id or call_id:
                    log_llm_call(
                        endpoint=f"{self.native_base}/api/chat", model=model,
                        payload=payload, result=data,
                        prompt_id=prompt_id, call_id=call_id,
                        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                    )
                return data["message"]["content"]
            except (requests.RequestException, KeyError) as exc:  # noqa: PERF203
                last_err = exc
                time.sleep(2 * attempt)
        if prompt_id or call_id:
            log_llm_call(
                endpoint=f"{self.native_base}/api/chat", model=model,
                payload=payload, result=None, status="error",
                prompt_id=prompt_id, call_id=call_id,
                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                error=f"native_chat failed after {retries} attempts: {last_err}",
            )
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
        model: str | None = None,
        temperature: float = 0.0,
        retries: int = 3,
        prompt_id: str | None = None,
        call_id: str | None = None,
    ) -> str:
        """Send a chat completion and return the assistant text.

        Cloud endpoints (`olc`/`hf`): the endpoint URL already carries
        the /chat/completions route and the Authorization header carries
        the OLC_*/HF_* key.

        The call is identified by ``prompt_id``/
        ``call_id`` per the prompt registry (change:
        centralize-llm-instruction-prompts): missing ids are flagged as
        errors (or refused in ``REMOTE_PROMPT_ENFORCE=strict`` mode) and
        the full request/result is recorded in ``log/llm_debug.log``."""
        prompt_id, call_id = validate_call_ids(
            prompt_id, call_id, context="kg.KgRemote.chat",
        )
        payload: dict[str, Any] = {
            "model": model or self._chat_model or DECISION_MODEL,
            "messages": messages,
            "temperature": temperature,
        }
        if self._cloud:
            headers = {"Authorization": f"Bearer {self._chat_key}"} if self._chat_key else {}
            url = (
                self._chat_url
                if str(self._chat_url).rstrip("/").endswith("chat/completions")
                else f"{str(self._chat_url).rstrip('/')}/chat/completions"
            )
        else:
            url = f"{self.base_url}/chat/completions"
            headers = {}
        t0 = time.perf_counter()
        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                r = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", 5))
                    time.sleep(wait)
                    last_err = RuntimeError("429 rate limited")
                    continue
                r.raise_for_status()
                data = r.json()
                log_llm_call(
                    endpoint=url, model=payload["model"], payload=payload,
                    result=data, prompt_id=prompt_id, call_id=call_id,
                    duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                )
                return data["choices"][0]["message"]["content"]
            except (requests.RequestException, KeyError) as exc:  # noqa: PERF203
                last_err = exc
                time.sleep(2 * attempt)
        log_llm_call(
            endpoint=url, model=payload["model"], payload=payload, result=None,
            status="error", prompt_id=prompt_id, call_id=call_id,
            duration_ms=round((time.perf_counter() - t0) * 1000, 1),
            error=f"chat failed after {retries} attempts: {last_err}",
        )
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

    def systemone(
        self,
        state: str,
        questions: dict[str, dict],
        model: str = DECISION_MODEL,
        timeout: float = 90.0,
        prompt_id: str | None = None,
        call_id: str | None = None,
    ) -> dict[str, dict]:
        """SystemOne decision protocol (ollama /v1/systemone).

        d3:2b supports ONLY this route (noul/choice/score questions);
        returns ``{"answers": {name: {"noul": 0..1} | {"choice": ...}}}``.

        Identified like every other prompt-bearing call (change:
        centralize-llm-instruction-prompts) — the full state/questions
        payload and the returned answers go to ``log/llm_debug.log``."""
        prompt_id, call_id = validate_call_ids(
            prompt_id, call_id, context="kg.KgRemote.systemone",
        )
        url = self._sysone_url or f"{self.base_url}/systemone"
        mdl = self._sysone_model or model
        headers = {"Authorization": f"Bearer {self._sysone_key}"} if self._sysone_key else {}
        body = {"model": mdl, "state": state, "questions": questions}
        # retry/backoff: the tagger and the inline crosscheck share the
        # decision endpoint — 429s are routine, not fatal
        t0 = time.perf_counter()
        last_err = None
        for attempt in range(1, 4):
            try:
                r = requests.post(
                    url,
                    json=body,
                    headers=headers,
                    timeout=timeout,
                )
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", 5 * attempt))
                    time.sleep(wait)
                    last_err = RuntimeError("429 rate limited")
                    continue
                r.raise_for_status()
                answers = r.json().get("answers", {})
                log_llm_call(
                    endpoint=url, model=mdl, payload=body, result=answers,
                    prompt_id=prompt_id, call_id=call_id,
                    duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                )
                return answers
            except (requests.RequestException, KeyError) as exc:
                last_err = exc
                time.sleep(3 * attempt)
        log_llm_call(
            endpoint=url, model=mdl, payload=body, result=None, status="error",
            prompt_id=prompt_id, call_id=call_id,
            duration_ms=round((time.perf_counter() - t0) * 1000, 1),
            error=f"systemone failed after retries: {last_err}",
        )
        raise RuntimeError(f"systemone failed after retries: {last_err}")

    # ------------------------------------------------------------------
    def chat_json(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
        num_ctx: int | None = None,
        prompt_id: str | None = None,
        call_id: str | None = None,
    ) -> dict[str, Any]:
        """JSON chat; native format=json locally, plain chat for cloud.

        Identifying ids are validated here once (the registry policy) and
        forwarded to the underlying route, which records the call."""
        prompt_id, call_id = validate_call_ids(
            prompt_id, call_id, context="kg.KgRemote.chat_json",
        )
        raw = (
            self.chat(messages, model=model, temperature=temperature,
                      prompt_id=prompt_id, call_id=call_id)
            if self._cloud
            else self.native_chat(
                messages,
                model=model or DECISION_MODEL,
                temperature=temperature,
                num_ctx=num_ctx,
                json_mode=True,
                prompt_id=prompt_id,
                call_id=call_id,
            )
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"model did not return JSON: {raw[:200]}")
