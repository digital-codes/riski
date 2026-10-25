"""RISKI search API (change: api-search-expand + intent-router).

Thin FastAPI layer over the search pipeline:

  POST /search   hybrid search (+ optional summary) -> full result incl.
                 timeline, graph, matched_entities, facets, applied_filters
  POST /ask      intent-routed question answering: decodes the query via
                 the SystemOne decision model (config/intents.yaml),
                 derives structured filters (gremium meeting scope,
                 decision-type documents), runs the search with an
                 empty-result fallback ladder, and returns the search
                 result contract plus intent, slots, applied_filters and
                 fallback_notes. Falls back to plain search when the
                 decision model is unreachable. Accepts an optional
                 sessionId (context reserved for a follow-up conversation
                 mode; recorded but not yet consulted).
  POST /expand   depth-1 neighborhood of a graph node (additive
                nodes/edges for client-side merge-by-id)
  GET  /facets   facet listing for filter UIs
  GET  /health   liveness

Run (dev):
    uvicorn src.apiServer:app --port 8000

Interactive clients (the web app) may hold a ``sessionId`` for future
contextual endpoints; /search and /ask create one. Sessions are
in-memory only.
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import os
import time
import uuid
import threading
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from src import apiRateLimit
from src.db import get_engine
from src.pgHybridSearch import CapacityError, FilterError, facets
from src.pgTimeline import get_db_session, search_and_summarize

app = FastAPI(title="RISKI Search API", version="0.1.0")

# CORS: dev origins by default (vite runs on its own port); production
# origins come from RISKI_CORS_ORIGINS (comma-separated) for split
# deployments — a same-origin production deployment behind apache needs
# none (change: api-security-hardening)
def _cors_origins() -> List[str]:
    raw = os.getenv("RISKI_CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:5173",
        "http://localhost:4173",
        "http://localhost:5199",
    ]


try:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )
except ImportError:  # pragma: no cover
    pass

# per-client sliding-window rate limiting (change: api-security-hardening)
app.add_middleware(apiRateLimit.RateLimitMiddleware)

# in-memory session store (no persistence for v1) — bounded since
# api-capacity-hardening: TTL + max size, lazy eviction on insert (no
# background thread)
_sessions: Dict[str, Dict[str, Any]] = {}
_sessions_lock = threading.Lock()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _session_ttl() -> int:
    return max(1, _env_int("RISKI_SESSION_TTL", 2 * 60 * 60))


def _session_max() -> int:
    return max(1, _env_int("RISKI_SESSION_MAX", 1000))


def _store_session(session_id: str, entry: Dict[str, Any]) -> None:
    """Insert a session, evicting expired and (if still over the cap) the
    oldest entries first."""
    now = time.time()
    with _sessions_lock:
        ttl = _session_ttl()
        cap = _session_max()
        expired = [sid for sid, s in _sessions.items()
                   if now - s.get("created", now) > ttl]
        for sid in expired:
            _sessions.pop(sid, None)
        while len(_sessions) >= cap:
            oldest = min(_sessions.items(), key=lambda kv: kv[1].get("created", 0))[0]
            _sessions.pop(oldest, None)
        entry["created"] = now
        _sessions[session_id] = entry


def _get_session(session_id: str) -> Optional[Dict[str, Any]]:
    with _sessions_lock:
        sess = _sessions.get(session_id)
        if sess is not None and time.time() - sess.get("created", time.time()) > _session_ttl():
            _sessions.pop(session_id, None)
            return None
        return sess


def _log_failure(where: str, exc: Exception) -> str:
    """Log the full exception, return a correlation id for the client-facing
    generic error body (change: api-security-hardening)."""
    import logging

    correlation_id = uuid.uuid4().hex
    logging.getLogger("riski.api").exception(
        "%s failed (correlation_id=%s): %s", where, correlation_id, exc
    )
    return correlation_id


# Input bounds (change: api-security-hardening): the API is anonymous;
# unbounded queries/filters burn tokens, pool connections and memory.
MAX_QUERY_LENGTH = 512
MAX_FILTER_ITEMS = 20
MAX_EXCLUDE_ITEMS = 100


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    filters: Optional[List[Dict[str, Any]]] = Field(default=None, max_length=MAX_FILTER_ITEMS)
    top_k: int = Field(default=10, ge=1, le=100)
    # change: api-capacity-hardening — default moved to False: the LLM
    # summary belongs in the async /summarize follow-up, not the search hot
    # path (each inline summary pins a thread + LLM slot for 10–90 s).
    # Non-interactive callers pass summarize=True explicitly.
    summarize: bool = False
    signals: Optional[Dict[str, bool]] = None


class ExpandRequest(BaseModel):
    node_id: str = Field(min_length=1, description="Graph node id, '{Type}_{oparlKey}'")
    limit_per_relation: int = Field(default=25, ge=1, le=100)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok"}


@app.post("/search")
def search(req: SearchRequest, request: Request) -> Dict[str, Any]:
    # inline summaries share the LLM budget (change: api-security-hardening);
    # enforced before any database/LLM work
    apiRateLimit.llm_budget_for_search(request, req.summarize)

    try:
        session = get_db_session()
    except Exception:  # pragma: no cover - db down
        raise HTTPException(status_code=503, detail="database temporarily unavailable")

    try:
        result = search_and_summarize(
            session, req.query, top_k=req.top_k,
            filters=req.filters, signals=req.signals, summarize=req.summarize,
        )
    except FilterError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except CapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Retry-After": "5"})
    except Exception as exc:
        correlation_id = _log_failure("search", exc)
        raise HTTPException(
            status_code=500,
            detail=f"internal error (correlation_id={correlation_id})",
        )
    finally:
        session.close()

    session_id = uuid.uuid4().hex
    _store_session(session_id, {
        "query": req.query,
        "filters": req.filters or [],
        "node_ids": [n["id"] for n in result.get("graph", {}).get("nodes", [])],
        "result": result,  # kept for the async /summarize + /geo steps
    })
    result["sessionId"] = session_id
    return result


class AskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)
    session_id: Optional[str] = Field(default=None, max_length=64)
    top_k: int = Field(default=10, ge=1, le=100)
    signals: Optional[Dict[str, bool]] = None
    summarize: bool = True


@app.post("/ask")
def ask(req: AskRequest) -> Dict[str, Any]:
    """Intent-routed question answering (change: intent-router).

    Decodes the query via the SystemOne decision model, derives structured
    filters, and runs the search with an empty-result fallback ladder.
    Degrades to plain search (intent=search_topic) when the decision
    model is unreachable."""
    from src.pgIntentRouter import ask as route_ask

    try:
        session = get_db_session()
    except Exception:  # pragma: no cover - db down
        raise HTTPException(status_code=503, detail="database temporarily unavailable")

    try:
        result = route_ask(
            session, req.query, top_k=req.top_k,
            signals=req.signals, summarize=req.summarize,
        )
    except CapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Retry-After": "5"})
    except Exception as exc:
        correlation_id = _log_failure("ask", exc)
        raise HTTPException(
            status_code=500,
            detail=f"internal error (correlation_id={correlation_id})",
        )
    finally:
        session.close()

    session_id = req.session_id or uuid.uuid4().hex
    _store_session(session_id, {
        "query": req.query,
        "filters": result.get("applied_filters") or [],
        "intent": result.get("intent"),
        "slots": result.get("slots") or {},
        "node_ids": [n["id"] for n in result.get("graph", {}).get("nodes", [])],
        "result": result,  # kept for the async /summarize + /geo steps
    })
    result["sessionId"] = session_id
    return result


@app.get("/geo/{session_id}")
def geo(session_id: str) -> Dict[str, Any]:
    """GeoJSON FeatureCollection of the streets/districts linked to the
    session's answer set (WGS84). Empty collection when the answer set
    has no georeferences."""
    from src.pgGeo import EMPTY_FEATURE_COLLECTION, collect_geo

    sess = _get_session(session_id)
    if sess is None or "result" not in sess:
        raise HTTPException(status_code=404, detail="unknown session")
    result = sess["result"]
    # map scope = the graph-connected answer set (not the matched_entities
    # long tail — weak recall matches drag in unrelated streets)
    keys = [n["oparlKey"] for n in result.get("graph", {}).get("nodes", []) if n.get("type") == "AgendaItem"]
    file_keys = [n["oparlKey"] for n in result.get("graph", {}).get("nodes", [])
                 if n.get("type") in ("File", "AuxFile")]
    # gate on the summarizer's relevance verdict: georeferences from
    # documents the summarizer refused are excluded from the map
    refused = {r["oparlKey"] for r in result.get("summary_refused", [])}
    file_keys = [k for k in file_keys if k not in refused]
    engine = get_engine(readonly=True)
    return collect_geo(engine, keys, file_keys)


class SummarizeRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    # change: summary-refine-file-control
    refine: bool = False          # re-run with full content (user action)
    exclude: list[str] = Field(default_factory=list, max_length=MAX_EXCLUDE_ITEMS)  # oparlKeys to drop


@app.post("/summarize")
def summarize(req: SummarizeRequest) -> Dict[str, Any]:
    """Async summary step: run the (teaser-based) summarizer over the
    stored search result of a session. Lets clients render search results
    immediately and fill the summary in when it arrives.

    With ``refine=True`` (user action) the summarizer re-runs with full
    document content; ``exclude`` drops files from the summary's document
    set and persists in the session. The response additionally carries the
    structured per-file metadata for the interactive file list."""
    sess = _get_session(req.session_id)
    if sess is None or "result" not in sess:
        raise HTTPException(status_code=404, detail="unknown session")
    result = sess["result"]
    # the request carries the COMPLETE desired exclusion set (the frontend
    # maintains it) — replace, never union: re-including a file must remove
    # it from the set (user finding: a union merge made re-inclusion
    # impossible and triggered a pointless second refinement)
    result["summary_excluded"] = sorted(set(req.exclude))
    # the flags in summary_files must always reflect the current exclusion
    # set — read at payload time, not snapshot time
    excluded_set = set(result.get("summary_excluded") or [])

    def _payload(in_progress: bool = False) -> Dict[str, Any]:
        # read the exclusion set at payload time — the summarizer may have
        # extended it (teaser run: refused files pre-excluded)
        excluded_now = set(result.get("summary_excluded") or [])
        files_payload = [
            {**f, "excluded": f["oparlKey"] in excluded_now}
            for f in result.get("summary_files", [])
        ]
        return {"summary": result.get("summary"),
                "files": files_payload,
                "refined": result.get("summary_refined", False),
                **({"in_progress": True} if in_progress else {})}

    if result.get("summary") and not req.refine:
        return _payload()
    if sess.get("summarizing"):
        # a refine is already in flight for this session — report the
        # current state (with the merged exclusions) instead of stacking
        # another LLM call
        return _payload(in_progress=True)

    req_exclude = excluded_set

    sess["summarizing"] = True
    db_session = get_db_session()
    try:
        from src.pgResultSummarizer import ResultSummarizer

        ResultSummarizer(db_session).summarize(
            result,
            force=req.refine,
            use_full_content=req.refine,
            exclude=req_exclude,
        )
    finally:
        db_session.close()
        sess["summarizing"] = False
    return _payload()


@app.post("/expand")
def expand(req: ExpandRequest) -> Dict[str, Any]:
    from src.graphModel import expand_neighbors

    engine = get_engine(readonly=True)
    try:
        return expand_neighbors(engine, req.node_id, req.limit_per_relation)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/facets")
def get_facets() -> Dict[str, Any]:
    import sqlalchemy as sa

    engine = get_engine(readonly=True)
    with engine.connect() as conn:
        return facets(conn)


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> Dict[str, Any]:
    sess = _get_session(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="unknown session")
    return sess
