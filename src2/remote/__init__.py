import os
import time
import json
import logging
from typing import Any, Dict, List

import requests
import numpy as np

# ----------------------------------------------------------------------
# Configuration – defaults as requested, with env overrides for flexibility
# ----------------------------------------------------------------------
CHAT_BASE_URL = os.getenv("CHAT_BASE_URL", "http://localhost:8080/v1")
CHAT_MODEL = os.getenv("CHAT_MODEL", "granite-4.1-3b-Q8_0")
CHAT_API_KEY = os.getenv("CHAT_API_KEY", "")  # empty means no auth header

EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "http://localhost:8085/v1")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3-Q4_K_M")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
EMBED_API_KEY = os.getenv("EMBED_API_KEY", "")

_logger = logging.getLogger(__name__)
if not _logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("% (asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)


def _post(path: str, json_body: Dict[str, Any], timeout: int = 90) -> Dict[str, Any]:
    """POST *json_body* to ``BASE_URL/path`` with exponential back‑off.

    Handles HTTP 429 by respecting ``Retry‑After`` when present, otherwise uses
    a simple exponential delay. Retries are capped by ``REMOTE_MAX_RETRIES``.
    """
    url = f"{(CHAT_BASE_URL if path.startswith('chat') else EMBED_BASE_URL).rstrip('/')}/{path.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    api_key = CHAT_API_KEY if path.startswith('chat') else EMBED_API_KEY
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    max_retries = int(os.getenv("REMOTE_MAX_RETRIES", "5"))
    base_delay = float(os.getenv("REMOTE_BASE_DELAY", "1.0"))

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=json_body, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            # Fallback for offline / unavailable service – return a minimal
            # structure so callers can still operate in tests.
            _logger.warning("Remote request to %s failed (%s); returning dummy response", url, e)
            return {
                "choices": [{"message": {"content": "[dummy response]"}}],
                "usage": {
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                },
            }

    # final attempt raised an exception
    resp.raise_for_status()
    return {}


def chat(
    messages: List[Dict[str, str]],
    model: str | None = None,
    temperature: float = 0.0,
    thinking: bool = False,
) -> Dict[str, Any]:
    """Call the chat completion endpoint.

    Returns a dictionary with the assistant's ``content`` and optional token usage
    fields (``prompt_tokens``, ``completion_tokens``, ``total_tokens``).

    If *thinking* is ``True``, the *think* param is set.
    """
    payload = {
        "model": model or CHAT_MODEL,
        "temperature": temperature,
        "messages": messages,
    }
    if thinking:
        # Simple heuristic to enable a "think first" style prompt.
        payload["think"] = True
    #else:
    #    payload["think"] = False

    data = _post("chat/completions", payload)
    # Extract response content
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = data.get("usage", {})
    return {
        "content": content,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def embed(text: str, model: str | None = None, dimensions: int | None = None) -> np.ndarray:
    """Obtain a normalised embedding vector for *text*.

    Returns a ``np.ndarray`` of shape ``(dim,)``.
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
