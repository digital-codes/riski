
# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.<name>``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass
import os
import json
import requests
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np
from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine, MetaData, Table, select, and_, or_, func, Column, Integer, String
from sqlalchemy import text as sa_text_imp
from sqlalchemy.orm import sessionmaker

import numpy as np
from pgvector.sqlalchemy import Vector

# Import helper to create DB engine
from sqlalchemy import create_engine  # needed for openDb

import requests

import time
from functools import lru_cache

# ----------------------------------------------------------------------
# Shared layers: DB (read-only engine + config) and remote model client
# ----------------------------------------------------------------------
from src.search.apiTrace import trace
from src.db import get_engine, _load_private
from src.timing import timed

log = None  # set by _ensure_log()


def _ensure_log():
    """Lazily create the module logger (debug chatter hidden by default)."""
    global log
    if log is None:
        import logging
        log = logging.getLogger("riski.timeline")
        if not log.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            log.addHandler(handler)
            log.setLevel(logging.WARNING)
    return log
from src import remote
from src.update.pgChunks import chunk_text, document_text


# Configuration
EMBEDDING_API_URL = None
EMBEDDING_MODEL = None
EMBEDDING_API_KEY = None
TOP_K = 100
TIMELINE_WINDOW_DAYS = 30


def _get_setting(attr: str, env_key: str):
    """Resolve a setting from private.py, then environment variables."""
    pr = _load_private()
    if pr is not None:
        value = getattr(pr, attr, None)
        if value:
            return value
    return os.getenv(env_key) or None


# test reranking with a small local model
try:
    RERANKING_API_URL = _get_setting("RERANK_URL", "RERANK_URL")
    RERANKING_MODEL = _get_setting("RERANK_MDL", "RERANK_MDL")
    RERANKING_API_KEY = _get_setting("RERANK_KEY", "RERANK_KEY")
    if RERANKING_API_URL is None:
        raise AttributeError("no reranking configuration")
    if "rerank" in RERANKING_API_URL.lower():
        RERANK_MODE = "rerank"
    else:
        RERANK_MODE = "chat"
except AttributeError:
    RERANKING_API_URL = None
    RERANKING_MODEL = None
    RERANKING_API_KEY = None
    RERANK_MODE = None

# summary model configuration is handled by src.remote (SUMMARY_*/CHAT_*)
SUMMARY_API_URL = remote.CHAT_BASE_URL
SUMMARY_MODEL = remote.CHAT_MODEL
SUMMARY_API_KEY = remote.CHAT_API_KEY

def call_reranking_chat_model(query: str, content: str) -> float:
    """
    Call local reranking model and return relevance score
    Adjust based on your actual API endpoint
    """
    if RERANKING_API_URL == None:
        _ensure_log().debug("Reranking API URL not configured, skipping reranking")
        return 1.0  # If no reranking API is configured, return a default relevance score of 1.0 (keep all results)
    lang = "German"  # Assuming the content and query are in German
    headers = {"Authorization": f"Bearer {RERANKING_API_KEY}"} if RERANKING_API_KEY else {}
    # instruction templates from the shared prompt registry
    # (change: centralize-llm-instruction-prompts)
    rerank_prompt = remote.get_prompt("rerank-relevance").format(lang=lang)
    rerank_query = remote.get_prompt("rerank-relevance-user").format(
        query=query, content=content,
    )
    _ensure_log().debug(f"Calling reranking model with query: {query} and content length: {len(content)}")  # Debugging line
    payload = {"model": RERANKING_MODEL, "temperature": 0.1, "random_seed": 42,
               "messages": [{"role": "system", "content": rerank_prompt},
                            {"role": "user", "content": rerank_query}]}
    try:
        response = requests.post(RERANKING_API_URL, json=payload, headers=headers)
        # handle 429 too many requests error by retrying after a delay. get delay from response headers if available, otherwise default to 5 seconds
        if response.status_code == 429:
            for attempt in range(5):  # Retry up to 5 times
                retry_after = int(response.headers.get("Retry-After", 5))
                _ensure_log().warning(f"Reranking model rate limited; retrying after {retry_after}s")
                time.sleep(retry_after)
                response = requests.post(RERANKING_API_URL, json=payload, headers=headers)
                if response.status_code != 429:
                    break
        response.raise_for_status()
        result = response.json()
    except requests.RequestException as exc:
        remote.log_llm_call(
            endpoint=RERANKING_API_URL, model=RERANKING_MODEL, payload=payload,
            result=None, status="error",
            prompt_id="rerank-relevance", call_id="pgTimeline.call_reranking_chat_model.1",
            error=str(exc),
        )
        raise
    remote.log_llm_call(
        endpoint=RERANKING_API_URL, model=RERANKING_MODEL, payload=payload,
        result=result, status="ok",
        prompt_id="rerank-relevance", call_id="pgTimeline.call_reranking_chat_model.1",
    )
    # Adjust based on actual API response structure
    if isinstance(result, dict) and result.get("choices") and isinstance(result["choices"], list) and len(result["choices"]) > 0:
        score_str = result["choices"][0].get('message', {}).get('content', '0')
        try:
            score = float(score_str.strip())
            return score
        except ValueError:
            _ensure_log().debug(f"Could not parse relevance score from model response: '{score_str}'")
            return 0.0
    else:
        _ensure_log().debug(f"Unexpected response format from reranking model: {result}")
        return 0.0 

@timed
def call_reranking_model(query: str, content: list[str], top_n=0) -> list[float]:
    """
    Call local reranking model and return relevance score
    Adjust based on your actual API endpoint
    """
    if RERANKING_API_URL == None:
        _ensure_log().debug("Reranking API URL not configured, skipping reranking")
        return [1.0 for x in content]  # If no reranking API is configured, return a default relevance score of 1.0 (keep all results)
    headers = {"Authorization": f"Bearer {RERANKING_API_KEY}"} if RERANKING_API_KEY else {}
    # adjust top_n if zero
    top_n = top_n if top_n > 0 else len(content)
    # with reranker we don't need a prompt, just the query and the content
    params = {"model": RERANKING_MODEL,  "random_seed": 42, 
                      "top_n": top_n, "query": query, "documents": content, 
                      "return_embeddings": False, "return_documents": False,
                      "max_doc_length": 4096}
    #print(f"Reranking model params: {params}")  # Debugging line
    response = requests.post(
        RERANKING_API_URL,
        json=params,
        headers=headers
    )
    # handle 429 too many requests error by retrying after a delay. get delay from response headers if available, otherwise default to 5 seconds
    if response.status_code == 429:
        for attempt in range(5):  # Retry up to 5 times
            retry_after = int(response.headers.get("Retry-After", 5))
            _ensure_log().warning(f"Reranking model rate limited; retrying after {retry_after}s")
            time.sleep(retry_after)
            response = requests.post(
                RERANKING_API_URL,
                json=params,
                headers=headers
            )
            if response.status_code != 429:
                break
    response.raise_for_status()
    result = response.json()
    # Adjust based on actual API response structure
    # llamacpp repsonse is like this:{
    #     "model": "jina-reranker-v3.5-Q4_K_M",
    #     "object": "list",
    #     "results": [
    #         {
    #             "index": 0,
    #             "relevance_score": 0.9999481439590454
    #         },
    #         {
    #             "index": 2,
    #             "relevance_score": 4.775548950419761e-05
    #         }
    #     ],
    #     "usage": {
    #         "prompt_tokens": 196,
    #         "total_tokens": 196
    #     }
    # }
    if isinstance(result, dict) and result.get("results") and isinstance(result["results"], list) and len(result["results"]) > 0:
        scores = []
        # results are ordered by best relevance first, with index indicating the original index of the document in the input list
        # we need to reorder the scores to match the original order of the content list
        for item in result["results"]:
            _ensure_log().debug(f"Reranking model item: {item}")  # Debugging line
            try:
                index = item.get("index")
                score = 1.0 if item.get("relevance_score") is None else float(item.get("relevance_score", 1.0))
                scores.append((index, score))
            except ValueError:
                _ensure_log().debug(f"Could not parse relevance score from model response: '{item}'")
                scores.append((index, 1.0))
            _ensure_log().debug(f"Reranking model item: index={index}, score={score}")  # Debugging line
        # reorder scores to match the original order of the content list
        scores.sort(key=lambda x: x[0])
        return [score for index, score in scores]
    else:
        _ensure_log().debug(f"Unexpected response format from reranking model: {result}")
        return [1.0 for x in content]  # Return a list of default relevance scores if response format is unexpected


######### 


Base = declarative_base()

# Vector Model
class Embeddings(Base):
    """Embeddings table with vector column (requires pgvector extension)"""
    __tablename__ = 'contentEmbeddings'
    
    id = Column(Integer, primary_key=True)
    oparlKey = Column(String)
    value = Column(Vector(1024))  # 1024-dimensional vector
    # Assuming you have a vector column named 'embedding'
    # Adjust column name/type based on your schema

# File Model
class File(Base):
    """File table for metadata and content"""
    __tablename__ = 'File'
    
    id = Column(Integer, primary_key=True)
    date = Column(String)
    oparlKey = Column(String)
    name = Column(String)
    downloadurl = Column(String)
    content = Column(String)



@timed(label="pgTimeline.embed_query")
def call_embedding_model(text: str, api_url: str = None, api_key: str = None, model: str = None) -> tuple[list[float], float]:
    """
    Call the shared remote embedding client and return a normalised vector.

    The endpoint/model/key configuration lives in ``src.remote`` (resolved
    from ``private.py`` / environment variables); the arguments are kept for
    API compatibility and override the shared configuration when given.

    Results are cached (LRU, 256 entries, keyed by text+model) — query
    texts repeat far more often than they change, and the remote call is
    the single largest fixed cost of a search (change:
    api-latency-optimization). Only QUERY paths use this helper; bulk
    document-embedding paths call ``remote.embed`` directly.
    """
    return _embed_cached(text, model)


@lru_cache(maxsize=256)
def _embed_cached(text: str, model: str | None) -> tuple[list[float], float]:
    if model:
        vec = remote.embed(text, model=model)
    else:
        vec = remote.embed(text)
    vector = vec.tolist()
    _ensure_log().debug(f"Received vector of length {len(vector)}")  # Debug print to check vector length
    return vector


def clear_embedding_cache() -> None:
    """Drop the query-embedding cache (e.g. after a model/config change)."""
    _embed_cached.cache_clear()

# here, threshold is a distance threshold, so we want to keep vectors with distance <= threshold (i.e. similarity above a certain level)
def filter_by_threshold(vectors_with_scores: list[tuple], threshold: float) -> list[tuple]:
    """Filter vectors above threshold"""
    return [(vec, score) for vec, score in vectors_with_scores if score <= threshold]


def _listwise_config() -> Tuple[bool, int]:
    """Instance config for the listwise chat rerank stage (change:
    fix-hybrid-search-ranking, fragment B): ``(enabled, window)``.
    Enabled by default — it fires only when RERANK_MODE is None (reranking
    dropped, SystemOne decision model owns query understanding) — with
    ``search.listwise_rerank: false`` / ``RISKI_SEARCH__LISTWISE_RERANK``
    as kill switch and ``search.listwise_window`` (default 50) sizing the
    single-call batch. 50 because moments like the minutes
    "Protokoll GR 24.02.2026 TOP 3" fuse at rank 30–45 (name-vector ghost
    matches saturate the top); still ONE chat call (~8k prompt tokens at
    600-char snippets). Explained in docs/search-weights.md (sync rule)."""
    try:
        from src.instanceConfig import section as _sec
        sc = _sec("search")
        return (
            bool(sc.get("listwise_rerank", True)),
            int(sc.get("listwise_window", 25)),
        )
    except Exception:  # noqa: BLE001 - config failure keeps old behaviour
        return (True, 50)


# Truncate what we show the listwise model per candidate (the chunk itself
# can be up to ~7000 chars — pgChunks CHUNK_TARGET/CHUNK_HARD; a few hundred
# chars decide relevance without blowing the context window).
_LISTWISE_SNIPPET_CHARS = 600


def _listwise_snippet(text: str, query: str) -> str:
    """Keyword-centered snippet for the listwise stage (change:
    fix-hybrid-search-ranking). The naive first-600-chars window can leave
    the decisive sentences out (minutes chunks start mid-context with
    '## Abstimmungsergebnis …' and only mention the searched platform
    some hundred chars later). When any query term (≥ 5 chars, lowercased)
    occurs in the text, the window is centred on the first hit — otherwise
    the naive head window applies."""
    flat = " ".join(str(text).split())
    if len(flat) <= _LISTWISE_SNIPPET_CHARS:
        return flat
    low = flat.lower()
    hit = -1
    hit_term = ""
    for term in sorted({t.lower() for t in query.split() if len(t) >= 5},
                       key=len, reverse=True):
        # German compounds: "Bürgerbeteiligungsplattform" appears in the
        # minutes as "Beteiligungsplattform" — walk progressively shorter
        # suffixes of the term until a substring hit (or len < 6)
        probe, term_hit = term, -1
        while len(probe) >= 6:
            term_hit = low.find(probe)
            if term_hit >= 0:
                break
            probe = probe[1:]
        if term_hit >= 0:
            hit, hit_term = term_hit, probe
            break
    if hit < 0:
        return flat[:_LISTWISE_SNIPPET_CHARS]
    half = (_LISTWISE_SNIPPET_CHARS - len(hit_term)) // 2
    start = max(0, hit - half)
    return flat[start:start + _LISTWISE_SNIPPET_CHARS]
# listwise stage: candidates the model did NOT mark relevant get this weak
# rerank score (rejected by the gate unless the lexical override applies;
# they still keep the clamped fallback ordering)
_LISTWISE_NOT_RELEVANT_SCORE = 0.1


def listwise_rerank(
    query: str,
    candidates: List[Tuple[str, Dict[str, Any]]],
    chunks: Dict[str, Optional[int]],
    snippet_lookup,
) -> Dict[str, float]:
    """Listwise chat rerank of fused candidates (change:
    fix-hybrid-search-ranking, fragment B) — plus ONE chat call with the
    numbered snippets (chunk text via ``snippet_lookup``; name as fallback)
    and the query; returns ``{oparlKey: rerank_score}`` for candidates the
    model marked relevant (order → decaying score), empty on any failure
    (the caller then keeps the fused order).

    Active only when ``RERANK_MODE is None`` (reranking dropped in favour
    of the SystemOne decision model) and ``search.listwise_rerank`` is on;
    uses SUMMARY_MDL (``src.remote.chat``) whose prompts live in
    ``config/instruction_prompts.json`` (``rerank-listwise`` /
    ``rerank-listwise-user``). Model output is strict JSON with numbered
    german ids: {"relevant": [...]}; position bias is handled by presenting
    candidates in fused order (small window)."""
    if not candidates:
        return {}
    system = remote.get_prompt("rerank-listwise")
    user_tmpl = remote.get_prompt("rerank-listwise-user")
    lines = []
    for i, (oparlKey, cand) in enumerate(candidates, start=1):
        text = snippet_lookup(oparlKey, chunks.get(oparlKey)) or ""
        if not text:
            text = cand.get("name") or ""
        snippet = _listwise_snippet(text, query)
        lines.append(f"{i}. {snippet}")
    user_msg = user_tmpl.format(query=query, candidates="\n".join(lines))
    try:
        resp = remote.chat(
            [{"role": "system", "content": system},
             {"role": "user", "content": user_msg}],
            temperature=0.0,
            prompt_id="rerank-listwise",
            call_id="pgTimeline.listwise_rerank.1",
        )
        content = resp.get("content") or ""
    except Exception as exc:  # noqa: BLE001 - rerank failure degrades to fused order
        _ensure_log().warning("listwise rerank call failed: %s", exc)
        return {}
    import json as _json
    import re as _re
    m = _re.search(r"\{.*\}", content, _re.DOTALL)
    if not m:
        _ensure_log().warning("listwise rerank: no JSON in model answer")
        return {}
    try:
        data = _json.loads(m.group(0))
        relevant = data.get("relevant") or []
        order = [int(x) for x in relevant if isinstance(x, int) and 1 <= x <= len(candidates)]
    except Exception as exc:  # noqa: BLE001
        _ensure_log().warning("listwise rerank: unparseable JSON (%s)", exc)
        return {}
    out: Dict[str, float] = {}
    n = len(candidates)
    for pos, idx in enumerate(order, start=1):
        oparlKey = candidates[idx - 1][0]
        out[oparlKey] = round(1.0 - 0.5 * (pos - 1) / max(1, n), 4)
    return out


def rerank_gate_decision(
    oparlKey: str,
    fusion_score: float,
    rerank_score: Optional[float],
    cutoff: float,
    lexical_override: bool,
    lexical_keys: set,
) -> Optional[float]:
    """Accept/keep/reject decision after reranking (search_stage).

    Returns the score to keep the file with, or ``None`` to reject.

    change: fix-hybrid-search-ranking — rerank acceptance is gated by
    ``cutoff`` (instance config ``search.rerank_cutoff``). A File that is
    lexically certain (oparlKey in ``lexical_keys``) survives a weak rerank
    score with the merged rank ``fusion × min(rerank, cutoff)``, which is
    strictly below every fully-accepted file, so lexical hits stay in
    ``top_files`` (and remain available to the summarizer) without
    displacing genuinely reranked results. Disable per instance with
    ``search.lexical_rerank_override: false``. Documented in
    ``docs/search-weights.md`` — keep both in sync in the same commit.
    """
    if rerank_score is None or not isinstance(rerank_score, (int, float)):
        # invalid/no rerank score: previous batch-mode behaviour kept the
        # file at its original fusion score (content-less documents)
        return fusion_score
    if rerank_score >= cutoff:
        return fusion_score * rerank_score
    if lexical_override and oparlKey in lexical_keys:
        return fusion_score * min(rerank_score, cutoff)
    return None

@timed
def query_vector_similarity(session, query_vector: list[float], top_k: int = 10) -> list[int]:
    """
    Query PostgreSQL for vector similarity using pgvector
    Requires pgvector extension installed
    """
    # Using cosine similarity (<=> operator in pgvector)
    # Adjust column name based on your schema
    query = session.query(
        Embeddings.oparlKey,
        (Embeddings.value.cosine_distance(query_vector)).label("distance")
    ).order_by("distance").limit(top_k)
    return query.all()



def get_db_session(db_url: str = None):
    """Create and return a new database session on the shared read-only engine."""
    if db_url is None:
        engine = get_engine(readonly=True)
    else:
        engine = create_engine(db_url, future=True)
    Session = sessionmaker(bind=engine)
    return Session()



@timed
def _block_prefix(number):
    if not number:
        return None
    head = str(number).split(".")[0].strip()
    try:
        return int(head)
    except ValueError:
        return None


def _block_reference(number):
    if not number:
        return None
    head = str(number).split(".")[0].strip()
    return f"TOP {head}" if head else None


def agenda_item_seeds(session, matched_entities: List[Dict[str, Any]]) -> List[int]:
    """Sids of agenda items matched by name search (change:
    agenda-sibling-documents) — they become traversal seeds so their block
    documents enter the answer set."""
    keys = [m.get("oparlKey") for m in (matched_entities or [])
            if m.get("type") == "AgendaItem" and m.get("oparlKey")]
    if not keys:
        return []
    from sqlalchemy import text as _text
    rows = session.execute(_text(
        'SELECT sid FROM "AgendaItem" WHERE "oparlKey" = ANY(:k)'),
        {"k": keys}).fetchall()
    return [r[0] for r in rows]


def expand_top_files_by_agenda_block(related_objects, edges, top_files,
                                     query_terms: Optional[List[str]] = None,
                                     text_provider=None) -> List[Dict[str, Any]]:
    """Append agenda-block sibling documents to the answer set (change:
    agenda-sibling-documents). Returns the expanded top_files list.

    Touched blocks: agenda items that carry at least one search-hit file, or
    that were matched by name (their documents arrive as edges to AuxFile
    nodes). For each touched block (same meetingSid + integer number
    prefix) all linked documents of the block's agenda items are appended
    unless already present; entries carry ``distance: None``,
    ``match: None`` and ``via`` = block reference (e.g. 'TOP 13').

    Content reference (verification finding, Knittelberg case): when
    ``query_terms`` is given, a sibling document joins ONLY if its stored
    text (content/chunks via ``text_provider``) contains ALL of the terms —
    block membership alone is not sufficient, since scattered search hits
    across a meeting would otherwise flood the answer set with unrelated
    documents. Without ``query_terms``/``text_provider`` no expansion runs
    (relevance cannot be verified)."""
    seed_keys = {f["oparlKey"] for f in top_files}
    if not query_terms or text_provider is None:
        # without distinctive query terms relevance cannot be verified —
        # no expansion (protects against unrelated-block floods)
        return list(top_files)
    name_seed_agenda = {a["oparlKey"] for a in related_objects.get("AgendaItem", [])
                        if a.get("_name_seed")}

    # agenda item -> linked files (from the edge log); seed File nodes are
    # included so a TOP whose ONLY document is the search hit still counts
    # as touched (its block siblings must be expanded)
    file_by_node: Dict[str, Dict[str, Any]] = {
        f"File_{f['oparlKey']}": f for f in top_files
    }
    for obj in related_objects.get("AuxFile", []):
        file_by_node[f"AuxFile_{obj['oparlKey']}"] = obj
    agenda_files: Dict[str, List[Dict[str, Any]]] = {}
    for e in edges:
        if e.get("relation") != "auxiliaryFile":
            continue
        source, target = e.get("source", ""), e.get("target", "")
        if not source.startswith("AgendaItem_"):
            continue
        obj = file_by_node.get(target)
        if obj is not None:
            agenda_files.setdefault(source, []).append(obj)

    # touched agenda items: carry a seed file, or were matched by name
    touched_blocks: set = set()
    for a in related_objects.get("AgendaItem", []):
        linked = agenda_files.get(f"AgendaItem_{a['oparlKey']}", [])
        if a["oparlKey"] in name_seed_agenda or any(
                o["oparlKey"] in seed_keys for o in linked):
            prefix = _block_prefix(a.get("number"))
            if prefix is not None:
                touched_blocks.add((a.get("meetingSid"), prefix))

    def in_touched_block(a) -> bool:
        prefix = _block_prefix(a.get("number"))
        return prefix is not None and (a.get("meetingSid"), prefix) in touched_blocks

    expanded = list(top_files)
    present = set(seed_keys)
    added = 0
    for a in related_objects.get("AgendaItem", []):
        if not in_touched_block(a):
            continue
        via = _block_reference(a.get("number")) or "TOP"
        for obj in agenda_files.get(f"AgendaItem_{a['oparlKey']}", []):
            if obj["oparlKey"] in present:
                continue  # seed hit or already appended
            if query_terms is not None and text_provider is not None:
                doc_text = (text_provider(obj["oparlKey"]) or "").lower()
                if not all(t in doc_text for t in query_terms):
                    continue  # does not reference the query subject
            present.add(obj["oparlKey"])
            added += 1
            expanded.append({
                "sid": obj["sid"],
                "oparlKey": obj["oparlKey"],
                "name": obj.get("name"),
                "fileName": obj.get("fileName"),
                "downloadurl": obj.get("downloadurl"),
                "oparlId": obj.get("oparlId"),
                "date": obj.get("date"),
                "distance": None,
                "match": None,
                "via": via,
            })
    if added:
        _ensure_log().debug(f"Agenda block expansion: +{added} sibling documents")
    return expanded


def block_expand_top_files(session, result: Dict[str, Any],
                           sess: Optional[Dict[str, Any]] = None) -> None:
    """Expand ``result["top_files"]`` with agenda-block sibling documents,
    in place (change: agenda-sibling-documents).

    Called from the /summarize path: the summarizer consumes
    ``result["top_files"]``, so the expansion must happen there — after the
    search response, possibly before the timeline stage has run. Reuses the
    timeline stage's traversal when available, otherwise runs
    ``find_related_objects`` for the answer set's files plus the
    name-matched agenda items. Idempotent per session via
    ``sess["top_files_expanded"]``.

    Content reference (verification finding, Knittelberg case): sibling
    documents must reference the query subject — the query's stop-term-
    stripped tokens must all appear in the document's stored text. Without
    distinctive tokens no expansion runs.
    """
    if sess is not None and sess.get("top_files_expanded"):
        return
    top_files = result.get("top_files") or []
    if not top_files:
        return

    from sqlalchemy import text as _sqltext

    from src.search.pgHybridSearch import load_stop_terms, _strip_terms_py

    stripped = _strip_terms_py(result.get("query") or "", load_stop_terms())
    query_terms = [w.lower() for w in stripped.split() if len(w) >= 3]

    def text_provider(oparl_key: str) -> Optional[str]:
        # change: unify-file-content-in-chunks — text comes exclusively
        # from File_chunks (the union with File.content double-counted the
        # head chunk of chunked documents)
        return document_text(session, oparl_key)

    stage2 = (sess or {}).get("_stage2")
    if stage2 and stage2.get("related_objects") is not None:
        ro = stage2["related_objects"]
        edges = ro.get("edges", [])
    else:
        file_sids = {f["oparlKey"]: f["sid"] for f in top_files
                     if f.get("oparlKey") and f.get("sid")}
        name_seeds = agenda_item_seeds(session, result.get("matched_entities") or [])
        ro = find_related_objects(session, file_sids, agenda_item_sids=name_seeds)
        edges = ro.get("edges", [])

    if query_terms:
        result["top_files"] = expand_top_files_by_agenda_block(
            ro, edges, top_files, query_terms=query_terms,
            text_provider=text_provider)
    else:
        _ensure_log().debug("Agenda block expansion skipped: no distinctive query tokens")
    if sess is not None:
        sess["top_files_expanded"] = True


def find_related_objects(session, file_sids: List[str],
                         agenda_item_sids: Optional[List[int]] = None) -> Dict[str, List[Dict]]:
    """
    Find all related OParl objects related to the given file sids through junction tables.

    ``agenda_item_sids`` (change: agenda-sibling-documents) adds name-matched
    agenda items as traversal seeds: their nodes, block siblings (same
    meeting, same integer number prefix) and all linked documents enter the
    answer set.

    Traverses the OParl association tables and logs every relationship it
    walks as a typed edge (add-network-view tasks 1.2/1.3). The returned
    dict carries the objects per type plus two extra keys: ``edges`` (the
    typed edge log) and ``_sid_maps`` (sid→oparlKey lookups used for FK
    edges) — both consumed by ``build_graph`` and stripped before output.

    Args:
        session: SQLAlchemy session
        file_sids: Dict mapping File oparlKey → File sid to find related objects for

    Returns:
        Dictionary with object types as keys and lists of related objects
        as values, plus "edges" and "_sid_maps".
    """
    engine = session.get_bind()
    metadata = MetaData()

    # typed edge log: {"source": "Type_key", "target": "Type_key", "relation": ..., "via": ...}
    edges: List[Dict[str, str]] = []
    # invert file_sids (oparlKey → sid) for junction-target resolution
    sid_to_file_key = {sid: key for key, sid in file_sids.items()}

    def log_edge(src_type: str, src_key, relation: str, tgt_type: str, tgt_key, via: str) -> None:
        if src_key is None or tgt_key is None:
            return
        edges.append({
            "source": f"{src_type}_{src_key}",
            "target": f"{tgt_type}_{tgt_key}",
            "relation": relation,
            "via": via,
        })

    
    
    # Load tables
    agenda_tbl = Table('AgendaItem', metadata, autoload_with=engine)
    paper_tbl = Table('Paper', metadata, autoload_with=engine)
    meeting_tbl = Table('Meeting', metadata, autoload_with=engine)
    consultation_tbl = Table('Consultation', metadata, autoload_with=engine)
    organization_tbl = Table('Organization', metadata, autoload_with=engine)
    file_tbl = Table('File', metadata, autoload_with=engine)
    
    # Load association tables
    af_assoc_tbl = Table('AgendaItem__auxiliaryFile__File', metadata, autoload_with=engine)
    pf_assoc_tbl = Table('Paper__auxiliaryFile__File', metadata, autoload_with=engine)
    mf_assoc_tbl = Table('Meeting__auxiliaryFile__File', metadata, autoload_with=engine)
    pc_assoc_tbl = Table('Paper__consultation__Consultation', metadata, autoload_with=engine)
    ma_assoc_tbl = Table('Meeting__agendaItem__AgendaItem', metadata, autoload_with=engine)
    co_assoc_tbl = Table('Consultation__organization__Organization', metadata, autoload_with=engine)
    po_assoc_tbl = Table('Paper__underDirectionOf__Organization', metadata, autoload_with=engine)
    
    related_objects = {
        "AgendaItem": [],
        "Paper": [],
        "Meeting": [],
        "Consultation": [],
        "Organization": [],
        "Person": [],
        "Body": [],
        "Location": [],
        "AuxFile": []  
    }

    # 1. Find AgendaItems connected to Files
    stmt = (
        select(
            agenda_tbl.c.sid,
            agenda_tbl.c.id,
            agenda_tbl.c.oparlKey,
            agenda_tbl.c.oparlId,
            agenda_tbl.c.name,
            agenda_tbl.c.start_date,
            agenda_tbl.c.end_date,
            agenda_tbl.c.meetingSid,
            agenda_tbl.c.number,
            agenda_tbl.c.result,
            af_assoc_tbl.c.tgtSid.label("fileSid"),
        )
        .select_from(
            af_assoc_tbl.join(
                agenda_tbl, af_assoc_tbl.c.srcSid == agenda_tbl.c.sid
            )
        )
        .where(af_assoc_tbl.c.tgtSid.in_(file_sids.values()))
    )
    with engine.connect() as conn:
        agenda_items = conn.execute(stmt).fetchall()

    for row in agenda_items:
        related_objects["AgendaItem"].append({
            "sid": row.sid,
            "id": row.id,
            "oparlKey": row.oparlKey,
            "oparlId": row.oparlId,
            "name": row.name,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "meetingSid": row.meetingSid,
            "number": row.number,
            "result": row.result
        })
        log_edge("AgendaItem", row.oparlKey, "auxiliaryFile", "File",
                 sid_to_file_key.get(row.fileSid), "AgendaItem__auxiliaryFile__File")

    _ensure_log().debug(f"Found {len(related_objects['AgendaItem'])} agenda items related to files")  # Debugging line

    # 1.a change: agenda-sibling-documents — agenda items matched by name
    # search arrive as extra seeds; load them into the traversal so their
    # nodes and documents enter the answer set
    agenda_item_sids = agenda_item_sids or []
    known_agenda_sids = {a["sid"] for a in related_objects["AgendaItem"]}
    seed_agenda_sids = [s for s in agenda_item_sids if s not in known_agenda_sids]
    if seed_agenda_sids:
        stmt = (
            select(
                agenda_tbl.c.sid,
                agenda_tbl.c.id,
                agenda_tbl.c.oparlKey,
                agenda_tbl.c.oparlId,
                agenda_tbl.c.name,
                agenda_tbl.c.start_date,
                agenda_tbl.c.end_date,
                agenda_tbl.c.meetingSid,
                agenda_tbl.c.number,
                agenda_tbl.c.result,
            )
            .where(agenda_tbl.c.sid.in_(seed_agenda_sids))
        )
        with engine.connect() as conn:
            for row in conn.execute(stmt).fetchall():
                related_objects["AgendaItem"].append({
                    "sid": row.sid,
                    "id": row.id,
                    "oparlKey": row.oparlKey,
                    "oparlId": row.oparlId,
                    "name": row.name,
                    "start_date": row.start_date,
                    "end_date": row.end_date,
                    "meetingSid": row.meetingSid,
                    "number": row.number,
                    "result": row.result,
                    "_name_seed": True  # change: agenda-sibling-documents
                })
        _ensure_log().debug(f"Added {len(related_objects['AgendaItem']) - len(known_agenda_sids)} name-matched agenda items as traversal seeds")

    # 1.b change: agenda-sibling-documents — block expansion: all agenda
    # items of the same meeting sharing the integer prefix of the number
    # (TOP 13.2 -> 13, 13.1, 13.2, 13.3, ...) belong to the same topic
    # block; their documents are collected as AuxFile. Other agenda items
    # of the meeting (different prefix) are unrelated.
    def _block_prefix(number):
        if not number:
            return None
        head = str(number).split(".")[0].strip()
        try:
            return int(head)
        except ValueError:
            return None

    all_agenda = related_objects["AgendaItem"]
    # group collected TOPs by (meetingSid, block prefix)
    blocks: Dict[tuple, List[Dict[str, Any]]] = {}
    for a in all_agenda:
        prefix = _block_prefix(a.get("number"))
        if prefix is None:
            continue
        blocks.setdefault((a.get("meetingSid"), prefix), []).append(a)

    collected_agenda_sids = {a["sid"] for a in all_agenda}
    block_siblings: List[Dict[str, Any]] = []
    for (meeting_sid, prefix), members in blocks.items():
        member_sids = {m["sid"] for m in members}
        # find sibling TOPs of the same block not yet collected
        stmt = (
            select(
                agenda_tbl.c.sid,
                agenda_tbl.c.id,
                agenda_tbl.c.oparlKey,
                agenda_tbl.c.oparlId,
                agenda_tbl.c.name,
                agenda_tbl.c.start_date,
                agenda_tbl.c.end_date,
                agenda_tbl.c.meetingSid,
                agenda_tbl.c.number,
                agenda_tbl.c.result,
            )
            .where(
                agenda_tbl.c.meetingSid == meeting_sid,
                agenda_tbl.c.sid.not_in(collected_agenda_sids),
            )
        )
        with engine.connect() as conn:
            for row in conn.execute(stmt).fetchall():
                if _block_prefix(row.number) != prefix:
                    continue
                block_siblings.append({
                    "sid": row.sid,
                    "id": row.id,
                    "oparlKey": row.oparlKey,
                    "oparlId": row.oparlId,
                    "name": row.name,
                    "start_date": row.start_date,
                    "end_date": row.end_date,
                    "meetingSid": row.meetingSid,
                    "number": row.number,
                    "result": row.result
                })
    for sibling in block_siblings:
        all_agenda.append(sibling)
    if block_siblings:
        _ensure_log().debug(f"Block expansion: added {len(block_siblings)} sibling agenda items")

    # 1.b (files): collect ALL files linked to the collected (and block)
    # agenda items as AuxFile — the missing counterpart to the paper
    # treatment in step 2.b
    all_agenda_sids = [a["sid"] for a in all_agenda]
    agenda_key_by_sid = {a["sid"]: a["oparlKey"] for a in all_agenda}
    if all_agenda_sids:
        stmt = (
            select(
                file_tbl.c.sid,
                file_tbl.c.oparlKey,
                file_tbl.c.name,
                file_tbl.c.filename,
                file_tbl.c.oparlId,
                file_tbl.c.downloadurl,
                file_tbl.c.date,
                af_assoc_tbl.c.srcSid.label("agendaSid"),
            )
            .select_from(
                af_assoc_tbl.join(
                    file_tbl, af_assoc_tbl.c.tgtSid == file_tbl.c.sid
                )
            )
            .where(af_assoc_tbl.c.srcSid.in_(all_agenda_sids))
        )
        with engine.connect() as conn:
            agenda_files = conn.execute(stmt).fetchall()

        seed_sids = set(file_sids.values())
        aux_via_block = set()
        for row in agenda_files:
            if row.sid in seed_sids:
                continue  # seed documents stay as-is (top_files)
            if not any(f["sid"] == row.sid for f in related_objects["AuxFile"]):
                agenda = next((a for a in all_agenda if a["sid"] == row.agendaSid), None)
                related_objects["AuxFile"].append({
                    "sid": row.sid,
                    "oparlKey": row.oparlKey,
                    "name": row.name,
                    "fileName": row.filename,
                    "oparlId": row.oparlId,
                    "downloadurl": row.downloadurl,
                    "date": row.date,
                    "via": _block_reference(agenda.get("number")) if agenda else None,
                })
            aux_via_block.add(row.sid)
            log_edge("AgendaItem", agenda_key_by_sid.get(row.agendaSid),
                     "auxiliaryFile", "AuxFile", row.oparlKey,
                     "AgendaItem__auxiliaryFile__File")
        _ensure_log().debug(f"Block expansion: {len(aux_via_block)} agenda-item documents collected as AuxFile")

    # 2. Find Papers connected to Files
    stmt = (
        select(
            paper_tbl.c.sid,
            paper_tbl.c.id,
            paper_tbl.c.oparlKey,
            paper_tbl.c.oparlId,
            paper_tbl.c.name,
            paper_tbl.c.date,
            paper_tbl.c.reference,
            paper_tbl.c.papertype,
            paper_tbl.c.bodySid,
            pf_assoc_tbl.c.tgtSid.label("fileSid"),
        )
        .select_from(
            pf_assoc_tbl.join(
                paper_tbl, pf_assoc_tbl.c.srcSid == paper_tbl.c.sid
            )
        )
        .where(pf_assoc_tbl.c.tgtSid.in_(file_sids.values()))
    )
    with engine.connect() as conn:
        papers = conn.execute(stmt).fetchall()

    for row in papers:
        related_objects["Paper"].append({
            "sid": row.sid,
            "id": row.id,
            "oparlKey": row.oparlKey,
            "oparlId": row.oparlId,
            "name": row.name,
            "date": row.date,
            "reference": row.reference,
            "paperType": row.papertype,
            "bodySid": row.bodySid
        })
        log_edge("Paper", row.oparlKey, "auxiliaryFile", "File",
                 sid_to_file_key.get(row.fileSid), "Paper__auxiliaryFile__File")
    _ensure_log().debug(f"Found {len(related_objects['Paper'])} papers related to files")  # Debugging line

    # 2.b when a paper is identified, we also want to get all associated files via pf_assoc_tbl, since the paper may have multiple files, and we want to include them in the timeline
    paper_sids = [p["sid"] for p in related_objects["Paper"]]
    if paper_sids:
        stmt = (
            select(
                file_tbl.c.sid,
                file_tbl.c.oparlKey,
                file_tbl.c.name,
                file_tbl.c.filename,
                file_tbl.c.oparlId,
                file_tbl.c.downloadurl,
                file_tbl.c.date,
                pf_assoc_tbl.c.srcSid.label("paperSid"),
            )
            .select_from(
                pf_assoc_tbl.join(
                    file_tbl, pf_assoc_tbl.c.tgtSid == file_tbl.c.sid
                )
            )
            .where(pf_assoc_tbl.c.srcSid.in_(paper_sids))
        )
        with engine.connect() as conn:
            paper_files = conn.execute(stmt).fetchall()

        paper_sid_to_key = {p["sid"]: p["oparlKey"] for p in related_objects["Paper"]}
        for row in paper_files:
            if not any(f["sid"] == row.sid for f in related_objects["AuxFile"]):
                related_objects["AuxFile"].append({
                    "sid": row.sid,
                    "oparlKey": row.oparlKey,
                    "name": row.name,
                    "fileName": row.filename,
                    "oparlId": row.oparlId,
                    "downloadurl": row.downloadurl,
                    "date": row.date
                })
            log_edge("Paper", paper_sid_to_key.get(row.paperSid), "auxiliaryFile", "AuxFile",
                     row.oparlKey, "Paper__auxiliaryFile__File")
        _ensure_log().debug(f"Found {len(related_objects['AuxFile'])} additional files related to papers")  # Debugging line
    
    # 3. Find Meetings connected to Files
    stmt = (
        select(
            meeting_tbl.c.sid,
            meeting_tbl.c.id,
            meeting_tbl.c.oparlKey,
            meeting_tbl.c.oparlId,
            meeting_tbl.c.name,
            meeting_tbl.c.start_date,
            meeting_tbl.c.end_date,
            mf_assoc_tbl.c.tgtSid.label("fileSid"),
        )
        .select_from(
            mf_assoc_tbl.join(
                meeting_tbl, mf_assoc_tbl.c.srcSid == meeting_tbl.c.sid
            )
        )
        .where(mf_assoc_tbl.c.tgtSid.in_(file_sids.values()))
    )
    with engine.connect() as conn:
        meetings = conn.execute(stmt).fetchall()

    for row in meetings:
        related_objects["Meeting"].append({
            "sid": row.sid,
            "id": row.id,
            "oparlKey": row.oparlKey,
            "oparlId": row.oparlId,
            "name": row.name,
            "start_date": row.start_date,
            "end_date": row.end_date
        })
        log_edge("Meeting", row.oparlKey, "auxiliaryFile", "File",
                 sid_to_file_key.get(row.fileSid), "Meeting__auxiliaryFile__File")

    # 4. For Papers, find related Consultations
    paper_sids = [p["sid"] for p in related_objects["Paper"]]
    if paper_sids:
        stmt = (
            select(
                consultation_tbl.c.sid,
                consultation_tbl.c.id,
                consultation_tbl.c.oparlKey,
                consultation_tbl.c.oparlId,
                consultation_tbl.c.role,
                consultation_tbl.c.authoritative,
                consultation_tbl.c.agendaItemSid,
                consultation_tbl.c.meetingSid,
                consultation_tbl.c.paperSid
            )
            .select_from(
                pc_assoc_tbl.join(
                    consultation_tbl, pc_assoc_tbl.c.tgtSid == consultation_tbl.c.sid
                )
            )
            .where(pc_assoc_tbl.c.srcSid.in_(paper_sids))
        )
        with engine.connect() as conn:
            consultations = conn.execute(stmt).fetchall()

        paper_sid_to_key = {p["sid"]: p["oparlKey"] for p in related_objects["Paper"]}
        for row in consultations:
            related_objects["Consultation"].append({
                "sid": row.sid,
                "id": row.id,
                "oparlKey": row.oparlKey,
                "oparlId": row.oparlId,
                "role": row.role,
                "authoritative": row.authoritative,
                "agendaItemSid": row.agendaItemSid,
                "meetingSid": row.meetingSid,
                "paperSid": row.paperSid
            })
            log_edge("Paper", paper_sid_to_key.get(row.paperSid), "consultation", "Consultation",
                     row.oparlKey, "Paper__consultation__Consultation")
    _ensure_log().debug(f"Found {len(related_objects['Consultation'])} consultations related to papers")  # Debugging line

    # 5. For Meetings, find related AgendaItems
    meeting_sids = [m["sid"] for m in related_objects["Meeting"]]
    if meeting_sids:
        stmt = (
            select(
                agenda_tbl.c.sid,
                agenda_tbl.c.id,
                agenda_tbl.c.oparlKey,
                agenda_tbl.c.oparlId,
                agenda_tbl.c.name,
                agenda_tbl.c.start_date,
                agenda_tbl.c.end_date,
                agenda_tbl.c.meetingSid,
                agenda_tbl.c.number,
                agenda_tbl.c.result
            )
            .select_from(
                ma_assoc_tbl.join(
                    agenda_tbl, ma_assoc_tbl.c.tgtSid == agenda_tbl.c.sid
                )
            )
            .where(ma_assoc_tbl.c.srcSid.in_(meeting_sids))
        )
        with engine.connect() as conn:
            meeting_agenda_items = conn.execute(stmt).fetchall()

        meeting_sid_to_key = {m["sid"]: m["oparlKey"] for m in related_objects["Meeting"]}
        for row in meeting_agenda_items:
            if not any(ai["sid"] == row.sid for ai in related_objects["AgendaItem"]):
                related_objects["AgendaItem"].append({
                    "sid": row.sid,
                    "id": row.id,
                    "oparlKey": row.oparlKey,
                    "oparlId": row.oparlId,
                    "name": row.name,
                    "start_date": row.start_date,
                    "end_date": row.end_date,
                    "meetingSid": row.meetingSid,
                    "number": row.number,
                    "result": row.result
                })
            log_edge("Meeting", meeting_sid_to_key.get(row.meetingSid), "agendaItem", "AgendaItem",
                     row.oparlKey, "Meeting__agendaItem__AgendaItem")
    _ensure_log().debug(f"Found {len(related_objects['AgendaItem'])} agenda items related to meetings")  # Debugging line

    # 6. For AgendaItems, find related Consultations
    agenda_item_sids = [ai["sid"] for ai in related_objects["AgendaItem"]]
    if agenda_item_sids:
        stmt = select(
            consultation_tbl.c.sid,
            consultation_tbl.c.id,
            consultation_tbl.c.oparlKey,
            consultation_tbl.c.oparlId,
            consultation_tbl.c.role,
            consultation_tbl.c.authoritative,
            consultation_tbl.c.agendaItemSid,
            consultation_tbl.c.meetingSid,
            consultation_tbl.c.paperSid
        ).where(consultation_tbl.c.agendaItemSid.in_(agenda_item_sids))
        
        with engine.connect() as conn:
            agenda_consultations = conn.execute(stmt).fetchall()
        
        for row in agenda_consultations:
            if not any(c["sid"] == row.sid for c in related_objects["Consultation"]):
                related_objects["Consultation"].append({
                    "sid": row.sid,
                    "id": row.id,
                    "oparlKey": row.oparlKey,
                    "oparlId": row.oparlId,
                    "role": row.role,
                    "authoritative": row.authoritative,
                    "agendaItemSid": row.agendaItemSid,
                    "meetingSid": row.meetingSid,
                    "paperSid": row.paperSid
                })

    # 6b. Fetch Meetings referenced by consultations/agenda items that were
    # not found through direct file links — without this, Meeting nodes (and
    # their calendar links) are missing from the graph whenever no seed file
    # links to the meeting directly.
    meeting_sid_to_key = {m["sid"]: m["oparlKey"] for m in related_objects["Meeting"]}
    referenced_meeting_sids = {c["meetingSid"] for c in related_objects["Consultation"] if c.get("meetingSid")}
    referenced_meeting_sids |= {a["meetingSid"] for a in related_objects["AgendaItem"] if a.get("meetingSid")}
    missing_meeting_sids = referenced_meeting_sids - set(meeting_sid_to_key)
    if missing_meeting_sids:
        stmt = (
            select(
                meeting_tbl.c.sid,
                meeting_tbl.c.id,
                meeting_tbl.c.oparlKey,
                meeting_tbl.c.oparlId,
                meeting_tbl.c.name,
                meeting_tbl.c.start_date,
                meeting_tbl.c.end_date,
            )
            .where(meeting_tbl.c.sid.in_(missing_meeting_sids))
        )
        with engine.connect() as conn:
            for row in conn.execute(stmt).fetchall():
                related_objects["Meeting"].append({
                    "sid": row.sid,
                    "id": row.id,
                    "oparlKey": row.oparlKey,
                    "oparlId": row.oparlId,
                    "name": row.name,
                    "start_date": row.start_date,
                    "end_date": row.end_date,
                })
        _ensure_log().debug(f"Fetched {len(missing_meeting_sids)} additional meetings via consultations/agenda items")

    # 7. For Consultations, find related Organizations
    consultation_sids = [c["sid"] for c in related_objects["Consultation"]]
    consultation_sid_to_key = {c["sid"]: c["oparlKey"] for c in related_objects["Consultation"]}
    if consultation_sids:
        stmt = (
            select(
                organization_tbl.c.sid,
                organization_tbl.c.id,
                organization_tbl.c.oparlKey,
                organization_tbl.c.oparlId,
                organization_tbl.c.name,
                organization_tbl.c.classification,
                organization_tbl.c.shortname,
                co_assoc_tbl.c.srcSid.label("consultSid"),
            )
            .select_from(
                co_assoc_tbl.join(
                    organization_tbl, co_assoc_tbl.c.tgtSid == organization_tbl.c.sid
                )
            )
            .where(co_assoc_tbl.c.srcSid.in_(consultation_sids))
        )
        with engine.connect() as conn:
            consultation_orgs = conn.execute(stmt).fetchall()
        
        for row in consultation_orgs:
            related_objects["Organization"].append({
                "sid": row.sid,
                "id": row.id,
                "oparlKey": row.oparlKey,
                "oparlId": row.oparlId,
                "name": row.name,
                "classification": row.classification,
                "shortName": row.shortname
            })
            log_edge("Consultation", consultation_sid_to_key.get(row.consultSid), "organization", "Organization",
                     row.oparlKey, "Consultation__organization__Organization")

    _ensure_log().debug(f"Found {len(related_objects['Organization'])} organizations related to consultations")  # Debugging line

    # 8. For Papers, find related Organizations (underDirectionOf)
    paper_sid_to_key = {p["sid"]: p["oparlKey"] for p in related_objects["Paper"]}
    if paper_sids:
        stmt = (
            select(
                organization_tbl.c.sid,
                organization_tbl.c.id,
                organization_tbl.c.oparlKey,
                organization_tbl.c.oparlId,
                organization_tbl.c.name,
                organization_tbl.c.classification,
                organization_tbl.c.shortname,
                po_assoc_tbl.c.srcSid.label("paperSid"),
            )
            .select_from(
                po_assoc_tbl.join(
                    organization_tbl, po_assoc_tbl.c.tgtSid == organization_tbl.c.sid
                )
            )
            .where(po_assoc_tbl.c.srcSid.in_(paper_sids))
        )
        with engine.connect() as conn:
            paper_orgs = conn.execute(stmt).fetchall()

        for row in paper_orgs:
            if not any(o["sid"] == row.sid for o in related_objects["Organization"]):
                related_objects["Organization"].append({
                    "sid": row.sid,
                    "id": row.id,
                    "oparlKey": row.oparlKey,
                    "oparlId": row.oparlId,
                    "name": row.name,
                    "classification": row.classification,
                    "shortName": row.shortname
                })
            log_edge("Paper", paper_sid_to_key.get(row.paperSid), "underDirectionOf", "Organization",
                     row.oparlKey, "Paper__underDirectionOf__Organization")

        _ensure_log().debug(f"Found {len(related_objects['Organization'])} organizations related to papers")  # Debugging line

    # 9. Direct-FK edges derivable from collected objects (no extra queries):
    #    Consultation.meetingSid/paperSid, AgendaItem.meetingSid
    meeting_sid_to_key = {m["sid"]: m["oparlKey"] for m in related_objects["Meeting"]}
    agenda_sid_to_key = {a["sid"]: a["oparlKey"] for a in related_objects["AgendaItem"]}
    for c in related_objects["Consultation"]:
        log_edge("Consultation", c["oparlKey"], "meeting", "Meeting",
                 meeting_sid_to_key.get(c.get("meetingSid")), "FK:Consultation.meetingSid")
        log_edge("Consultation", c["oparlKey"], "paper", "Paper",
                 paper_sid_to_key.get(c.get("paperSid")), "FK:Consultation.paperSid")
        log_edge("Consultation", c["oparlKey"], "agendaItem", "AgendaItem",
                 agenda_sid_to_key.get(c.get("agendaItemSid")), "FK:Consultation.agendaItemSid")
    for a in related_objects["AgendaItem"]:
        log_edge("AgendaItem", a["oparlKey"], "meeting", "Meeting",
                 meeting_sid_to_key.get(a.get("meetingSid")), "FK:AgendaItem.meetingSid")

    related_objects["edges"] = edges
    return related_objects

def build_timeline(related_objects: Dict[str, List[Dict]]) -> List[Dict]:
    """
    Build a timeline from related OParl objects, sorted by date.
    """
    timeline_events = []
    for obj_type, objects in related_objects.items():
        _ensure_log().debug(f"Processing {len(objects)} objects of type {obj_type} for timeline")  # Debugging line
        for obj in objects:
            # Determine the best date field for this object type
            date_field = None
            if obj_type == "Meeting":
                date_field = obj.get("start_date") or obj.get("end_date")
            elif obj_type == "AgendaItem":
                date_field = obj.get("start_date") or obj.get("end_date")
            elif obj_type == "Paper":
                date_field = obj.get("date")
            elif obj_type == "File":
                date_field = obj.get("date")
            elif obj_type == "AuxFile":
                date_field = obj.get("date")
            elif obj_type == "Consultation":
                # Consultations don't have direct dates, use related object dates
                continue
            else:
                date_field = obj.get("created") or obj.get("modified")

            if date_field is None:
                continue

            event = {
                "type": obj_type,
                "id": obj.get("id"),
                "oparlKey": obj.get("oparlKey"),
                "oparlId": obj.get("oparlId"),
                "name": obj.get("name") or obj.get("fileName") or f"{obj_type} {obj.get('id')}",
                "date": date_field,
                "details": {k: v for k, v in obj.items()
                          if k not in ["start_date", "end_date", "date", "created", "modified"]}
            }
            timeline_events.append(event)

    # Sort by date
    timeline_events.sort(key=lambda x: x["date"] if x["date"] else datetime.max)
    _ensure_log().debug(f"Built timeline with {len(timeline_events)} events after sorting")  # Debugging line

    return timeline_events

def group_timeline_events(timeline_events: List[Dict], window_days: int = TIMELINE_WINDOW_DAYS) -> List[Dict]:
    """
    Group timeline events that are close together in time.
    """
    if not timeline_events:
        return []

    # Convert to list of tuples (date, event) for easier processing
    events_with_dates = [(e["date"], e) for e in timeline_events if e["date"]]
    if not events_with_dates:
        return []

    _ensure_log().debug(f"Grouping {len(events_with_dates)} timeline events with window of {window_days} days")  # Debugging line

    grouped = []
    current_group = [events_with_dates[0][1]]

    for i in range(1, len(events_with_dates)):
        prev_date = current_group[-1]["date"]
        curr_date = events_with_dates[i][1]["date"]

        if prev_date and curr_date:
            delta = abs((curr_date - prev_date).days)
            if delta <= window_days:
                current_group.append(events_with_dates[i][1])
                continue

        # Finalize current group
        grouped.append({
            "start_date": current_group[0]["date"],
            "end_date": current_group[-1]["date"],
            "events": current_group.copy()
        })
        current_group = [events_with_dates[i][1]]

    # Add the last group
    if current_group:
        grouped.append({
            "start_date": current_group[0]["date"],
            "end_date": current_group[-1]["date"],
            "events": current_group.copy()
        })

    _ensure_log().debug(f"Grouped into {len(grouped)} event groups")  # Debugging line
    return grouped

@timed
def _typed_objects(related_objects: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """Strip the internal keys (``edges``, ``_sid_maps``) that
    ``find_related_objects`` mixes into its result, leaving only the
    object-type → objects mapping consumed by ``build_timeline`` and
    ``build_graph``. Deliberately non-mutating: the full dict (with the
    edge log) stays intact for the later graph stage."""
    return {
        k: v for k, v in related_objects.items()
        if k != "edges" and not k.startswith("_")
    }


@timed
def search_stage(
    session,
    query: str,
    top_k: int = TOP_K,
    threshold: float = 0.40,
    hybrid: bool = True,
    filters: Optional[List[Dict[str, Any]]] = None,
    signals: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """Stage 1 of the search pipeline (change: progressive-frontend-rendering):
    recall — query embedding, hybrid candidate retrieval, reranking, and
    the top-file list. Everything the file list pane needs; timeline and
    graph are built by :func:`timeline_stage` and :func:`graph_stage`.

    Returns a dict with ``query``, ``top_files``, ``matched_entities``,
    ``facets``, ``applied_filters`` and — on empty recall — a ``message``.
    """
    # api-debug-logging: every query the API sends through recall
    trace("recall", stage="search_stage", query=query, top_k=top_k,
          filters=len(filters or []), signals=bool(signals), hybrid=hybrid)
    # Generate embedding for the query
    query_embedding = call_embedding_model(query, EMBEDDING_API_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL)
    _ensure_log().debug(f"Generated embedding for query: {query_embedding[:5]}...")  # Debugging line

    matched_entities: List[Dict[str, Any]] = []
    facets_data: Dict[str, Any] = {}
    applied_filters: List[Dict[str, Any]] = []
    hybrid_distances: Dict[str, Optional[float]] = {}
    hybrid_match_info: Dict[str, Dict[str, Any]] = {}

    if hybrid:
        from src.search.pgHybridSearch import (
            _strip_terms_py,
            facets as facet_listing,
            hybrid_candidates,
            load_stop_terms,
            parse_filters,
        )

        conn = session.connection()
        applied_filters = parse_filters(filters)
        # Name vectors are embedded from stop-term-stripped names, so the
        # query side of that signal must be stripped too (design decision 6).
        stop_terms = load_stop_terms()
        stripped_query = _strip_terms_py(query, stop_terms)
        query_embedding_stripped = None
        if stripped_query and stripped_query != query:
            query_embedding_stripped = call_embedding_model(
                stripped_query, EMBEDDING_API_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL
            )
        hyb = hybrid_candidates(
            conn, query, query_embedding, top_k, filters=filters, signals=signals,
            query_embedding_stripped=query_embedding_stripped,
        )
        matched_entities = hyb["matched_entities"]
        candidates = hyb["file_candidates"]  # [{oparlKey, score, signals}]
        # kg-app-integration: topic-focus boost — documents carrying the
        # focus tag get a ×1.2 multiplier (never overtakes lexical top
        # hits aggressively: boost only, no reordering of unaffected)
        topic_focus = None
        try:
            from src.kg.kgQueries import topic_focus_for_query
            topic_focus = topic_focus_for_query(query)
        except Exception:
            topic_focus = None
        if topic_focus:
            ftags = {
                r[0]
                for r in conn.execute(sa_text_imp(
                    'SELECT oparl_key FROM "File_tags_assoc" a '
                    'JOIN "File_tags" t ON t.id = a.tag_id '
                    'WHERE a.scheme = \'kg-topic\' AND t.tag = :tag'),
                    {"tag": topic_focus}).fetchall()
            }
            for c in candidates:
                if c.get("oparlKey") in ftags:
                    c["score"] = round(c.get("score", 0.0) * 1.2, 6)
                    c.setdefault("signals", {})["kg_topic_boosted"] = topic_focus
        candidates.sort(key=lambda c: -c.get("score", 0.0))
        facets_data = facet_listing(conn)
        hybrid_distances = {
            c["oparlKey"]: c["signals"].get("content") for c in candidates
        }
        # change: content-chunking — best-matching chunk per file (reranker
        # input); None for legacy single-vector files
        hybrid_chunks = {
            c["oparlKey"]: c["signals"].get("content_chunk") for c in candidates
        }
        hybrid_match_info = {c["oparlKey"]: c["signals"] for c in candidates}
        _ensure_log().debug(f"Hybrid recall: {len(matched_entities)} entities, {len(candidates)} file candidates")
        if not candidates:
            trace("recall_done", stage="search_stage", hits=0,
                  entities=len(matched_entities), empty=True)
            return {
                "query": query,
                "top_files": [],
                "matched_entities": [],
                "facets": facets_data,
                "applied_filters": applied_filters,
                "message": "No candidates found for the given query/filters",
            }
        # Fused score feeds the reranker stage; distances are kept for output.
        top_scores = [(c["oparlKey"], c["score"]) for c in candidates]
    else:
        # legacy vector-only path
        # find similarities and get top-k files
        file_scores = query_vector_similarity(session, query_embedding, top_k)
        _ensure_log().debug(f"Inital Top files: {file_scores}")  # Debugging line

        _ensure_log().debug(f"Top files (before thresholding): {file_scores}")  # Debugging line
        if not file_scores:
            trace("recall_done", stage="search_stage", hits=0, entities=0,
                  empty=True)
            return {"query": query, "top_files": [], "matched_entities": [], "facets": {}, "applied_filters": [], "message": "No files with embeddings found"}

        # filter by threshold
        top_scores = filter_by_threshold(file_scores, threshold=threshold)
        _ensure_log().debug(f"Top files (after thresholding {threshold}): {top_scores}")  # Debugging line
        if not top_scores:
            trace("recall_done", stage="search_stage", hits=0, entities=0,
                  empty=True)
            return {"query": query, "top_files": [], "matched_entities": [], "facets": {}, "applied_filters": [], "message": "No files above similarity threshold"}

    # run reranking on all files and append rerank score to file_score
    top_scores_with_rerank = []
    # change: fix-hybrid-search-ranking — rerank gate config: the cutoff is
    # configurable, and lexically-certain Files survive the cutoff (ranked
    # below accepted files) when the lexical override is on. The logic
    # (module-level :func:`rerank_gate_decision`) is covered by unit tests.
    def _search_gate_config() -> Tuple[float, bool, int]:
        try:
            from src.instanceConfig import section as _sec
            sc = _sec("search")
            return (
                float(sc.get("rerank_cutoff", 0.8)),
                bool(sc.get("lexical_rerank_override", True)),
                int(sc.get("rerank_max_candidates", 60)),
            )
        except Exception:  # noqa: BLE001 - config failure = today's behaviour
            return (0.8, True, 60)
    RERANK_CUTOFF, LEXICAL_OVERRIDE, RERANK_WINDOW = _search_gate_config()

    # change: fix-hybrid-search-ranking, fragment B — listwise chat rerank:
    # with the reranker dropped (RERANK_MODE None) ONE SUMMARY_MDL call ranks
    # the fused-first candidates; scores then flow through
    # rerank_gate_decision like classical rerank scores.
    LISTWISE_ON, LISTWISE_WINDOW = _listwise_config()
    listwise_scores: Dict[str, float] = {}
    if RERANK_MODE is None and LISTWISE_ON and top_scores:
        window_lw = top_scores[:LISTWISE_WINDOW]
        cand = [(k, {"name": hybrid_match_info.get(k, {}).get("name")}) for k, _s in window_lw]
        try:
            listwise_scores = listwise_rerank(
                query, cand, hybrid_chunks, lambda k, c: chunk_text(session, k, c)
            )
        except Exception as exc:  # noqa: BLE001 - degrade to fused order
            _ensure_log().warning("listwise rerank stage failed: %s", exc)
        _ensure_log().debug(f"Listwise rerank: {len(listwise_scores)} relevant of {len(window_lw)}")

    def _lexical_keys() -> set:
        return {
            k for k, sig in hybrid_match_info.items()
            if isinstance(sig, dict) and ("lexical" in sig)
        }

    _ensure_log().debug(f"Running reranking on top {len(top_scores)} files")  # Debugging line

    if RERANK_MODE == "chat":
        for wi, (oparlKey, score) in enumerate(top_scores):
            # change: fix-hybrid-search-ranking extension — only the first
            # RERANK_WINDOW candidates (by fused score) get a real rerank
            # call; the rest keep the clamped fallback (fusion * cutoff),
            # which is at/below every reranked file's weakest accept score
            if wi >= RERANK_WINDOW:
                top_scores_with_rerank.append((oparlKey, score * min(1.0, RERANK_CUTOFF)))
                continue
            _ensure_log().debug(f"Processing file {oparlKey} with initial score {score:.4f}")  # Debugging line
            # rerank input (change: content-chunking): the best-matching
            # chunk for chunked documents — more discriminative than the
            # stored summary/head; legacy files keep File.content
            file_content = chunk_text(session, oparlKey, hybrid_chunks.get(oparlKey))
            if file_content is None:
                # change: unify-file-content-in-chunks — File_chunks is the
                # single text store (chunk 0 = the complete small document)
                file_content = document_text(session, oparlKey)
            if file_content:  # content exists and is not None
                rerank_score = call_reranking_chat_model(query, file_content)
                _ensure_log().debug(f"Reranking score for file {oparlKey}: {rerank_score:.4f}")  # Debugging line
                kept = rerank_gate_decision(
                    oparlKey, score, rerank_score, RERANK_CUTOFF,
                    LEXICAL_OVERRIDE, _lexical_keys())
                if kept is not None:
                    top_scores_with_rerank.append((oparlKey, kept))
                    _ensure_log().debug(f"Keep file {oparlKey}: score {score:.4f}, rerank {rerank_score}")  # Debugging line
                else:
                    _ensure_log().debug(f"Reject reranked file {oparlKey}: original score {score:.4f}, rerank score {rerank_score}")  # Debugging line
            else:
                _ensure_log().debug(f"No content found for file {oparlKey}, skipping reranking")  # Debugging line
                top_scores_with_rerank.append((oparlKey, score))  # No content, keep original score
                _ensure_log().debug(f"No content for file {oparlKey}, keeping original score {score:.4f}")  # Debugging line

        # update top_scores_with_rerank with rerank scores
        # top_scores_with_rerank = [(top_scores[i][0], rerank_scores[i]) for i in range(len(top_scores))]
    else:
        # change: fix-hybrid-search-ranking extension — rerank only the
        # first RERANK_WINDOW candidates by fused score before the top_k
        # cut; candidates beyond the window keep the clamped fallback
        # (fusion * cutoff), at/below every accepted file. With a running
        # listwise stage the model only saw LISTWISE_WINDOW candidates —
        # the cross-encoder pass must cover exactly the same span, else
        # unseen candidates would inherit a bogus "not relevant" verdict.
        window = top_scores[:LISTWISE_WINDOW if listwise_scores else RERANK_WINDOW]
        documents = []
        for oparlKey, score in window:
            # rerank input (change: content-chunking): best chunk first
            file_content = chunk_text(session, oparlKey, hybrid_chunks.get(oparlKey))
            if file_content is None:
                file_content = document_text(session, oparlKey)
            if file_content:
                documents.append(file_content)
            else:
                _ensure_log().debug(f"No content found for file {oparlKey}, skipping reranking")  # Debugging line
                documents.append("")  # Append empty string to maintain order
        rerank_scores = call_reranking_model(query, documents, top_n=len(documents))
        # fragment B: when reranking is dropped and the listwise stage ran,
        # merge its verdicts: relevant candidates (decaying score, floored
        # at the cutoff so they pass the gate), model-decided "not relevant"
        # → weak score (rejected unless lexically overridden; fusion order
        # is preserved by the gate's fallback), and candidates beyond the
        # listwise window fall back to the cross-encoder's own (pass-through)
        # score.
        if RERANK_MODE is None and listwise_scores:
            merged = []
            for (oK, _s), rs in zip(window, rerank_scores):
                if oK in listwise_scores:
                    merged.append(max(listwise_scores[oK], RERANK_CUTOFF))
                else:
                    merged.append(_LISTWISE_NOT_RELEVANT_SCORE)
            rerank_scores = merged
        _ensure_log().debug(f"Reranking scores: {rerank_scores}")
        for i, rscore in enumerate(rerank_scores):
            oparlKey, score = top_scores[i]
            kept = rerank_gate_decision(
                oparlKey, score, rscore, RERANK_CUTOFF,
                LEXICAL_OVERRIDE, _lexical_keys())
            if kept is not None:
                top_scores_with_rerank.append((oparlKey, kept))
                _ensure_log().debug(f"Keep file {oparlKey}: score {score:.4f}, rerank {rscore}")  # Debugging line
            else:
                _ensure_log().debug(f"Reject reranked file {oparlKey}: original score {score:.4f}, rerank score {rscore}")  # Debugging line
                # reject reranked file. don't append
        # extension: files beyond the rerank window keep clamped fallback
        rerank_covered = {k for k, _s in window}
        for oparlKey, score in top_scores:
            if oparlKey not in rerank_covered:
                top_scores_with_rerank.append((oparlKey, score * min(1.0, RERANK_CUTOFF)))

    # extension: honour rerank order via combined scoring (batch mode multiplies),
    # then apply the top_k cut AFTER the gate — deep-but-relevant matches survive
    _ensure_log().debug(f"Top files after reranking: {top_scores_with_rerank}")  # Debugging line
    top_scores_with_rerank = sorted(
        top_scores_with_rerank, key=lambda ks: ks[1], reverse=True)[:top_k]

    # Get Keys of top files
    top_file_keys = [f[0] for f in top_scores_with_rerank]
    _ensure_log().debug(f"Top file Keys: {top_file_keys}")
    # keep the rerank/fusion ordering in the output (DB returns arbitrary order)
    key_rank = {k: i for i, k in enumerate(top_file_keys)}  # Debugging line

    # first, we need to get the sid for each file key, since the associations are based on sids, not keys
    engine = session.get_bind()
    metadata = MetaData()
    file_tbl = Table('File', metadata, autoload_with=engine)
    stmt = select(file_tbl.c.sid, file_tbl.c.oparlKey, file_tbl.c.name, file_tbl.c.filename,
                  file_tbl.c.oparlId, file_tbl.c.downloadurl, file_tbl.c.date).where(file_tbl.c.oparlKey.in_(top_file_keys))
    with engine.connect() as conn:
        result = conn.execute(stmt).fetchall()
    top_files = [{
        "sid": row.sid,
        "oparlKey": row.oparlKey,
        "name": row.name,
        "fileName": row.filename,
        "downloadurl": row.downloadurl,
        "oparlId": row.oparlId,
        "date": row.date,
        # hybrid mode: content-vector cosine distance where the file came
        # from that signal, plus which signals matched it (match-type
        # qualifier; name-vector distance included where available)
        "distance": hybrid_distances.get(row.oparlKey)
                    if hybrid else
                    next((score for key, score in top_scores_with_rerank if key == row.oparlKey), None),
        "match": hybrid_match_info.get(row.oparlKey) if hybrid else None,
    } for row in result]
    top_files.sort(key=lambda f: key_rank.get(f["oparlKey"], len(key_rank)))
    _ensure_log().debug(f"Top files details: {top_files}")  # Debugging line

    trace("recall_done", stage="search_stage", hits=len(top_files),
          entities=len(matched_entities), empty=False)

    return {
        "query": query,
        "top_files": [{
            "sid": f["sid"],
            "oparlKey": f["oparlKey"],
            "name": f["name"],
            "fileName": f["fileName"],
            "downloadurl": f["downloadurl"],
            "oparlId": f["oparlId"],
            "date": f["date"],
            "distance": f["distance"],
            "match": f.get("match")
        } for f in top_files],
        "matched_entities": matched_entities,
        "facets": facets_data,
        "applied_filters": applied_filters,
    }


@timed
def timeline_stage(session, stage1: Dict[str, Any]) -> Dict[str, Any]:
    """Stage 2 of the search pipeline (change: progressive-frontend-rendering):
    traverse the association tables once (``find_related_objects``) and
    build the grouped timeline. The traversal result (including the edge
    log) is returned under ``related_objects`` so :func:`graph_stage` can
    reuse it without a second traversal.

    Returns ``{"timeline": ..., "related_objects": ..., "timeline_events":
    ..., "typed_objects": ...}``, or empty results when recall found no
    files.
    """
    top_files = stage1.get("top_files") or []
    if not top_files:
        return {"timeline": [], "related_objects": None, "timeline_events": [], "typed_objects": {},
                "related_objects_documents": None}

    file_sids = {item["oparlKey"]: item["sid"] for item in top_files}
    _ensure_log().debug(f"Resolved file keys to sids: {file_sids}")  # Debugging line

    # change: disable-organisation-expansion — two graph scopes per session:
    # `documents` = traversal seeded by the top_k answer documents only;
    # `full` = complete result-list traversal (agenda-item name-seed blocks).
    # Both traversals run in this stage; /graph serves them by scope.
    related_objects = find_related_objects(
        session, file_sids,
        agenda_item_sids=agenda_item_seeds(session, stage1.get("matched_entities")),
    )
    _ensure_log().debug(f"Related objects found: { {k: len(v) for k, v in related_objects.items()} }")  # Debugging line

    related_objects_documents = find_related_objects(session, file_sids)

    typed = _typed_objects(related_objects)

    # Build timeline from all related objects
    timeline_events = build_timeline(typed)
    _ensure_log().debug(f"Timeline events built: {len(timeline_events)}")  # Debugging line

    # Group timeline events
    grouped_timeline = group_timeline_events(timeline_events)
    _ensure_log().debug(f"Grouped timeline events: {len(grouped_timeline)}")  # Debugging line

    return {
        "timeline": grouped_timeline,
        "related_objects": related_objects,
        "related_objects_documents": related_objects_documents,
        "timeline_events": timeline_events,
        "typed_objects": typed,
    }


@timed
def graph_stage(session, stage1: Dict[str, Any], stage2: Dict[str, Any]) -> Dict[str, Any]:
    """Stage 3 of the search pipeline (change: progressive-frontend-rendering):
    serialize the traversed objects into the graph contract and compute the
    geo availability of the graph-connected answer set. Reuses the
    traversal from :func:`timeline_stage` (one ``find_related_objects``
    call per search); the edge list is copied, never popped, so both
    stages see the full traversal result.

    Returns ``{"graph": ..., "geo_available": ...}``.
    """
    from src.search.graphModel import build_graph, filter_skip_types

    top_files = stage1.get("top_files") or []
    related_objects = stage2.get("related_objects")
    if not top_files or related_objects is None:
        return {"graph": {"nodes": [], "edges": []},
                "graph_documents": {"nodes": [], "edges": []},
                "geo_available": False}

    typed = stage2.get("typed_objects") or _typed_objects(related_objects)
    edges = list(related_objects.get("edges") or [])

    # Serialize the traversed graph (nodes + typed edges, add-network-view).
    # Full scope: the accumulation stops at Organisation (change:
    # disable-organisation-expansion) — no org hub from many consultations
    # sharing one organisation.
    graph = filter_skip_types(build_graph(typed, edges, top_files))

    # documents scope (change: disable-organisation-expansion): the
    # traversal seeded by the top_k answer documents only — the default
    # view. Organisation leaves are kept here (no hub at this scale).
    related_docs = stage2.get("related_objects_documents")
    if related_docs is not None:
        typed_docs = _typed_objects(related_docs)
        edges_docs = list(related_docs.get("edges") or [])
        graph_documents = build_graph(typed_docs, edges_docs, top_files)
    else:
        graph_documents = graph

    # georeferences: streets/districts linked to the GRAPH-connected answer
    # set (seed files + traversal). Deliberately NOT the matched_entities
    # long tail — weak recall matches (rank 11+) drag in unrelated streets
    # and flood the map (analysis: query "rückbau herrenalber strasse":
    # graph scope = 175 features/13 streets, tail scope = 1475/65).
    from src.pgGeo import geo_available_for_keys
    agenda_item_keys = [n["oparlKey"] for n in graph["nodes"] if n["type"] == "AgendaItem"]
    file_keys = [n["oparlKey"] for n in graph["nodes"] if n["type"] in ("File", "AuxFile")]
    file_keys = [k for k in file_keys if k]
    geo_available = geo_available_for_keys(session.get_bind(), agenda_item_keys, file_keys)

    return {"graph": graph, "graph_documents": graph_documents, "geo_available": geo_available}


def search_and_build_timeline(
    session,
    query: str,
    top_k: int = TOP_K,
    threshold: float = 0.40,
    hybrid: bool = True,
    filters: Optional[List[Dict[str, Any]]] = None,
    signals: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """
    Main function to search files by embeddings and build a timeline of related OParl events.

    Composed of the three pipeline stages (change:
    progressive-frontend-rendering): :func:`search_stage` (recall),
    :func:`timeline_stage` (traversal + timeline) and :func:`graph_stage`
    (graph + geo availability). Interactive clients consume the stages
    individually; this composition keeps the monolithic result contract
    for the semantic timeline CLI and other non-interactive consumers.

    Args:
        session: SQLAlchemy session
        query: User search query
        top_k: Number of top results to return
        threshold: Similarity threshold for filtering results (legacy vector-only path)
        hybrid: Use hybrid multi-signal recall (lexical + name vectors + content
            vectors, RRF-fused). With False, falls back to the legacy
            content-vector-only path with distance thresholding.
        filters: Structured facet filters (see pgHybridSearch.parse_filters)
        signals: Per-signal toggles {"lexical": bool, "name_vectors": bool,
            "content_vectors": bool}; all default to True.

    Returns:
        Dictionary containing search results and timeline
    """
    stage1 = search_stage(
        session, query, top_k=top_k, threshold=threshold,
        hybrid=hybrid, filters=filters, signals=signals,
    )
    stage2 = timeline_stage(session, stage1)
    stage3 = graph_stage(session, stage1, stage2)

    return {
        "query": stage1["query"],
        "top_files": stage1["top_files"],
        "timeline": stage2["timeline"],
        "graph": stage3["graph"],
        "geo_available": stage3["geo_available"],
        "matched_entities": stage1["matched_entities"],
        "facets": stage1["facets"],
        "applied_filters": stage1["applied_filters"],
        "stats": {
            "total_files": len(stage1["top_files"]),
            "total_events": len(stage2["timeline_events"]),
            "event_types": {k: len(v) for k, v in stage2["typed_objects"].items() if v}
        },
        **({"message": stage1["message"]} if stage1.get("message") else {}),
    }

@timed
def search_and_summarize(
    session,
    query: str,
    top_k: int = TOP_K,
    threshold: float = 0.40,
    hybrid: bool = True,
    filters: Optional[List[Dict[str, Any]]] = None,
    signals: Optional[Dict[str, bool]] = None,
    summarize: bool = True,
) -> Dict[str, Any]:
    """Convenience wrapper: hybrid search + German summary of the top files.

    Calls :func:`search_and_build_timeline` and — unless *summarize* is
    False or no chat model is configured — runs
    ``src.pgResultSummarizer.ResultSummarizer`` over the result, adding
    ``result["summary"]`` (the field the web app's SummaryCard renders).
    This is the recommended entry point for non-interactive consumers
    (regeneration scripts, the future /search API endpoint).
    """
    result = search_and_build_timeline(
        session, query, top_k=top_k, threshold=threshold,
        hybrid=hybrid, filters=filters, signals=signals,
    )
    if summarize:
        from src.search.pgResultSummarizer import ResultSummarizer

        ResultSummarizer(session).summarize(result)
    return result


def main(directory: str, threshold: float = .40, top_k: int = TOP_K, filters: Optional[str] = None) -> None:
    """Main entry point for the script."""
    global EMBEDDING_API_KEY, EMBEDDING_API_URL, EMBEDDING_MODEL
    # Embedding configuration comes from src.remote (private.py / env)
    EMBEDDING_API_KEY = remote.EMBED_API_KEY
    EMBEDDING_API_URL = remote.EMBED_BASE_URL
    EMBEDDING_MODEL = remote.EMBED_MODEL

    # Create database session on the shared read-only engine
    session = get_db_session()

    try:
        while True:
            query = input("\nEnter your search query (or 'exit' to quit): ").strip()
            if query.lower() in ('exit', 'quit'):
                break

            if not query:
                _ensure_log().debug("Please enter a valid query.")
                continue

            try:
                parsed_filters = json.loads(filters) if filters else None
                results = search_and_build_timeline(session, query, top_k=top_k, threshold=threshold, filters=parsed_filters)

                # Print results
                _ensure_log().debug(f"\nQuery: {results['query']}")
                _ensure_log().debug(f"Found {len(results['top_files'])} matching files")

                if results['top_files']:
                    _ensure_log().debug("\nTop Files:")
                    for i, file in enumerate(results['top_files'][:5], 1):
                        _ensure_log().debug(f"{i}. {file['name']} ({file['fileName']})")
                        _ensure_log().debug(f"   Distance: {file['distance']:.3f}")
                        _ensure_log().debug(f"   OParl ID: {file['oparlId']}")
                        _ensure_log().debug(f"   Download URL: {file['downloadurl']}")
                        _ensure_log().debug(f"   Date: {file['date']}")

                    # generate a summary of the top files via the result summarizer
                    from src.search.pgResultSummarizer import ResultSummarizer

                    ResultSummarizer(session).summarize(results, force=True)
                else:
                    _ensure_log().debug("No top files found above the similarity threshold.")

                if results['timeline']:
                    _ensure_log().debug("\nTimeline of Related Events:")
                    for i, group in enumerate(results['timeline'], 1):
                        _ensure_log().debug(f"\nGroup {i}: {group['start_date']} to {group['end_date']}")
                        for event in group['events']:
                            _ensure_log().debug(f"  - {event['date']}: [{event['type']}] {event['name']} {event['oparlId']}")

                # Save results to file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = os.path.join(directory, f"search_results_{timestamp}.json")
                with open(save_path, 'w') as f:
                    json.dump(results, f, default=str, indent=2, ensure_ascii=False)
                _ensure_log().debug(f"\nDetailed results saved to {save_path}")




            except Exception as e:
                _ensure_log().debug(f"Error processing query: {str(e)}")

    finally:
        session.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Search OParl files by embedding similarity and build a timeline of related events.")
    parser.add_argument("-d", "--directory", default = os.getcwd(), help="Directory to save results (default: current directory)")
    parser.add_argument("-t", "--threshold", type=float, default=0.40, help="Similarity threshold (default: 0.40)")
    parser.add_argument("-k", "--top_k", type=int, default=TOP_K, help="Number of top results to return (default: TOP_K)")
    parser.add_argument("-F", "--filters", type=str, default=None, help='Structured facet filters as JSON, e.g. \'[{"facet":"paperType","op":"in","values":["Antrag"]}]\'' )
    args = parser.parse_args()
    main(args.directory, args.threshold, args.top_k, args.filters)
