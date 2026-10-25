"""Per-client sliding-window rate limiting (change: api-security-hardening).

The API is unauthenticated and inference-expensive: `/ask`, `/summarize`
and `/search?summarize=true` trigger LLM calls against a configured
(possibly paid) endpoint. This module bounds what one client can inflict:

- **Client identity**: the socket address, or the last hop of
  `X-Forwarded-For` when the peer address is in the trusted-proxy range
  (`RISKI_TRUSTED_PROXIES`, default `127.0.0.1`). A spoofed header from a
  non-proxy peer is ignored.
- **Groups**: `llm` (LLM-triggering endpoints, enforced by the middleware)
  and `search` (cheap endpoints). `/health` is exempt (monitoring).
  `/search` counts in the `search` group by middleware; when a search
  request triggers an inline summary (`summarize=true`), the endpoint
  additionally enforces the `llm` budget via
  :func:`llm_budget_for_search` before any work.
- **Mechanism**: per-(client, group) deque of timestamps inside a sliding
  window; 429 + `Retry-After` before any work is done when the group
  limit is exceeded. In-process (single-worker deployment); resets on
  restart — this is cost bounding, not billing.
"""

import os
import time
import threading
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

DEFAULT_LLM_LIMIT = 10          # requests per window for LLM-triggering endpoints
DEFAULT_SEARCH_LIMIT = 60       # requests per window for the cheap endpoints
DEFAULT_WINDOW_SECONDS = 60

LLM_PATHS = {"/ask", "/summarize"}
EXEMPT_PATHS = {"/health", "/health/"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _trusted_proxies() -> set:
    raw = os.getenv("RISKI_TRUSTED_PROXIES", "127.0.0.1").strip()
    return {p.strip() for p in raw.split(",") if p.strip()} or {"127.0.0.1"}


def client_identifier(request) -> str:
    """Client key for rate limiting: the last X-Forwarded-For hop when the
    direct peer is a trusted proxy, else the peer address itself (a spoofed
    header from a non-proxy peer is never trusted)."""
    peer = (request.client.host if request.client else "") or "unknown"
    if peer in _trusted_proxies():
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-1]
    return peer


class SlidingWindowLimiter:
    """In-process sliding-window counter per (client, group)."""

    def __init__(self, window_seconds: int = DEFAULT_WINDOW_SECONDS):
        self.window = window_seconds
        self._hits: dict = {}
        self._lock = threading.Lock()

    def check(self, client: str, group: str, limit: int) -> bool:
        """True when the request is allowed; the attempt is recorded."""
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            key = (client, group)
            dq = self._hits.setdefault(key, deque())
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            return True

    def retry_after(self, client: str, group: str) -> int:
        """Seconds until the oldest recorded hit ages out of the window."""
        with self._lock:
            dq = self._hits.get((client, group))
            if not dq:
                return self.window
            elapsed = time.time() - dq[0]
            return max(1, int(self.window - elapsed) + 1)


def _limits() -> dict:
    return {
        "llm": _env_int("RISKI_RATE_LIMIT_LLM", DEFAULT_LLM_LIMIT),
        "search": _env_int("RISKI_RATE_LIMIT_SEARCH", DEFAULT_SEARCH_LIMIT),
    }


limiter = SlidingWindowLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware: 429 + Retry-After before routing (and therefore
    before any database/LLM work) when a client exceeds its group's limit.
    /health (monitoring) is never limited."""

    async def dispatch(self, request, call_next):
        path = request.url.path.rstrip("/") or "/"
        if path in EXEMPT_PATHS:
            return await call_next(request)
        group = "llm" if path in LLM_PATHS else "search"
        client = client_identifier(request)
        limit = _limits()[group]
        if not limiter.check(client, group, limit):
            retry = limiter.retry_after(client, group)
            return JSONResponse(
                status_code=429,
                content={"detail": f"rate limit exceeded (group={group})"},
                headers={"Retry-After": str(retry)},
            )
        return await call_next(request)


def llm_budget_for_search(request, summarize: bool) -> None:
    """Enforce the LLM budget for /search requests with summarize=true.

    Called from the /search endpoint *before* any database or LLM work.
    Raises HTTPException 429 (Retry-After) when the llm-group budget for
    this client is exhausted; records the attempt otherwise.
    """
    if not summarize:
        return

    from fastapi import HTTPException

    client = client_identifier(request)
    limit = _limits()["llm"]
    if not limiter.check(client, "llm", limit):
        retry = limiter.retry_after(client, "llm")
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded (group=llm)",
            headers={"Retry-After": str(retry)},
        )
