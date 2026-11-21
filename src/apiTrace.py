"""apiTrace — opt-in end-to-end debug tracing of the API request flow
(change: api-debug-logging).

Activated with ``RISKI_API_TRACE=1`` in the environment when starting the
uvicorn API service; disabled by default (no file, no handler, no cost).
All scripts involved in API interaction append single-line JSON entries
to a fixed file at the project root, ``log/api_debug.log``:

    {"ts": "2026-11-21T10:04:05.123+01:00", "src": "src.apiServer",
     "req": "ab12cd34ef56", "event": "http_request", ...fields}

``ts`` (ISO-8601 with timezone), ``src`` (calling module) and ``event``
are always present; ``req`` carries the request id when called within a
request context (set by the apiServer middleware) and is ``null``
otherwise. Field values are size-capped (strings ~300 chars, lists 5
items). The trace never raises: after a write failure it logs one
warning and goes silent for the rest of the process.
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ENV_FLAG = "RISKI_API_TRACE"
_TRUTHY_ON = {"1", "true", "yes", "on"}

MAX_STR = 300   # per-field string cap
MAX_LIST = 5    # per-field list cap

_logger = logging.getLogger("riski.apitrace")
_env_cache: Optional[tuple] = None  # (raw env value, enabled) — env won't change mid-process
_failed = False

_req_var: ContextVar[Optional[str]] = ContextVar(
    "riski_api_trace_req", default=None)


def trace_enabled() -> bool:
    """Whether the API debug trace is on (env ``RISKI_API_TRACE``)."""
    global _env_cache
    raw = os.getenv(ENV_FLAG, "0")
    if _env_cache is not None and _env_cache[0] == raw:
        return _env_cache[1]
    on = raw.strip().lower() in _TRUTHY_ON
    _env_cache = (raw, on)
    return on


def log_file_path() -> Path:
    """The fixed trace file at the project root (independent of the CWD
    the service was started from)."""
    return Path(__file__).resolve().parent.parent / "log" / "api_debug.log"


def _is_trace_handler(handler: logging.Handler) -> bool:
    """Identify OUR file handler among whatever else is attached to the
    logger (test frameworks and uvicorn attach their own handlers)."""
    return getattr(handler, "_riski_api_trace", False)


def _ensure_handler() -> None:
    if any(_is_trace_handler(h) for h in _logger.handlers):
        return
    path = log_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8", delay=True)
    handler._riski_api_trace = True  # marker for _is_trace_handler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False  # stay independent of root-logger config


def _truncate(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_STR:
        return value[:MAX_STR] + "…"
    if isinstance(value, (list, tuple)):
        out = [_truncate(v) for v in value[:MAX_LIST]]
        if len(value) > MAX_LIST:
            out.append("(+%d more)" % (len(value) - MAX_LIST))
        return out
    if isinstance(value, dict):
        return {str(k): _truncate(v) for k, v in value.items()}
    return value


def new_request_id() -> str:
    """Short unique id for one HTTP request (links all its trace entries)."""
    return uuid.uuid4().hex[:12]


def set_request_id(req_id: str) -> None:
    _req_var.set(req_id)


def get_request_id() -> Optional[str]:
    """The current request's trace id, or None outside a request."""
    return _req_var.get()


def trace(event: str, req: Optional[str] = None, **fields: Any) -> None:
    """Append one debug entry to ``log/api_debug.log`` (no-op unless the
    env flag is on; never raises). ``req`` defaults to the current
    request context's id."""
    global _failed
    if _failed or not trace_enabled():
        return
    try:
        _ensure_handler()
        try:
            src = sys._getframe(1).f_globals.get("__name__", "unknown")
        except (AttributeError, ValueError):  # pragma: no cover
            src = "unknown"
        entry = {
            "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "src": src,
            "req": req if req is not None else _req_var.get(),
            "event": event,
        }
        entry.update(_truncate(fields))
        _logger.info(json.dumps(entry, ensure_ascii=False, default=str))
    except Exception:  # noqa: BLE001 - tracing must never break a request
        _failed = True
        logging.getLogger("riski.kg.app").warning(
            "apiTrace disabled after a write failure", exc_info=True)


def _reset() -> None:
    """Test hook: drop cached state (env cache, handler, failure latch)."""
    global _failed, _env_cache
    _failed = False
    _env_cache = None
    for h in list(_logger.handlers):
        if _is_trace_handler(h):
            _logger.removeHandler(h)
            h.close()
    _req_var.set(None)
