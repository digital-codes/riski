import os
import time
import base64
import json
import logging
from typing import Any, Dict, List

import requests
import numpy as np

# ----------------------------------------------------------------------
# Configuration – resolution order: private.py -> env var -> local default
# ----------------------------------------------------------------------


def _load_private():
    try:
        import src.private as pr

        return pr
    except Exception:
        return None


_pr = _load_private()


def _get(attr: str, env_key: str, default: str = "") -> str:
    """Env first, then private.py, then default — a second instance never
    needs an edited source file (change: instance-agnostic-config)."""
    value = os.getenv(env_key)
    if value:
        return value
    if _pr is not None:
        value = getattr(_pr, attr, None)
        if value:
            return value
    return default


def _get_first(pairs, default: str = "") -> str:
    """First non-empty value across (private_attr, env_key) pairs.

    Supports the older local-config naming (``LLM_MDL``/``LLM_URL``)
    alongside the current ``SUMMARY_MDL``/``SUMMARY_URL`` names so a
    deployment's private.py works regardless of which generation it
    was written for."""
    for attr, env_key in pairs:
        value = _get(attr, env_key)
        if value:
            return value
    return default


CHAT_BASE_URL = _get_first(
    [("SUMMARY_URL", "CHAT_BASE_URL"), ("LLM_URL", "LLM_URL")],
    "http://localhost:8080/v1",
)
CHAT_MODEL = _get_first(
    [("SUMMARY_MDL", "CHAT_MODEL"), ("LLM_MDL", "LLM_MDL")],
    "granite-4.1-3b-Q8_0",
)
CHAT_API_KEY = _get_first(
    [("SUMMARY_KEY", "CHAT_API_KEY"), ("LLM_KEY", "LLM_KEY")],
    "",
)

EMBED_BASE_URL = _get("EMB_URL", "EMBED_BASE_URL", "http://localhost:8085/v1")
EMBED_MODEL = _get("EMB_MDL", "EMBED_MODEL", "bge-m3-Q4_K_M")
EMBED_DIM = int(_get("EMB_DIM", "EMBED_DIM", os.getenv("EMBED_DIM", "1024")))
EMBED_API_KEY = _get("EMB_KEY", "EMBED_API_KEY", "")

OCR_URL = _get("OCR_URL", "OCR_URL", "https://api.mistral.ai/v1/ocr")
OCR_KEY = _get("OCR_KEY", "OCR_KEY", "")
OCR_MDL = _get("OCR_MDL", "OCR_MDL", "mistral-ocr-latest")



def _make_logger() -> logging.Logger:
    logger = logging.getLogger(__name__)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


_logger = _make_logger()

_DUMMY_CHAT_RESPONSE = {
    "choices": [{"message": {"content": "[dummy response]"}}],
    "usage": {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    },
}


def _post(
    path: str,
    json_body: Dict[str, Any],
    timeout: int = 90,
    base_url: str | None = None,
    api_key: str | None = None,
) -> Dict[str, Any]:
    """POST *json_body* to an OpenAI-compatible endpoint with retries.

    Retries transient failures up to ``REMOTE_MAX_RETRIES`` (default 3) with
    exponential back-off, honouring ``Retry-After`` on HTTP 429. Raises on the
    final failure; no dummy response is ever returned.
    """
    if base_url is None:
        base_url = CHAT_BASE_URL if path.startswith("chat") else EMBED_BASE_URL
    if api_key is None:
        api_key = CHAT_API_KEY if path.startswith("chat") else EMBED_API_KEY
    # Accept both a base URL (``.../v1``) and a full endpoint URL
    # (``.../v1/embeddings`` or ``.../v1/chat/completions``) as configured:
    # only append the path when the base URL does not already end with it.
    endpoint = path.lstrip("/")
    url = base_url.rstrip("/")
    if not url.endswith("/" + endpoint):
        url = f"{url}/{endpoint}"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    max_retries = int(os.getenv("REMOTE_MAX_RETRIES", "3"))
    base_delay = float(os.getenv("REMOTE_BASE_DELAY", "1.0"))

    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=json_body, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            last_exc = e
            if attempt >= max_retries:
                break
            delay = base_delay * (2 ** (attempt - 1))
            response = getattr(e, "response", None)
            retry_after = response.headers.get("Retry-After") if response is not None else None
            if retry_after and retry_after.isdigit():
                delay = float(retry_after)
            _logger.warning(
                "Remote request to %s failed (%s); retry %d/%d in %.1fs",
                url, e, attempt, max_retries - 1, delay,
            )
            time.sleep(delay)

    # surface the endpoint's own error text — without it a 400 from
    # ollama/llama.cpp is undebuggable (which field? why?)
    detail = ""
    response = getattr(last_exc, "response", None)
    if response is not None:
        try:
            detail = f" | response: {response.text[:500]}"
        except Exception:  # noqa: BLE001
            pass
    raise RuntimeError(
        f"Remote request to {url} failed after {max_retries} attempts "
        f"({last_exc}){detail}"
    ) from last_exc


def _coerce_temperature(value) -> float:
    """Coerce *value* to a float for the chat payload.

    Ollama (and strict OpenAI-compatible endpoints) reject the request with
    a 400 when ``temperature`` arrives as a string — e.g. when it comes
    from a string-typed config value. Garbage values fall back to 0.0
    (deterministic) rather than failing the call."""
    try:
        return float(value)
    except (TypeError, ValueError):
        _logger.warning("Invalid temperature %r; falling back to 0.0", value)
        return 0.0


def chat(
    messages: List[Dict[str, str]],
    model: str | None = None,
    temperature: float = 0.0,
    thinking: bool = False,
) -> Dict[str, Any]:
    """Call the chat completion endpoint.

    Returns a dictionary with the assistant's ``content`` and optional token
    usage fields. As a last resort (e.g. offline tests) a dummy response with
    ``content="[dummy response]"`` is returned.
    """
    payload = {
        "model": model or CHAT_MODEL,
        "temperature": _coerce_temperature(temperature),
        "messages": messages,
    }
    if thinking:
        payload["think"] = True

    try:
        data = _post("chat/completions", payload)
    except RuntimeError as e:
        # "think" is an ollama-native-API field; some OpenAI-compatible
        # endpoints reject the whole request over it with a 400. Retry
        # once without the optional field before giving up.
        if thinking:
            _logger.warning(
                "Chat request failed with optional fields (%s); "
                "retrying without 'think'", e,
            )
            payload.pop("think", None)
            try:
                data = _post("chat/completions", payload)
            except RuntimeError as e2:
                _logger.warning("Chat request failed (%s); returning dummy response", e2)
                data = _DUMMY_CHAT_RESPONSE
        else:
            _logger.warning("Chat request failed (%s); returning dummy response", e)
            data = _DUMMY_CHAT_RESPONSE
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = data.get("usage", {})
    return {
        "content": content,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        # verbatim for provenance/footers; None when the endpoint omits them
        "model": data.get("model"),
        "usage": usage or None,
        "impact": data.get("impact"),  # energy/emissions when the endpoint reports them
        "endpoint": CHAT_BASE_URL,
    }



def embed(text: str, model: str | None = None, dimensions: int | None = None) -> np.ndarray:
    """Obtain a normalised embedding vector for *text*.

    Returns a ``np.ndarray`` of shape ``(dim,)``. Raises on endpoint failure;
    no fabricated vector is ever returned.
    """
    payload = {
        "model": model or EMBED_MODEL,
        "input": [text[:8100]],  # limit length to typical service limits
        "dimensions": dimensions or EMBED_DIM,
    }
    data = _post("embeddings", payload)
    vec = data["data"][0]["embedding"]
    arr = np.array(vec, dtype=np.float64)
    norm = np.linalg.norm(arr) + 1e-9
    return arr / norm


def embed_batch(texts: list, model: str | None = None,
                dimensions: int | None = None) -> list:
    """Normalised embeddings for a batch of texts in ONE API call.

    Preserves input order (sorted by the API's ``index`` field). Raises on
    endpoint failure; no fabricated vector is ever returned.
    """
    payload = {
        "model": model or EMBED_MODEL,
        "input": [t[:8100] for t in texts],
        "dimensions": dimensions or EMBED_DIM,
    }
    data = _post("embeddings", payload)
    out: list = [None] * len(texts)
    for item in data["data"]:
        arr = np.array(item["embedding"], dtype=np.float64)
        norm = np.linalg.norm(arr) + 1e-9
        out[item.get("index", 0)] = arr / norm
    return out


def ocr(document: bytes | str, model: str | None = None,
        pages: str | list[int] | None = None) -> Dict[str, Any]:
    """Perform OCR on a PDF.

    *document* may be raw PDF bytes or a filesystem path. *pages* limits
    processing to specific pages — a string like ``"0-11"`` or a list of
    page numbers (0-based, Mistral OCR ``pages`` parameter). Sends a base64
    encoded document to the configured OCR endpoint and returns the parsed
    JSON result. HTTP 429 responses are retried honouring ``Retry-After``,
    up to 8 attempts.
    """
    if isinstance(document, (bytes, bytearray)):
        file_data = bytes(document)
    else:
        with open(document, "rb") as f:
            file_data = f.read()
    base64_file = base64.b64encode(file_data).decode("utf-8")
    payload = {
        "document": {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{base64_file}",
        },
        "model": model or OCR_MDL,
        "include_image_base64": True,
    }
    if pages is not None:
        payload["pages"] = pages
    headers = {"Content-Type": "application/json"}
    if OCR_KEY:
        headers["Authorization"] = f"Bearer {OCR_KEY}"

    max_retries = 8
    base_delay = 1.0
    attempt = 0
    while True:
        response = requests.post(OCR_URL, headers=headers, data=json.dumps(payload), timeout=120)
        if response.status_code != 429:
            break
        attempt += 1
        if attempt >= max_retries:
            break
        retry_after = response.headers.get("Retry-After")
        delay = float(retry_after) if retry_after and retry_after.isdigit() else base_delay * (2 ** (attempt - 1))
        _logger.warning("OCR rate limited (429); retry %d/%d in %.1fs", attempt, max_retries - 1, delay)
        time.sleep(delay)
    response.raise_for_status()
    return response.json()
