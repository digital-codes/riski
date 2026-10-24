"""RISKI search API (change: api-search-expand).

Thin FastAPI layer over the search pipeline:

  POST /search   hybrid search (+ optional summary) -> full result incl.
                 timeline, graph, matched_entities, facets, applied_filters
  POST /expand   depth-1 neighborhood of a graph node (additive
                nodes/edges for client-side merge-by-id)
  GET  /facets   facet listing for filter UIs
  GET  /health   liveness

Run (dev):
    uvicorn src.apiServer:app --port 8000

Interactive clients (the web app) may hold a ``sessionId`` for future
contextual endpoints (/ask — follow-up questions — is drafted but not
implemented); /search creates one. Sessions are in-memory only.
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.db import get_engine
from src.pgHybridSearch import FilterError, facets
from src.pgTimeline import get_db_session, search_and_summarize

app = FastAPI(title="RISKI Search API", version="0.1.0")

# permissive CORS for local frontend dev (vite runs on its own port)
try:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:4173", "http://localhost:5199"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
except ImportError:  # pragma: no cover
    pass

# in-memory session store (no persistence for v1)
_sessions: Dict[str, Dict[str, Any]] = {}


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    filters: Optional[List[Dict[str, Any]]] = None
    top_k: int = Field(default=10, ge=1, le=100)
    summarize: bool = True
    signals: Optional[Dict[str, bool]] = None


class ExpandRequest(BaseModel):
    node_id: str = Field(min_length=1, description="Graph node id, '{Type}_{oparlKey}'")
    limit_per_relation: int = Field(default=25, ge=1, le=100)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok"}


@app.post("/search")
def search(req: SearchRequest) -> Dict[str, Any]:
    from src.db import get_engine as _ge  # noqa: F401 (import guard)

    try:
        session = get_db_session()
    except Exception as exc:  # pragma: no cover - db down
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}")

    try:
        result = search_and_summarize(
            session, req.query, top_k=req.top_k,
            filters=req.filters, signals=req.signals, summarize=req.summarize,
        )
    except FilterError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        session.close()

    session_id = uuid.uuid4().hex
    _sessions[session_id] = {
        "query": req.query,
        "filters": req.filters or [],
        "node_ids": [n["id"] for n in result.get("graph", {}).get("nodes", [])],
        "result": result,  # kept for the async /summarize + /geo steps
    }
    result["sessionId"] = session_id
    return result


@app.get("/geo/{session_id}")
def geo(session_id: str) -> Dict[str, Any]:
    """GeoJSON FeatureCollection of the streets/districts linked to the
    session's answer set (WGS84). Empty collection when the answer set
    has no georeferences."""
    from src.pgGeo import EMPTY_FEATURE_COLLECTION, collect_geo

    sess = _sessions.get(session_id)
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
    session_id: str = Field(min_length=1)
    # change: summary-refine-file-control
    refine: bool = False          # re-run with full content (user action)
    exclude: list[str] = Field(default_factory=list)  # oparlKeys to drop


@app.post("/summarize")
def summarize(req: SummarizeRequest) -> Dict[str, Any]:
    """Async summary step: run the (teaser-based) summarizer over the
    stored search result of a session. Lets clients render search results
    immediately and fill the summary in when it arrives.

    With ``refine=True`` (user action) the summarizer re-runs with full
    document content; ``exclude`` drops files from the summary's document
    set and persists in the session. The response additionally carries the
    structured per-file metadata for the interactive file list."""
    sess = _sessions.get(req.session_id)
    if sess is None or "result" not in sess:
        raise HTTPException(status_code=404, detail="unknown session")
    result = sess["result"]
    if result.get("summary") and not req.refine:
        return {"summary": result["summary"],
                "files": result.get("summary_files", []),
                "refined": result.get("summary_refined", False)}
    if sess.get("summarizing"):
        # a refine is already in flight for this session — report the
        # current state instead of stacking another LLM call
        return {"summary": result.get("summary"),
                "files": result.get("summary_files", []),
                "refined": result.get("summary_refined", False),
                "in_progress": True}

    # persist exclusions in the session so subsequent refinements honour
    # them without resending
    if req.exclude:
        merged = set(result.get("summary_excluded") or []) | set(req.exclude)
        result["summary_excluded"] = sorted(merged)
    # refused files stay excluded across refinements
    req_exclude = set(result.get("summary_excluded") or [])

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
    return {"summary": result.get("summary"),
            "files": result.get("summary_files", []),
            "refined": result.get("summary_refined", False)}


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
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="unknown session")
    return _sessions[session_id]
