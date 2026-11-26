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

import logging
import os
import threading
import time
import unicodedata
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import text
from pydantic import BaseModel, Field

from src.pgIntentRouter import _FORCE as ROUTER_FORCE  # change: request-thread-facets
from src.apiTrace import (
    new_request_id, set_request_id, trace, trace_enabled,
)
from src.db import get_engine
from src.pgHybridSearch import FilterError, facets
from src.pgTimeline import get_db_session, search_stage

app = FastAPI(title="RISKI Search API", version="0.1.0")

_kg_log = logging.getLogger("riski.kg.app")
# kg-app-integration rollout flag (design D6 rollback path)
app.state.kg_app_integration = os.getenv("KG_APP_INTEGRATION", "1") == "1"


# ----------------------------------------------------------------------
# api-debug-logging: request-flow debug trace (env RISKI_API_TRACE)
# ----------------------------------------------------------------------
def _trace_query(endpoint: str, query: str, **params: Any) -> None:
    """Incoming-query event: sanitized query + request parameters."""
    trace("api_query", endpoint=endpoint, query=query, **params)


def _trace_response(endpoint: str, result: Dict[str, Any]) -> None:
    """Frontend-bound response summary (compact counters, never the body)."""
    if not trace_enabled():
        return
    trace(
        "api_response", endpoint=endpoint,
        mode=result.get("mode") or "normal",
        intent=result.get("intent"),
        result_count=len(result.get("top_files") or []),
        topics_count=len(result.get("topics") or []),
        has_summary=bool(result.get("summary")),
        related_count=len(result.get("related_documents") or []),
        chips_count=len(result.get("chips") or []),
        followups_count=len(result.get("followups") or []),
        clarification=bool(result.get("clarification")),
        empty=bool(result.get("empty_response")),
        thread_reset=bool(result.get("thread_reset")),
        session_id=result.get("sessionId"),
    )


@app.middleware("http")
async def _trace_middleware(request: Request, call_next):
    """Emit http_request/http_response entries and set the request id all
    downstream trace entries inherit (contextvar propagates into the
    endpoint's threadpool context)."""
    if not trace_enabled():
        return await call_next(request)
    req_id = new_request_id()
    set_request_id(req_id)
    trace("http_request", req=req_id, method=request.method,
          path=request.url.path, query_params=dict(request.query_params))
    t0 = time.perf_counter()
    response = await call_next(request)
    trace("http_response", req=req_id, path=request.url.path,
          status=response.status_code,
          ms=round((time.perf_counter() - t0) * 1000, 1))
    return response

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
    # kg-app-integration D7: {state, session_id} of the prior sealed turn,
    # or {fresh: true} to request a new thread (app load). Optional.
    thread: Optional[Dict[str, Any]] = None


# Weak-recall floor for chips mode (D7): matched_entities max score below
# this = nothing lexically significant → chips sheet (calibrated 2026-11-20).
KG_RECALL_FLOOR = 0.025


def _thread_chips(limit: int = 5) -> list[dict]:
    """Chips-mode payload: 5 kg topic chips from the vocabulary
    (deterministic, no LLM) — topic + description (task 7.5)."""
    from src.kg.kgVocab import load_vocab
    vocab = load_vocab()
    chips = []
    for tag, spec in (vocab.get("file_tags") or {}).items():
        desc = str(spec.get("description", tag)) if isinstance(spec, dict) else str(spec)
        chips.append({"topic": tag, "example": desc})
        if len(chips) >= limit:
            break
    return chips


def _thread_turn(session, query: str, req_thread: dict | None,
                 model_followup: bool | None = None) -> dict:
    """kg-app-integration D7: open the prior sealed thread, classify the
    turn (followup vs break), apply the 5-turn budget, and return
    {thread, effective_query, forced_break} (tasks 7.1–7.4)."""
    from src.kg.kgFollowups import (
        THREAD_MAX_TURNS, advance_thread, effective_query,
        maybe_new_thread, new_thread,
    )
    from src.kg.kgFollowups import open_state
    from src.pgIntentRouter import classify_thread_turn
    from src.kg.kgQueries import topic_focus_for_query

    req_thread = req_thread if isinstance(req_thread, dict) else None
    sid = uuid.uuid4().hex
    prior_state: dict = {}
    thread = None
    if req_thread and req_thread.get("state") and req_thread.get("session_id"):
        sid = str(req_thread["session_id"])[:64]
        try:
            prior_state = open_state(req_thread["state"], sid) or {}
            thread = maybe_new_thread(prior_state)
        except Exception as exc:  # expired/tampered → treat as new query
            _kg_log.warning("thread token rejected (%s) — new thread", exc)
            thread = new_thread(origin="search")
    if req_thread and req_thread.get("fresh"):
        thread = new_thread(origin="chips")
    if thread is None:
        thread = new_thread(origin="search")

    forced_break = thread["turn_count"] >= THREAD_MAX_TURNS
    if forced_break:
        thread = new_thread(origin="search")

    tf = topic_focus_for_query(query)
    cls = classify_thread_turn(query, "search_topic",
                               {"search_topic": 1.0 if tf else 0.0}, tf,
                               recall_confident=True)
    used_query = query
    concatenated = False
    # change: fix-followup-deixis — the topic_follow model decision (both
    # queries in the slot question) overrides the lexicon when it answered
    if model_followup is not None:
        cls = dict(cls, action="followup" if model_followup else "break")
    followup = cls["action"] == "followup"
    if followup and thread["turns"]:
        used_query = effective_query(thread, query)
        concatenated = True
    advance_thread(thread, query)
    return {
        "thread": thread,
        "session_id": sid,
        "effective_query": used_query,
        "forced_break": forced_break,
        "model_followup": model_followup,
        "concatenated": concatenated,
        "classification": cls,
    }


_OPTION_SLOT_MARKER = "facet:gremium"


def resolve_gremium_for_slot(session: Any, term: str,
                             option: Optional[Dict[str, Any]]) -> Optional[dict]:
    """Slot fill via the option machinery (change: request-thread-facets):
    resolve the gremium term the user SELECTED, month/year from the option
    hint may be absent — the meeting resolution targets the latest held
    meeting with documents. Returns the resolved dict or None."""
    try:
        from src.pgIntentRouter import resolve_gremium, load_intents_config
        cfg = load_intents_config()
        gi = next((i for i in cfg["intents"]
                   if "gremium" in (i.get("slots") or {})), None)
        groups = (gi.get("groups") or {}).get("gremium", []) if gi else []
        out = resolve_gremium(session, term, groups,
                              month=(option or {}).get("month"),
                              year=(option or {}).get("year"))
        return out if out.get("meeting") else None
    except Exception as exc:  # noqa: BLE001
        _kg_log.warning("slot resolve failed: %s", exc)
        return None


def _option_turn(req: Any, query: str) -> Optional[Dict[str, Any]]:
    """Deterministic thread turn for an OPTION selection (change:
    fix-gremium-session-docs-thread): the backend offered the chip, so the
    selection is follow-up by construction — no classify call. Opens the
    sealed state (q0 + turns = the history), builds the effective query
    (history + option topic), advances the thread."""
    try:
        from src.kg.kgFollowups import (
            advance_thread, effective_query, maybe_new_thread, new_thread,
            open_state,
        )
        req_thread = req.thread if isinstance(req.thread, dict) else None
        prior: dict = {}
        sid = uuid.uuid4().hex
        if req_thread and req_thread.get("state") and req_thread.get("session_id"):
            sid = str(req_thread["session_id"])[:64]
            try:
                prior = open_state(req_thread["state"], sid) or {}
            except Exception as exc:  # expired/tampered → new thread
                _kg_log.warning("option state rejected (%s) — new thread", exc)
        thread = maybe_new_thread(prior) or new_thread(origin="chips")
        topic_text = validate_user_query(str(req.option.get("topic")))
        if thread.get("turns"):
            effective = effective_query(thread, topic_text)
        else:
            effective = topic_text
        thread = advance_thread(thread, topic_text)
        # change: request-thread-facets — a gremium-facet option FILLS the
        # slot: the thread keeps the history for concat, but the turn marks
        # the slot so the /ask branch scopes by the organization filter
        option_ctx = (getattr(req, "option", None) or {})
        facet = option_ctx.get("facet") or option_ctx.get("slot")
        return {
            "thread": thread,
            "session_id": sid,
            "effective_query": effective if facet != "gremium" else topic_text,
            "facet": facet,
            "slot_term": topic_text,
            "forced_break": False,
            "concatenated": bool(prior.get("turns")) and facet != "gremium",
            "classification": {"action": "followup", "source": "option",
                               "facet": facet},
        }
    except Exception as exc:  # noqa: BLE001
        _kg_log.warning("option turn failed: %s", exc)
        return None


def _apply_thread_to_result(turn: dict, result: dict, top_files: list | None) -> None:
    """Seal the advanced thread onto the response (normal mode, task 7.4)."""
    from src.kg.kgFollowups import seal_state_or_none
    thread = turn["thread"]
    if not result.get("mode"):
        result["mode"] = "normal"   # keep an options payload's own mode
    result["thread"] = {
        "thread_id": thread["thread_id"],
        "turn_count": thread["turn_count"],
        "origin": thread["origin"],
    }
    if turn["forced_break"]:
        result["thread_reset"] = True
    token = seal_state_or_none(
        {"q0": turn["effective_query"], "thread": thread,
         "top_docs": [tf.get("oparlKey") for tf in (top_files or [])][:8]},
        turn["session_id"],
    )
    if token:
        result["state"] = token
        result["state_session"] = turn["session_id"]


def _apply_chips_mode(turn: dict, result: dict) -> None:
    """Chips-mode payload (tasks 7.5): thread + chips + hint only."""
    from src.kg.kgFollowups import seal_state_or_none
    thread = turn["thread"]
    result["mode"] = "chips"
    result["chips"] = _thread_chips()
    result["hint"] = "Hinweis: Bitte präzisieren Sie Ihre Anfrage."
    result["thread"] = {"thread_id": thread["thread_id"],
                        "turn_count": thread["turn_count"],
                        "origin": thread["origin"]}
    if turn["forced_break"]:
        result["thread_reset"] = True
    token = seal_state_or_none({"q0": turn["effective_query"],
                                "thread": thread, "top_docs": []},
                               turn["session_id"])
    if token:
        result["state"] = token
        result["state_session"] = turn["session_id"]
    # suppress card data — only thread + chips in the payload
    for field in ("top_files", "followups", "clarification",
                  "summary", "related_documents", "matched_entities",
                  "facets", "applied_filters"):
        result.pop(field, None)


# ----------------------------------------------------------------------
# Query sanitation (change: sanitize-queries-and-initial-response)
# ----------------------------------------------------------------------
MAX_QUERY_CHARS = 250
# allow-list: Unicode letters (covers German umlauts/ß), digits, whitespace,
# and common punctuation. Everything else (control characters, zero-width
# characters, emoji, angle brackets / markup) is rejected.
_QUERY_ALLOWED_PUNCT = set(".,;:!?()[]{}„“«»\"'’`-–—/&%+*#@=_|~°§$€")


def validate_user_query(query: str) -> str:
    """Sanitize a user query; returns the trimmed query or raises
    HTTPException 400 with a clear German message. Applied to every
    user-facing query field before any retrieval or decision-model work."""
    q = (query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Die Suchanfrage ist leer.")
    if len(q) > MAX_QUERY_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Die Suchanfrage ist zu lang (maximal {MAX_QUERY_CHARS} Zeichen). "
                   "Bitte kürzen Sie die Anfrage.")
    for ch in q:
        if ch.isspace():
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("L") or cat.startswith("N"):
            continue
        if ch in _QUERY_ALLOWED_PUNCT:
            continue
        raise HTTPException(
            status_code=400,
            detail="Die Suchanfrage enthält unzulässige Zeichen. Bitte nur "
                   "Buchstaben, Zahlen und übliche Satzzeichen verwenden.")
    return q


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



def _carry_over_prior_docs(req: Any, turn: dict, result: dict) -> None:
    """Facet amendment (change: request-thread-facets): the prior request's
    selected documents (sealed context `top_docs`) persist in the answer:
    ranked AFTER the new hits, capped at 5, marked
    `via: "aus Ihrer vorherigen Anfrage"` — dedup by oparlKey. On an empty
    new search the carry-over set alone remains the answer (no topic
    jump)."""
    prior_docs = []
    try:
        from src.kg.kgFollowups import open_state
        rt = getattr(req, "thread", None)
        if isinstance(rt, dict) and rt.get("state") and rt.get("session_id"):
            prior = open_state(rt["state"], str(rt["session_id"])[:64]) or {}
            prior_docs = (prior.get("top_docs") or [])[:5]
    except Exception as exc:  # noqa: BLE001
        _kg_log.warning("carry-over open_state failed: %s", exc)
        return
    if not prior_docs:
        return
    top = result.get("top_files") or []
    present = {tf.get("oparlKey") for tf in top}
    adds = [k for k in prior_docs if k and k not in present][:5]
    if not adds:
        return
    missing_sids = {k: None for k in adds}
    try:
        from src.db import get_engine
        import sqlalchemy as sa
        with get_engine(readonly=True).connect() as c:
            rows = c.execute(sa.text(
                'SELECT sid, "oparlKey", name, filename, "oparlId", '
                'downloadurl, date FROM "File" WHERE "oparlKey" = ANY(:ks)'),
                {"ks": adds}).fetchall()
            missing_sids = {r[1]: r for r in rows}
    except Exception as exc:  # noqa: BLE001
        _kg_log.warning("carry-over file lookup failed: %s", exc)
        return
    for k in adds:
        r = missing_sids.get(k)
        if not r:
            continue
        # change: fix-followup-deixis — the carried entries MUST carry sid
        # (timeline_stage / graph build file_sids from top_files entries)
        top.append({
            "sid": r[0], "oparlKey": k, "name": r[2], "fileName": r[3],
            "downloadurl": r[5] or r[4], "oparlId": r[4], "date": r[6],
            "distance": None, "match": {},
            "via": "aus Ihrer vorherigen Anfrage",
        })
    result["top_files"] = top


def _kg_enrich(result: dict, query: str, session_id: str) -> None:
    """kg-app-integration: related documents + followups/clarification
    injected into a stage-1 result (used by /search and /ask)."""
    try:
        from src.kg.kgQueries import related_by_tags
        top = [(tf["oparlKey"], tf.get("distance") or 0.0)
               for tf in result.get("top_files", []) if tf.get("oparlKey")]
        result["related_documents"] = related_by_tags(top)
    except Exception as exc:  # pragma: no cover - kg layer issues
        _kg_log.warning("related_documents failed: %s", exc)
        result["related_documents"] = []
    try:
        from src.kg.kgFollowups import (
            generate_followups, seal_state_or_none,
        )
        all_topics: dict = {}
        for rd in result.get("related_documents", []):
            for t in rd.get("shared_tags") or []:
                all_topics[t] = all_topics.get(t, 0) + 1
        topic_clusters = len([t for t in all_topics if all_topics[t] >= 2])
        state_payload = {
            "q0": query,
            "top_docs": [tf.get("oparlKey") for tf in result.get("top_files", [])][:8],
            "stmt_refs": [],
        }
        is_short_fuzzy = len(query.split()) <= 3
        is_multi_cluster = topic_clusters >= 3
        rand_id = uuid.uuid4().hex
        if is_short_fuzzy and is_multi_cluster:
            _kg_log.info("clarification mode: %d clusters", topic_clusters)
            options: list = []
            seen: set = set()
            for rd in result.get("related_documents", [])[:5]:
                label = None
                for t in rd.get("shared_tags") or []:
                    if t not in seen:
                        label = t
                        seen.add(t)
                        break
                if label:
                    options.append({"topic": label,
                                    "example": rd.get("name") or "",
                                    "shared_tags": rd.get("shared_tags", [])[:3]})
            if len(options) >= 2:
                trace("clarification_mode",
                      reason="short-fuzzy multi-cluster",
                      query_words=len(query.split()),
                      clusters=topic_clusters,
                      topics=[t for t, n in all_topics.items() if n >= 2])
                result["clarification"] = {
                    "message": "Meinst du eines dieser Themen?",
                    "options": options[:5],
                }
                result["followups"] = [
                    o["topic"] + " — " + (o["example"][:60]) for o in options[:5]
                ]
                state_payload["clarifying"] = True
                state_payload["topics"] = [o["topic"] for o in options[:5]]
                if not result.get("state"):  # D7: never clobber a thread token
                    token = seal_state_or_none(state_payload, session_id)
                    if token:
                        result["state"] = token
                        result["state_session"] = session_id
        else:
            topics: list = []
            for rd in result.get("related_documents", [])[:2]:
                topics.extend(rd.get("shared_tags") or [])
            summary_text = ((result.get("summary") or {}).get("text", "")
                            if isinstance(result.get("summary"), dict)
                            else (result.get("summary") or ""))
            # change: fix-gremium-session-docs-thread — generate_followups
            # is an LLM call (~3 s); it needs a summary to ground the
            # questions. Meeting-scope answers (answer_mode list_topics)
            # have none — skip the empty-context call so the /ask round
            # trip stays fast (intent decode + graph build only)
            if summary_text:
                fu = generate_followups(summary_text, statements=None,
                                        topics=list(dict.fromkeys(topics))[:5])
                result["followups"] = fu.get("questions")
            token = seal_state_or_none(state_payload, session_id)
            if token and not result.get("state"):  # D7: thread token wins
                result["state"] = token
                result["state_session"] = session_id
    except Exception as exc:  # pragma: no cover
        _kg_log.warning("kg followup/related failed: %s", exc)



@app.get("/file-proxy/{oparl_key}")
def file_proxy(oparl_key: str):
    """kg-app-integration: stream a RIS file through our server so the
    browser never talks to cal server (web1/web2) directly — the F5/BIG-IP
    session cookies (TS01ea880d etc.) the RIS sets belong to a foreign
    origin; proxying avoids them entirely.

    The File row carries the resolved downloadurl; we stream the bytes
    and strip the RIS response headers (cookies, P3P, VS). Cached
    client-side for one hour."""
    import requests as _requests
    from src.db import get_engine as _ge
    row = None
    try:
        e = _ge(readonly=True)
        with e.connect() as c:
            row = c.execute(text(
                'SELECT downloadurl, filename, name FROM "File" WHERE "oparlKey" = :k'),
                {"k": oparl_key}).fetchone()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}")
    if row is None:
        raise HTTPException(status_code=404, detail="Datei (oparlKey) nicht gefunden")
    url = row.downloadurl
    if not url:
        raise HTTPException(status_code=404, detail="Datei hat keinen Download-Link")
    try:
        upstream = _requests.get(url, timeout=120, stream=True)
        upstream.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"fremder Server nicht erreichbar: {exc}")
    # stream without upstream headers (cookies stripped)
    filename = row.filename or f"{oparl_key}.pdf"
    from urllib.parse import quote as _quote
    headers = {
        "Content-Type": upstream.headers.get("Content-Type", "application/pdf"),
        "Content-Disposition": f"inline; filename*=UTF-8''{_quote(filename)}",
        "Cache-Control": "public, max-age=3600",
    }
    if upstream.headers.get("Content-Length"):
        headers["Content-Length"] = upstream.headers["Content-Length"]
    from fastapi.responses import StreamingResponse
    return StreamingResponse(upstream.iter_content(chunk_size=64 * 1024),
                             status_code=upstream.status_code, headers=headers)


@app.post("/search")
def search(req: SearchRequest) -> Dict[str, Any]:
    """Recall stage only (change: progressive-frontend-rendering): returns
    top_files, matched_entities, facets, applied_filters + sessionId.
    Timeline and graph follow via POST /timeline and POST /graph."""
    query = validate_user_query(req.query)  # change: sanitize-queries…
    _trace_query("search", query, top_k=req.top_k, summarize=req.summarize,
                 filters=len(req.filters or []), thread=bool(req.thread))
    from src.db import get_engine as _ge  # noqa: F401 (import guard)

    try:
        session = get_db_session()
    except Exception as exc:  # pragma: no cover - db down
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}")

    # kg-app-integration D7: thread turn FIRST — effective query decided
    # before recall (concat on followup, new thread after the 5-turn budget)
    req_thread = getattr(req, "thread", None)
    kg_on = app.state.kg_app_integration
    turn = None
    if kg_on:
        try:
            turn = _thread_turn(session, query, req_thread)
            query = turn["effective_query"]
        except Exception as exc:  # thread layer must never break search
            _kg_log.warning("thread turn failed: %s", exc)

    # change: rework-search-result-cards — additive boolean for the UI's
    # related-hints card: the topic focus (kg topic above the threshold)
    # enables a topical summary, in which case the refinement-hints card
    # is NOT rendered. Cheap query-side check on the /search path.
    try:
        from src.kg.kgQueries import topic_focus_for_query as _tfq
        result_focus = _tfq(query)
    except Exception:  # pragma: no cover
        result_focus = None

    try:
        result = search_stage(
            session, query, top_k=req.top_k,
            filters=req.filters, signals=req.signals,
        )
        if req.summarize:
            _run_summarizer(session, result)
    except FilterError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        session.close()

    session_id = uuid.uuid4().hex
    if kg_on and turn is not None:
        # chips mode on weak recall (D7): top distance above the floor
        top_files = result.get("top_files") or []
        # Weak recall (D7): no hybrid matches at all, or every entity
        # score under the lexical-significance floor. Cross-check with
        # live data 2026-11-20: topical queries score 0.04+ per entity,
        # gibberish ("qwertyui xzz blorb") maxes ~0.016.
        entities = result.get("matched_entities") or []
        max_entity = max(
            (float(e.get("score") or 0.0) for e in entities),
            default=0.0)
        weak = (not top_files
                or max_entity < KG_RECALL_FLOOR)
        if weak and not turn["forced_break"]:
            _apply_chips_mode(turn, result)
        else:
            _apply_thread_to_result(turn, result, top_files)
            _kg_enrich(result, query, session_id)   # after session_id exists
    elif app.state.kg_app_integration:
        _kg_enrich(result, query, session_id)   # kg-app-integration: after session_id exists
    _sessions[session_id] = {
        "query": query,
        "filters": req.filters or [],
        "stage1": result,      # full stage-1 payload (top_files with sids)
        "timeline": None,      # filled by POST /timeline
        "graph": None,         # filled by POST /graph (stage lock-guarded)
        "result": result,      # client-facing fields; /summarize mutates in place
        "stage_lock": threading.Lock(),
    }
    result["sessionId"] = session_id
    result["topical_summary"] = result_focus is not None
    _trace_response("search", result)
    return result


class AskRequest(BaseModel):
    query: str = Field(min_length=1)
    session_id: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=100)
    signals: Optional[Dict[str, bool]] = None
    summarize: bool = True
    thread: Optional[Dict[str, Any]] = None  # D7: {state, session_id|fresh}
    # change: fix-gremium-session-docs-thread — chip picks are transmitted
    # as OPTION SELECTION, not as text input: {topic, example?} resolved by
    # the backend against the sealed thread (follow-up classification is
    # deterministic here — the option WAS offered by the backend).
    option: Optional[Dict[str, Any]] = None


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

    query = validate_user_query(req.query)  # change: sanitize-queries…
    _trace_query("ask", query, top_k=req.top_k, summarize=req.summarize,
                 session=bool(req.session_id), thread=bool(req.thread))
    try:
        session = get_db_session()
    except Exception as exc:  # pragma: no cover - db down
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}")

    # kg-app-integration D7: /ask also participates in query threads.
    # change: fix-gremium-session-docs-thread — a gremium-session query is
    # HEAD OF CHAIN: no thread turn (context history resets), no
    # effective-query concatenation. Pre-check via the gremium slot
    # vocabulary + session date frame ("letzte sitzung", month) — cheap DB
    # scan, no model call.
    kg_on = app.state.kg_app_integration
    turn = None
    gremium_head = False
    if kg_on:
        try:
            from src.pgIntentRouter import is_gremium_session_query
            gremium_head = is_gremium_session_query(query)
        except Exception as exc:
            _kg_log.warning("gremium precheck failed: %s", exc)
    decoded_topic_follow = None
    if kg_on and not gremium_head:
        opt = getattr(req, "option", None)
        if isinstance(req.thread, dict) and isinstance(opt, dict) and opt.get("topic"):
            # change: fix-gremium-session-docs-thread — option selection =
            # deterministic follow-up turn (backend offered the option → no
            # classification call); helper seals the advanced thread
            try:
                turn = _option_turn(req, query)
                if turn:
                    if turn.get("facet") == "gremium" and turn.get("slot_term"):
                        # change: request-thread-facets — slot fill: the
                        # option selection resolved the body; the scoped
                        # gremium request runs (resolve_gremium inside the
                        # routed handler) with that slot term — no concat
                        grem = resolve_gremium_for_slot(session,
                                                        turn["slot_term"],
                                                        req.option)
                        if grem:
                            req.__dict__["_slot_forced"] = grem
                    query = turn["effective_query"]
            except Exception as exc:
                _kg_log.warning("option selection failed: %s", exc)
        else:
            # change: fix-followup-deixis — ONE decode round decides
            # EVERYTHING: the /ask runs the decode FIRST (with the previous
            # query activating the topic_follow slot question); the result
            # is forced into the router (no second decode) and threads
            # through the thread turn's classification (model decision
            # wins over the lexicon)
            prev_q = None
            try:
                from src.kg.kgFollowups import open_state as _open
                if isinstance(req.thread, dict) and req.thread.get("state"):
                    prior = _open(req.thread["state"],
                                  str(req.thread.get("session_id") or "")[:64]) or {}
                    turns = (prior.get("thread") or {}).get("turns") or []
                    prev_q = (turns or [])[-1] if turns else None
                    prev_q = prev_q if prev_q != query else None
            except Exception:
                prev_q = None
            try:
                from src.pgIntentRouter import IntentRouter
                decoded_early = IntentRouter().decode(query, prev_query=prev_q)
            except Exception as exc:  # thread layer must never break ask
                _kg_log.warning("early decode failed: %s", exc)
                decoded_early = None
            # change: fix-followup-deixis — the topic_follow slot answer
            # (nachfrage) overlays the deictic-lexicon classification
            if decoded_early:
                model_says = (((decoded_early.get("slots") or {})
                               .get("topic_follow")) == "nachfrage")
                # deictic lexicon stays as an OR-fallback: the model can
                # answer "neues Thema" for a clear pronoun reference (live
                # "wo wird es gebaut" — safety first)
                from src.pgIntentRouter import _is_deictic as _deix
                model_followup = model_says or _deix(query)
                ROUTER_FORCE["ctx"] = {
                    "forced_intent": decoded_early["intent"],
                    "slots": decoded_early.get("slots") or {},
                    "scores": decoded_early.get("scores") or {},
                }
            else:
                model_followup = None
            try:
                turn = _thread_turn(session, query, req.thread,
                                    model_followup=model_followup)
                query = turn["effective_query"]
            except Exception as exc:  # thread layer must never break ask
                _kg_log.warning("thread turn (ask) failed: %s", exc)

    # change: request-thread-facets — the gremium SLOT FILL (option
    # selection) forces the routed intent + slot: no decode, the option
    # decided it
    if turn is not None and turn.get("facet") == "gremium" and \
            turn.get("slot_term"):
        ROUTER_FORCE["ctx"] = {"forced_intent": "ask_gremium_recent",
                         "slots": {"gremium": turn["slot_term"].lower()}}
        try:
            result = route_ask(
                session, turn["slot_term"], top_k=req.top_k,
                signals=req.signals, summarize=req.summarize,
                search_fn=_stage1_search_fn)
            result["slot_filled"] = True
        finally:
            ROUTER_FORCE["ctx"] = None
            session.close()
    else:
        ROUTER_FORCE["ctx"] = None
        # change: fix-followup-deixis — the previous query (the last sealed
        # thread turn) activates the topic_follow slot question: the model
        # decides nachfrage / neues Thema per request
        prev_q = None
        try:
            from src.kg.kgFollowups import open_state as _open
            if isinstance(req.thread, dict) and req.thread.get("state"):
                prior = _open(req.thread["state"],
                              str(req.thread.get("session_id") or "")[:64]) or {}
                turns = (prior.get("thread") or {}).get("turns") or []
                prev_q = (turns or [])[-1] if turns else None
                prev_q = prev_q if prev_q != query else None
        except Exception:
            prev_q = None
        try:
            result = route_ask(
                session, query, top_k=req.top_k,
                signals=req.signals, summarize=req.summarize,
                search_fn=_stage1_search_fn,
                prev_query=prev_q,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        finally:
            session.close()

    session_id = req.session_id or uuid.uuid4().hex
    if kg_on and turn is not None:
        resolved_intent = result.get("intent") or "search_topic"
        if result.get("slot_filled"):
            # change: request-thread-facets — a slot-filled gremium request
            # is a REAL scoped answer (meeting scope), never chips mode: the
            # options resolved the slot, so the scope is complete
            _apply_thread_to_result(turn, result, result.get("top_files"))
            precomputed_graph = result.pop("graph", None)
            _sessions[session_id] = {
                "query": turn["slot_term"], "filters": [], "intent": resolved_intent,
                "slots": {"gremium": turn["slot_term"].lower()},
                "stage1": result, "timeline": None, "graph": precomputed_graph,
                "result": result, "stage_lock": threading.Lock(),
            }
            result["sessionId"] = session_id
            _trace_response("ask", result)
            return result
        # change: request-thread-facets — slot-filling OPTIONS when the
        # intent is clear but a required slot is unresolvable: instead of
        # an unscoped/guessed search the backend offers the known bodies
        # (bounded: ≤ 12, primary bodies first)
        from src.pgIntentRouter import gremium_slot_options
        opts = gremium_slot_options(session, query, result)
        _kg_log.info("ask options eval: opts=%s intent=%s", bool(opts), resolved_intent)
        if opts:
            # change: request-thread-facets — the OPTIONS response itself
            # is not an option turn: the thread turn of THIS request
            # (already the seeded history) continues as-is
            turn2 = turn
            result = {
                "query": query, "intent": resolved_intent,
                "mode": "options", "options": opts, "sessionId": session_id,
                "thread": result.get("thread"),
                "state": result.get("state"),
                "state_session": result.get("state_session"),
                "thread_reset": True,
            }
            _apply_thread_to_result(turn2, result, [])
            _sessions[session_id] = {
                "query": query, "filters": [], "intent": resolved_intent,
                "slots": {}, "stage1": {"query": query, "top_files": []},
                "timeline": None, "graph": None, "result": result,
                "stage_lock": threading.Lock(),
            }
            _kg_log.info("ask options mode: intent=%s facet=gremium",
                         resolved_intent)
            _trace_response("ask", result)
            return result
        # change: request-thread-facets — chips mode back to the D7 weak-
        # recall trigger only: a successful gremium scope (meeting view,
        # slot fill) is a REAL answer, never chips; "non_thematic" alone is
        # not a break condition (that regressed the gremium view: everything
        # popped into a chips payload)
        top_files = result.get("top_files") or []
        entities = result.get("matched_entities") or []
        max_entity = max(
            (float(e.get("score") or 0.0) for e in entities), default=0.0)
        # change: request-thread-facets — a successful gromium answer
        # (meeting scope, answer_mode list_topics) is NEVER chips mode —
        # even without matched entities (the gremium view carries no
        # entity signals). weak is only for the topical path.
        gremium_view = (resolved_intent == "ask_gremium_recent"
                        and result.get("answer_mode") == "list_topics")
        weak = ((not top_files or max_entity < KG_RECALL_FLOOR)
                and not gremium_view)
        empty = not (top_files or result.get("topics"))
        if weak or turn["forced_break"] or (empty and not result.get("topics")):
            _apply_chips_mode(turn, result)
            if not turn["forced_break"]:
                result.pop("thread_reset", None)
            result["sessionId"] = session_id
            _kg_log.info("ask chips mode: intent=%s empty=%s", resolved_intent, empty)
            _sessions[session_id] = {
                "query": query, "filters": [], "intent": resolved_intent,
                "slots": {}, "stage1": {"query": query, "top_files": []},
                "timeline": None, "graph": None, "result": result,
                "stage_lock": threading.Lock(),
            }
            _trace_response("ask", result)
            return result
        _apply_thread_to_result(turn, result, result.get("top_files"))
        if turn.get("classification", {}).get("action") == "followup":
            # change: request-thread-facets — facet amendment: the prior
            # request's selected documents persist (best-of carry-over),
            # ranked after the new hits and marked "via"
            _carry_over_prior_docs(req, turn, result)

    # meeting-centric answers (D10) build their graph synchronously in the
    # router — stash it as the precomputed graph stage instead of sending
    # it in the stage-1 response (change: progressive-frontend-rendering)
    precomputed_graph = result.pop("graph", None)
    _sessions[session_id] = {
        "query": query,
        "filters": result.get("applied_filters") or [],
        "intent": result.get("intent"),
        "slots": result.get("slots") or {},
        "stage1": result,           # full stage-1 payload (top_files with sids)
        "timeline": None,           # filled by POST /timeline
        "graph": precomputed_graph, # precomputed (meeting mode) or filled by POST /graph
        "result": result,           # client-facing fields; /summarize mutates in place
        "stage_lock": threading.Lock(),
    }
    session_id = session_id or uuid.uuid4().hex
    # change: fix-gremium-session-docs-thread (task 7.3) — a gremium
    # session view (list_topics) gets NO enrichment: no related_documents,
    # no chips, no followups — topics + session files only
    if result.get("answer_mode") != "list_topics":
        _kg_enrich(result, query, session_id)
    else:
        result["thread_reset"] = True   # head of chain: context cleared
    result["sessionId"] = session_id
    _trace_response("ask", result)
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


class FollowupRequest(BaseModel):
    question: str = Field(min_length=1)
    state: str = Field(min_length=1)
    session_id: str


@app.post("/followup")
def followup(req: FollowupRequest) -> Dict[str, Any]:
    """kg-app-integration: follow-up turn with sealed state.

    Opens the state token, runs the scoped pipeline (search + summary
    grounded in the prior round's statement context), and returns the
    new answer, 3–5 fresh follow-ups and a fresh sealed token."""
    query = validate_user_query(req.question)
    _trace_query("followup", query, session=req.session_id)
    if req.session_id and any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        for c in req.session_id
    ):
        raise HTTPException(status_code=400, detail="Ungültige Session-ID.")
    try:
        from src.kg.kgFollowups import open_state
        state = open_state(req.state, req.session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiger oder abgelaufener Sitzungs-Token: {exc}",
        )
    except Exception as exc:
        _kg_log.warning("followup open_state failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Ungültiger Sitzungs-Token.",
        )

    try:
        session = get_db_session()
    except Exception as exc:  # pragma: no cover - db down
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}")

    try:
        result = search_stage(session, query, top_k=req.top_k if hasattr(req, "top_k") else 10)
        if app.state.kg_app_integration:
            try:
                from src.kg.kgFollowups import (
                    generate_followups, seal_state_or_none,
                )
                # grounding from prior round: seed via kg statements for the
                # state's top docs
                from src.kg.kgQueries import (
                    file_sid_for_key, statements_for_papers,
                )
                sids = file_sid_for_key((state.get("top_docs") or [])[:6])
                pairs = statements_for_papers(
                    [v for v in sids.values() if v])
                faketopics = list(state.get("topics") or [])[:5]
                fu = generate_followups(
                    query, statements=list(pairs.values())[:2],
                    topics=faketopics,
                )
                # questions rendered as a scoped response, alto the token chain
                state_payload = {
                    "q0": state.get("q0") or query,
                    "top_docs": [tf.get("oparlKey") for tf in (result.get("top_files") or [])][:8],
                    "stmt_refs": [v.get("pair_id") for v in pairs.values()][:6],
                    "topics": faketopics,
                }
                token = seal_state_or_none(state_payload, req.session_id)
                if token:
                    result["followups"] = fu.get("questions")
                    result["state"] = token
                    result["state_session"] = req.session_id
                    if req.state != token:
                        result["state_refreshed"] = True
            except Exception as exc:  # pragma: no cover
                _kg_log.warning("followup grounding failed: %s", exc)
        if req.__class__.__dict__.get("summarize") or True:
            _run_summarizer(session, result)
    except FilterError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        session.close()

    if req.session_id not in _sessions:
        _sessions[req.session_id] = {
            "query": query, "filters": [], "stage1": result, "timeline": None,
            "graph": None, "result": result,
            "stage_lock": threading.Lock(),
        }
    result["sessionId"] = req.session_id
    _trace_response("followup", result)
    return result


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
