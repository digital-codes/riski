"""RISKI search API (change: api-search-expand + intent-router).

Thin FastAPI layer over the search pipeline:

  POST /search   recall stage only (change: progressive-frontend-
                 rendering): top_files, matched_entities, facets,
                 applied_filters + sessionId — timeline and graph are
                 fetched separately via /timeline and /graph
  POST /ask      intent-routed question answering: decodes the query via
                 the SystemOne decision model (config/intents.yaml),
                 derives structured filters (gremium meeting scope,
                 decision-type documents), runs the recall stage with an
                 empty-result fallback ladder, and returns the stage-1
                 contract plus intent, slots, applied_filters and
                 fallback_notes. Falls back to plain search when the
                 decision model is unreachable. Accepts an optional
                 sessionId (context reserved for a follow-up conversation
                 mode; recorded but not yet consulted).
  POST /timeline stage 2 for a session: traversal + grouped timeline
  POST /graph    stage 3 for a session: serialized graph + geo
                 availability (computes stage 2 first if needed, so
                 out-of-order calls are safe)
  POST /expand   depth-1 neighborhood of a graph node (additive
                 nodes/edges for client-side merge-by-id)
  GET  /facets   facet listing for filter UIs
  GET  /health   liveness

Run (dev):
    uvicorn src.apiServer:app --port 8000

Interactive clients (the web app) may hold a ``sessionId`` for the
staged follow-up endpoints; /search and /ask create one. Sessions are
in-memory only.
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import threading
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.db import get_engine
from src.pgHybridSearch import FilterError, facets
from src.pgTimeline import get_db_session, search_stage

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


def _run_summarizer(session, result: Dict[str, Any]) -> None:
    """Run the result summarizer inline over a stage-1 result (the
    ``summarize`` request flag — non-interactive consumers; the web app
    always uses the async /summarize endpoint instead)."""
    from src.pgResultSummarizer import ResultSummarizer

    ResultSummarizer(session).summarize(result)


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


@app.get("/instance")
def instance_config() -> Dict[str, Any]:
    """Deployment-instance settings for the frontend (change:
    instance-agnostic-config): branding, legal links, data sources, map
    view center/zoom and the default search query. Served from the
    instance config (env > config/instance.yaml > Karlsruhe defaults)."""
    from src.instanceConfig import get_instance_config

    cfg = get_instance_config()
    geo = cfg.get("geo") or {}
    return {
        "frontend": cfg.get("frontend") or {},
        "geo": {
            "city": geo.get("city"),
            "map_center": geo.get("map_center"),
            "map_zoom": geo.get("map_zoom"),
        },
    }


@app.post("/search")
def search(req: SearchRequest) -> Dict[str, Any]:
    """Recall stage only (change: progressive-frontend-rendering): returns
    top_files, matched_entities, facets, applied_filters + sessionId.
    Timeline and graph follow via POST /timeline and POST /graph."""
    from src.db import get_engine as _ge  # noqa: F401 (import guard)

    try:
        session = get_db_session()
    except Exception as exc:  # pragma: no cover - db down
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}")

    try:
        result = search_stage(
            session, req.query, top_k=req.top_k,
            filters=req.filters, signals=req.signals,
        )
        if req.summarize:
            _run_summarizer(session, result)
    except FilterError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        session.close()

    session_id = uuid.uuid4().hex
    _sessions[session_id] = {
        "query": req.query,
        "filters": req.filters or [],
        "stage1": result,      # full stage-1 payload (top_files with sids)
        "timeline": None,      # filled by POST /timeline
        "graph": None,         # filled by POST /graph (stage lock-guarded)
        "result": result,      # client-facing fields; /summarize mutates in place
        "stage_lock": threading.Lock(),
    }
    result["sessionId"] = session_id
    return result


class AskRequest(BaseModel):
    query: str = Field(min_length=1)
    session_id: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=100)
    signals: Optional[Dict[str, bool]] = None
    summarize: bool = True


def _stage1_search_fn(session, query: str, top_k: int = 10,
                      filters: Optional[List[Dict[str, Any]]] = None,
                      signals: Optional[Dict[str, bool]] = None,
                      summarize: bool = False) -> Dict[str, Any]:
    """Recall-stage-only pipeline callable injected into the intent router
    (change: progressive-frontend-rendering) — same signature as
    ``search_and_summarize``, but runs :func:`search_stage` and never
    builds timeline/graph. With ``summarize`` (request flag), the LLM
    summarizer runs inline as before."""
    result = search_stage(session, query, top_k=top_k, filters=filters, signals=signals)
    if summarize:
        _run_summarizer(session, result)
    return result


@app.post("/ask")
def ask(req: AskRequest) -> Dict[str, Any]:
    """Intent-routed question answering (change: intent-router).

    Decodes the query via the SystemOne decision model, derives structured
    filters, and runs the recall stage with an empty-result fallback
    ladder. Degrades to plain search (intent=search_topic) when the
    decision model is unreachable. Timeline and graph follow via the
    staged /timeline and /graph endpoints."""
    from src.pgIntentRouter import ask as route_ask

    try:
        session = get_db_session()
    except Exception as exc:  # pragma: no cover - db down
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}")

    try:
        result = route_ask(
            session, req.query, top_k=req.top_k,
            signals=req.signals, summarize=req.summarize,
            search_fn=_stage1_search_fn,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        session.close()

    session_id = req.session_id or uuid.uuid4().hex
    # meeting-centric answers (D10) build their graph synchronously in the
    # router — stash it as the precomputed graph stage instead of sending
    # it in the stage-1 response (change: progressive-frontend-rendering)
    precomputed_graph = result.pop("graph", None)
    _sessions[session_id] = {
        "query": req.query,
        "filters": result.get("applied_filters") or [],
        "intent": result.get("intent"),
        "slots": result.get("slots") or {},
        "stage1": result,           # full stage-1 payload (top_files with sids)
        "timeline": None,           # filled by POST /timeline
        "graph": precomputed_graph, # precomputed (meeting mode) or filled by POST /graph
        "result": result,           # client-facing fields; /summarize mutates in place
        "stage_lock": threading.Lock(),
    }
    result["sessionId"] = session_id
    return result


class SessionRequest(BaseModel):
    session_id: str = Field(min_length=1)


class GraphRequest(SessionRequest):
    # change: disable-organisation-expansion — "documents" (default) or
    # "full"; see POST /graph docstring
    scope: Optional[str] = None


def _get_session(session_id: str) -> Dict[str, Any]:
    sess = _sessions.get(session_id)
    if sess is None or "result" not in sess:
        raise HTTPException(status_code=404, detail="unknown session")
    return sess


@app.post("/timeline")
def timeline(req: SessionRequest) -> Dict[str, Any]:
    """Stage 2 for a session (change: progressive-frontend-rendering):
    traversal + grouped timeline for the session's recall results. Runs
    the stage on first call; lock-guarded so concurrent callers wait for
    the same computation instead of racing."""
    sess = _get_session(req.session_id)
    with sess["stage_lock"]:
        _ensure_stage2(sess)
    return {"sessionId": req.session_id, "query": sess["query"], "timeline": sess["timeline"]}


def _ensure_stage2(sess: Dict[str, Any]) -> None:
    """Compute stage 2 (traversal + timeline) once per session. Callers
    must hold ``sess["stage_lock"]``. The full stage-2 payload is kept in
    the session so /graph reuses the same ``find_related_objects``
    traversal instead of walking the association tables again."""
    if sess.get("_stage2") is not None:
        return
    db_session = get_db_session()
    try:
        from src.pgTimeline import timeline_stage

        stage2 = timeline_stage(db_session, sess["stage1"])
    finally:
        db_session.close()
    sess["_stage2"] = stage2
    sess["timeline"] = stage2["timeline"]


@app.post("/graph")
def graph(req: GraphRequest) -> Dict[str, Any]:
    """Stage 3 for a session (change: progressive-frontend-rendering):
    serialized graph + geo availability. Computes stage 2 first when it
    has not run yet, so out-of-order calls (graph before timeline) are
    safe; a later /timeline call returns the already-computed result.

    ``scope`` (change: disable-organisation-expansion): "documents" (the
    default — traversal seeded by the top_k answer documents only) or
    "full" (complete result-list traversal incl. agenda-item seed blocks).
    Both scopes are computed once per stage-2 run; switching serves the
    stored graph without re-traversal."""
    sess = _get_session(req.session_id)
    with sess["stage_lock"]:
        if sess.get("graph") is None:
            _ensure_stage2(sess)
            db_session = get_db_session()
            try:
                from src.pgTimeline import graph_stage

                stage3 = graph_stage(db_session, sess["stage1"], sess["_stage2"])
            finally:
                db_session.close()
            sess["graph"] = stage3["graph"]                  # full scope (back-compat)
            sess["graph_documents"] = stage3.get("graph_documents") or stage3["graph"]
            sess["geo_available"] = stage3["geo_available"]
            sess["node_ids"] = [n["id"] for n in stage3["graph"].get("nodes", [])]
    from src.graphModel import expandable_types

    scope = req.scope or "documents"
    selected = (sess.get("graph_documents") if scope == "documents" else sess["graph"]) \
        or sess["graph"]
    return {
        "sessionId": req.session_id,
        "query": sess["query"],
        "scope": scope,
        "graph": selected,
        "geo_available": sess.get("geo_available", False),
        "expandable_types": expandable_types(),
    }


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
    # staged sessions carry the graph under its own key (filled by
    # POST /graph); monolithic payloads (sample data, old clients) keep it
    # in the result (change: progressive-frontend-rendering)
    graph = sess.get("graph") or result.get("graph") or {}
    # user's document set state (change: geo-gating): the summary_refused
    # + summary_excluded keys, authoritative for the enabled document set
    refused = {r["oparlKey"] for r in result.get("summary_refused", [])}
    excluded = set(result.get("summary_excluded") or [])

    summary_files = result.get("summary_files") or []
    if summary_files:
        # change: geo-gating (map scope = summary document list) — once the
        # summarizer has produced the document list, the map uses ONLY the
        # selected (enabled) documents from that list. Graph-side auxiliary
        # files and agenda-item links no longer contribute: their names
        # cannot be correlated with the document list (user finding), and
        # weak traversal matches flooded the map.
        seen = {f.get("oparlKey") for f in summary_files if isinstance(f, dict)}
        blocked = (refused | excluded) & seen
        keys = []
        file_keys = [f.get("oparlKey") for f in summary_files
                     if isinstance(f, dict) and f.get("oparlKey")
                     and f["oparlKey"] not in blocked]
    else:
        # no summary verdicts yet (pre-summary fetch, meeting-mode answers):
        # map scope = the graph-connected answer set (not the
        # matched_entities long tail — weak recall matches drag in
        # unrelated streets); files not yet in summary_files cannot have
        # been disabled by the user — only files the summarizer has seen
        # can be excluded/refused
        keys = [n["oparlKey"] for n in graph.get("nodes", []) if n.get("type") == "AgendaItem"]
        file_keys = [n["oparlKey"] for n in graph.get("nodes", [])
                     if n.get("type") in ("File", "AuxFile")]
        file_keys = [k for k in file_keys if k not in (refused | excluded)]
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
    # change: agenda-sibling-documents — the summarizer's document set is
    # the block-expanded answer set: search hits + all documents of touched
    # agenda-item blocks (e.g. TOP 13.1/13.2/13.3), even beyond top_k.
    # Idempotent per session (re-runs/refines reuse the expansion).
    if not sess.get("top_files_expanded"):
        from src.pgTimeline import block_expand_top_files

        block_expand_top_files(get_db_session(), result, sess)
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
                # refused keys: the frontend marks these documents as
                # rejected in the network view (change: network-highlighting)
                "refused": sorted(r.get("oparlKey") for r in
                                  (result.get("summary_refused") or [])),
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
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="unknown session")
    # internals: stage_lock is not serializable; _stage2 carries the raw
    # traversal payload (large, debug-only dump keeps it out)
    return {k: v for k, v in _sessions[session_id].items()
            if k not in ("stage_lock", "_stage2")}
