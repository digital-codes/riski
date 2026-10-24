"""Hybrid multi-signal recall for RIS-KI search (change: categorization-indexing).

Combines three candidate signals over the OParl tables:
  L  = trigram lexical similarity over indexed `name` columns
       (GIN indexes created by pgGen)
  Vn = name vectors from `{item}_name_vecs` (pgvector cosine)
  Vc = content vectors from `contentEmbeddings` (pgvector cosine, File only)

Signals are fused per item table by reciprocal-rank fusion (RRF) and then
handed to the reranker (pgTimeline), which remains the final ranking step.

Structured filters are applied pre-fusion as WHERE clauses / key sets, so
they reduce candidate volume before reranking.

Note on identity: all query builders within one ``hybrid_candidates`` call
share a single ``MetaData``/``Table`` per item table — SQLAlchemy emits a
duplicate-alias FROM when two ``Table`` objects of the same name appear in
one statement.
"""

# Dual-mode import support: allow running directly as a script.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

from typing import Any, Dict, List, Optional, Sequence, Tuple

import re

import sqlalchemy as sa
from sqlalchemy import Column, MetaData, Table, select
from pgvector.sqlalchemy import Vector

from src.db import _load_private
from src.timing import timed, timed_block
import os

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
RRF_K = 60
DEFAULT_CANDIDATES_PER_SIGNAL = 50
LEXICAL_SIMILARITY_THRESHOLD = 0.30

# table -> (name column, date column) used for lexical recall and year filters
TABLE_NAME_COL = {
    "Paper": "name",
    "File": "name",
    "AgendaItem": "name",
    "Meeting": "name",
}
TABLE_DATE_COL = {
    "Paper": "date",
    "File": "date",
    "AgendaItem": "start_date",
    "Meeting": "start_date",
}
CANDIDATE_TABLES = ("Paper", "File", "AgendaItem", "Meeting")

DEFAULT_STOP_TERMS_FILE = "config/lexical_stop_terms.txt"


def load_stop_terms() -> List[str]:
    """Load the lexical stop-term list (design decision 6).

    Resolution order: path from private.py ``LEXICAL_STOP_TERMS_FILE`` or
    env ``LEXICAL_STOP_TERMS_FILE``, else the shipped
    ``config/lexical_stop_terms.txt``. A missing/unset file yields an empty
    list (no stripping). The list itself lives in a separate file —
    private.py only references it — so deployments differ without code
    changes.
    """
    pr = _load_private()
    path = None
    if pr is not None:
        path = getattr(pr, "LEXICAL_STOP_TERMS_FILE", None)
    path = path or os.getenv("LEXICAL_STOP_TERMS_FILE") or DEFAULT_STOP_TERMS_FILE
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def _pg_regex_escape(term: str) -> str:
    """Escape a stop term for use inside a PostgreSQL regex alternation."""
    return re.sub(r"([\\.^$|(){}\[\]*+?])", r"\\\1", term)


def _strip_terms_py(text: str, terms: Sequence[str]) -> str:
    """Remove stop terms from a query string (case-insensitive, word bounds)."""
    if not terms:
        return text
    pattern = re.compile(r"\b(" + "|".join(_pg_regex_escape(t) for t in terms) + r")\b", re.IGNORECASE)
    return re.sub(r"\s+", " ", pattern.sub("", text)).strip()


def _strip_expr(name_col, terms: Sequence[str]):
    """SQL expression stripping stop terms from a name column."""
    pattern = r"\m(" + "|".join(_pg_regex_escape(t) for t in terms) + r")\M"
    return sa.func.regexp_replace(sa.func.lower(name_col), pattern, "", "gi")


# ----------------------------------------------------------------------
# Structured filters (task 4.4)
# ----------------------------------------------------------------------
_FACETS = {
    "paperType", "year", "result", "role", "authoritative", "tag", "district",
    "organization",
}
_OPS = {"in", "eq", "range"}
_YEAR_BASES = {"paper", "meeting", "file"}


class FilterError(ValueError):
    """Raised for structurally invalid filter specifications."""


def parse_filters(filters: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Validate and normalize the structured filter list.

    Supported shapes (see change design decision 5):
      {"facet": "paperType",     "op": "in", "values": [...]}
      {"facet": "year",          "op": "range", "from": "2021", "to": "2022",
       "basis": "meeting"}                                     # default: paper
      {"facet": "result",        "op": "in", "values": [...]}
      {"facet": "role",          "op": "in", "values": [...]}
      {"facet": "authoritative", "op": "eq", "value": true}
      {"facet": "tag", "scheme": "district", "op": "in", "values": [...]}
      {"facet": "district",      "op": "in", "values": [...]}
    """
    if not filters:
        return []
    normalized: List[Dict[str, Any]] = []
    for f in filters:
        if not isinstance(f, dict):
            raise FilterError(f"Filter must be an object, got {f!r}")
        facet = f.get("facet")
        if facet not in _FACETS:
            raise FilterError(f"Unknown facet {facet!r}; expected one of {sorted(_FACETS)}")
        op = f.get("op", "in")
        if op not in _OPS:
            raise FilterError(f"Unknown filter op {op!r}; expected one of {sorted(_OPS)}")

        norm: Dict[str, Any] = {"facet": facet, "op": op}
        if op == "in":
            values = f.get("values")
            if not isinstance(values, (list, tuple)) or not values:
                raise FilterError(f"'in' filter for {facet!r} requires a non-empty 'values' list")
            norm["values"] = [str(v) for v in values]
        elif op == "eq":
            if "value" not in f:
                raise FilterError(f"'eq' filter for {facet!r} requires 'value'")
            norm["value"] = f["value"]
        else:  # range
            if facet != "year":
                raise FilterError(f"'range' op is only supported for facet 'year', got {facet!r}")
            norm["from"] = f.get("from")
            norm["to"] = f.get("to")
            if norm["from"] is None and norm["to"] is None:
                raise FilterError("year range filter requires 'from' and/or 'to'")
            basis = f.get("basis", "paper")
            if basis not in _YEAR_BASES:
                raise FilterError(f"year basis must be one of {sorted(_YEAR_BASES)}, got {basis!r}")
            norm["basis"] = basis
        if facet == "tag":
            scheme = f.get("scheme")
            if not scheme:
                raise FilterError("tag filter requires a 'scheme' (e.g. 'document-type', 'topic')")
            norm["scheme"] = str(scheme)
        if facet == "organization" and op != "in":
            raise FilterError("organization filter supports op 'in' (names) only")
        normalized.append(norm)
    return normalized


def _has_table(conn, name: str) -> bool:
    return sa.inspect(conn).has_table(name)


# ----------------------------------------------------------------------
# Candidate signals (task 4.2)
# ----------------------------------------------------------------------
@timed
def lexical_candidates(
    conn,
    query: str,
    tbl,
    limit: int = DEFAULT_CANDIDATES_PER_SIGNAL,
    threshold: float = LEXICAL_SIMILARITY_THRESHOLD,
    extra_where: Optional[List] = None,
    stop_terms: Optional[Sequence[str]] = None,
) -> List[Tuple[str, str, float]]:
    """Trigram lexical candidates over the indexed name column.

    ``tbl`` is a shared Table object. Both the query and the name column
    are stripped of the configured stop terms (e.g. the city name) before
    similarity — see design decision 6. Returns ``(oparlKey, name,
    similarity)`` ordered by descending similarity. At current corpus sizes
    an ordered scan is fast enough despite the GIN index only accelerating
    the % operator.
    """
    terms = load_stop_terms() if stop_terms is None else list(stop_terms)
    name_col = getattr(tbl.c, TABLE_NAME_COL[tbl.name])
    if terms:
        compared = _strip_expr(name_col, terms)
        compared_query = _strip_terms_py(query, terms)
    else:
        compared = sa.func.lower(name_col)
        compared_query = query.lower()
    stmt = (
        select(tbl.c.oparlKey, name_col, sa.func.similarity(compared, compared_query).label("sim"))
        .where(sa.func.similarity(compared, compared_query) > threshold)
    )
    for f in extra_where or []:
        stmt = stmt.where(f)
    # deterministic tie-break on oparlKey: identical scores (duplicate
    # names / identical vectors) must order identically across runs and
    # connections (change: api-latency-optimization, parity requirement)
    stmt = stmt.order_by(sa.desc("sim"), sa.asc(tbl.c.oparlKey)).limit(limit)
    return [(row.oparlKey, row[1], float(row.sim)) for row in conn.execute(stmt)]


@timed
def name_vector_candidates(
    conn,
    query_embedding: Sequence[float],
    tbl,
    limit: int = DEFAULT_CANDIDATES_PER_SIGNAL,
    extra_where: Optional[List] = None,
) -> List[Tuple[str, float]]:
    """Name-vector nearest neighbors from ``{table}_name_vecs``.

    Returns ``(oparlKey, cosine_distance)``. Missing table yields [] so
    fusion degrades gracefully (design decision 4).
    """
    vec_table = f"{tbl.name}_name_vecs"
    if not _has_table(conn, vec_table):
        return []
    # Declared explicitly: reflection would drop the pgvector comparator.
    vec = Table(
        vec_table, MetaData(),
        Column("oparl_key", sa.String(500), primary_key=True),
        Column("embedding", Vector(1024)),
    )
    name_col = getattr(tbl.c, TABLE_NAME_COL[tbl.name])
    dist = vec.c.embedding.cosine_distance(query_embedding).label("distance")
    stmt = (
        select(vec.c.oparl_key, dist)
        .select_from(vec)
        .where(dist < 0.9)  # keep only plausibly related items
    )
    # constrain via subquery on the item table's keys
    item_keys = select(tbl.c.oparlKey)
    for f in extra_where or []:
        item_keys = item_keys.where(f)
    stmt = stmt.where(vec.c.oparl_key.in_(item_keys.scalar_subquery()))
    stmt = stmt.order_by(sa.asc("distance"), sa.asc(vec.c.oparl_key)).limit(limit)
    return [(row.oparl_key, float(row.distance)) for row in conn.execute(stmt)]


@timed
def content_vector_candidates(
    conn,
    query_embedding: Sequence[float],
    limit: int = DEFAULT_CANDIDATES_PER_SIGNAL,
    extra_where: Optional[List] = None,
    file_tbl=None,
) -> List[Tuple[str, float]]:
    """Content-vector nearest neighbors from ``contentEmbeddings`` (File only).

    Returns ``(oparlKey, cosine_distance)``. When ``file_tbl`` is given
    (shared Table object), filters referencing File columns are applied via
    a join — the embeddings table itself carries no metadata.
    """
    # Declared explicitly: reflection would drop the pgvector comparator.
    emb = Table(
        "contentEmbeddings", MetaData(),
        Column("oparlKey", sa.String(500)),
        Column("value", Vector(1024)),
    )
    dist = emb.c.value.cosine_distance(query_embedding).label("distance")
    stmt = select(emb.c.oparlKey, dist)
    if file_tbl is not None:
        stmt = stmt.join(file_tbl, emb.c.oparlKey == file_tbl.c.oparlKey)
    for f in extra_where or []:
        stmt = stmt.where(f)
    stmt = stmt.order_by(sa.asc("distance"), sa.asc(emb.c.oparlKey)).limit(limit)
    return [(row.oparlKey, float(row.distance)) for row in conn.execute(stmt)]


# ----------------------------------------------------------------------
# Fusion (task 4.3)
# ----------------------------------------------------------------------
def rrf_fuse(
    ranked_lists: Sequence[Sequence[str]],
    k: int = RRF_K,
) -> Dict[str, float]:
    """Reciprocal-rank fusion over candidate id lists.

    score(id) = sum over lists of 1 / (k + rank), rank starting at 1.
    Returns ``{id: fused_score}`` ordered by descending score.
    """
    scores: Dict[str, float] = {}
    for lst in ranked_lists:
        for rank, ident in enumerate(lst, start=1):
            scores[ident] = scores.get(ident, 0.0) + 1.0 / (k + rank)
    return dict(sorted(scores.items(), key=lambda kv: kv[1], reverse=True))


def _names_for(conn, tbl, oparl_keys: Sequence[str]) -> Dict[str, str]:
    if not oparl_keys:
        return {}
    name_col = getattr(tbl.c, TABLE_NAME_COL[tbl.name])
    rows = conn.execute(
        select(tbl.c.oparlKey, name_col).where(tbl.c.oparlKey.in_(list(oparl_keys)))
    ).all()
    return {r[0]: r[1] for r in rows}


# ----------------------------------------------------------------------
# Filters applied pre-fusion (task 4.4)
# ----------------------------------------------------------------------
def build_candidate_filters(tbl, filters: List[Dict[str, Any]], conn):
    """Translate normalized filters into constraints for *tbl* candidates.

    Returns ``(extra_where, required_keys)``:
      extra_where   list of SQLAlchemy clauses for this table
      required_keys set of oparlKeys the candidates must belong to (from
                    tag/district filters), or None
    """
    import datetime

    table = tbl.name
    extra: List = []
    required: Optional[set] = None

    def _require(keys):
        nonlocal required
        required = keys if required is None else (required & keys)

    for f in filters:
        facet, op = f["facet"], f["op"]
        if facet == "paperType" and table == "Paper":
            col = tbl.c.papertype if hasattr(tbl.c, "papertype") else tbl.c.paperType
            extra.append(col.in_(f["values"]))
        elif facet == "result" and table == "AgendaItem":
            extra.append(tbl.c.result.in_(f["values"]))
        elif facet == "role" and table == "Consultation":
            extra.append(tbl.c.role.in_(f["values"]))
        elif facet == "authoritative" and table == "Consultation":
            extra.append(tbl.c.authoritative.is_(bool(f["value"])))
        elif facet == "year":
            basis_map = {"paper": "Paper", "meeting": "Meeting", "file": "File"}
            if basis_map.get(f["basis"]) != table:
                continue
            col = getattr(tbl.c, TABLE_DATE_COL[table])
            for bound, lo in (("from", True), ("to", False)):
                year = f.get(bound)
                if year is None:
                    continue
                if lo:
                    extra.append(col >= datetime.datetime(int(year), 1, 1))
                else:
                    extra.append(col <= datetime.datetime(int(year), 12, 31, 23, 59, 59))
        elif facet in ("tag", "district", "organization"):
            keys = _keys_for_facet(conn, table, f)
            if keys is None:
                # Facet does not apply to this table (e.g. district only
                # links agenda items) — leave the table unconstrained.
                continue
            _require(keys)
    return extra, required


def _keys_for_facet(conn, table: str, f: Dict[str, Any]) -> Optional[set]:
    """Resolve tag/district filters to oparlKey sets for *table*.

    Returns None when the facet cannot constrain *table* at all.
    """
    metadata = MetaData()
    if f["facet"] == "tag":
        assoc = f"{table}_tags_assoc"
        if not _has_table(conn, assoc):
            return None
        assoc_tbl = Table(assoc, metadata, autoload_with=conn)
        tagt = Table(f"{table}_tags", metadata, autoload_with=conn)
        stmt = (
            select(assoc_tbl.c.oparl_key)
            .select_from(assoc_tbl.join(tagt, assoc_tbl.c.tag_id == tagt.c.id))
            .where(assoc_tbl.c.scheme == f["scheme"])
            .where(tagt.c.tag.in_(f["values"]))
        )
        return {r[0] for r in conn.execute(stmt)}
    # district facet: only AgendaItems are district-linked (existing table)
    if f["facet"] == "district":
        if table != "AgendaItem":
            return None
        assoc_name = "Districts_items_AgendaItems"
        if not _has_table(conn, assoc_name):
            return None
        assoc = Table(assoc_name, metadata, autoload_with=conn)
        district = Table("District", metadata, autoload_with=conn)
        agenda = Table("AgendaItem", metadata, autoload_with=conn)
        stmt = (
            select(agenda.c.oparlKey)
            .select_from(
                assoc.join(district, assoc.c.district_id == district.c.id)
                .join(agenda, assoc.c.agendaitem_id == agenda.c.sid)
            )
            .where(district.c.name.in_(f["values"]))
        )
        return {r[0] for r in conn.execute(stmt)}
    # organization facet: entities directly associated with the named
    # organizations via their junction tables (committee membership etc.)
    if f["facet"] == "organization":
        org = Table("Organization", metadata, autoload_with=conn)
        if table == "File":
            # two-hop path: File -File__meeting__Meeting-> Meeting
            #   -Meeting__organization__Organization-> Organization
            assoc_name = "File__meeting__Meeting"
            if not _has_table(conn, assoc_name):
                return None
            assoc = Table(assoc_name, metadata, autoload_with=conn)
            meeting = Table("Meeting", metadata, autoload_with=conn)
            morg = Table("Meeting__organization__Organization", metadata, autoload_with=conn)
            item = Table(table, metadata, autoload_with=conn)
            stmt = (
                select(item.c.oparlKey)
                .select_from(
                    assoc.join(meeting, assoc.c.tgtSid == meeting.c.sid)
                    .join(morg, morg.c.srcSid == meeting.c.sid)
                    .join(org, morg.c.tgtSid == org.c.sid)
                    .join(item, assoc.c.srcSid == item.c.sid)
                )
                .where(org.c.name.in_(f["values"]))
            )
            return {r[0] for r in conn.execute(stmt)}
        org_links = {
            "Meeting": "Meeting__organization__Organization",
            "Paper": "Paper__underDirectionOf__Organization",
        }
        assoc_name = org_links.get(table)
        if assoc_name is None or not _has_table(conn, assoc_name):
            return None
        assoc = Table(assoc_name, metadata, autoload_with=conn)
        org = Table("Organization", metadata, autoload_with=conn)
        item = Table(table, metadata, autoload_with=conn)
        stmt = (
            select(item.c.oparlKey)
            .select_from(
                assoc.join(org, assoc.c.tgtSid == org.c.sid)
                .join(item, assoc.c.srcSid == item.c.sid)
            )
            .where(org.c.name.in_(f["values"]))
        )
        return {r[0] for r in conn.execute(stmt)}
    return None


# ----------------------------------------------------------------------
# Facet listing (task 4.5) + TTL cache (change: api-latency-optimization)
# ----------------------------------------------------------------------
_FACET_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": None}
FACET_TTL_DEFAULT = 600.0  # seconds


def facet_ttl() -> float:
    """TTL for the facet cache (env ``RISKI_FACET_TTL``, 0 disables)."""
    try:
        return float(os.getenv("RISKI_FACET_TTL", str(FACET_TTL_DEFAULT)))
    except ValueError:
        return FACET_TTL_DEFAULT


def invalidate_facet_cache() -> None:
    """Drop the cached facet listing (called after data syncs)."""
    _FACET_CACHE["ts"] = 0.0
    _FACET_CACHE["payload"] = None


@timed
def facets(conn) -> Dict[str, Any]:
    """Available filter values with counts, to drive UI dropdowns.

    Cached with a TTL (``RISKI_FACET_TTL``, default 10 min, 0 disables):
    /facets and the per-search facet block share the cache; invalidated
    by :func:`invalidate_facet_cache` after pipeline imports."""
    ttl = facet_ttl()
    if ttl <= 0:
        return _facets_uncached(conn)
    import copy
    import time as _time

    now = _time.time()
    payload = _FACET_CACHE["payload"]
    if payload is not None and now - _FACET_CACHE["ts"] < ttl:
        return copy.deepcopy(payload)
    payload = _facets_uncached(conn)
    _FACET_CACHE["ts"] = now
    _FACET_CACHE["payload"] = payload
    return copy.deepcopy(payload)


def _facets_uncached(conn) -> Dict[str, Any]:
    """Available filter values with counts, to drive UI dropdowns."""
    out: Dict[str, Any] = {}
    meta = MetaData()
    if _has_table(conn, "Paper"):
        paper = Table("Paper", meta, autoload_with=conn)
        col = paper.c.papertype if hasattr(paper.c, "papertype") else paper.c.paperType
        rows = conn.execute(
            select(col, sa.func.count()).where(col.isnot(None)).group_by(col).order_by(sa.func.count().desc())
        ).all()
        out["paperType"] = {r[0]: r[1] for r in rows}
        years = conn.execute(
            select(sa.func.distinct(sa.func.extract("year", paper.c.date)))
            .where(paper.c.date.isnot(None))
            .order_by(sa.func.extract("year", paper.c.date))
        ).scalars().all()
        out["years"] = [int(y) for y in years if y is not None]
    if _has_table(conn, "AgendaItem"):
        agenda = Table("AgendaItem", meta, autoload_with=conn)
        rows = conn.execute(
            select(agenda.c.result, sa.func.count())
            .where(agenda.c.result.isnot(None) & (agenda.c.result != ""))
            .group_by(agenda.c.result)
            .order_by(sa.func.count().desc())
        ).all()
        out["result"] = {r[0]: r[1] for r in rows}
    # tag counts per scheme (union over item tables)
    tag_schemes: Dict[str, int] = {}
    for table in ("Paper", "File", "AgendaItem", "Meeting", "Organization"):
        assoc = f"{table}_tags_assoc"
        if not _has_table(conn, assoc):
            continue
        tbl = Table(assoc, meta, autoload_with=conn)
        rows = conn.execute(
            select(sa.func.coalesce(tbl.c.scheme, "(none)"), sa.func.count(sa.func.distinct(tbl.c.oparl_key)))
            .group_by(sa.func.coalesce(tbl.c.scheme, "(none)"))
        ).all()
        for scheme, n in rows:
            tag_schemes[scheme] = tag_schemes.get(scheme, 0) + n
    out["tags"] = tag_schemes
    # organizations (committee filter): item counts across direct links
    org_counts: Dict[str, int] = {}
    if _has_table(conn, "Organization"):
        for assoc_name in ("Meeting__organization__Organization",
                           "Paper__underDirectionOf__Organization"):
            if not _has_table(conn, assoc_name):
                continue
            assoc = Table(assoc_name, meta, autoload_with=conn)
            org = Table("Organization", meta, autoload_with=conn)
            rows = conn.execute(
                select(org.c.name, sa.func.count(sa.func.distinct(assoc.c.srcSid)))
                .select_from(assoc.join(org, assoc.c.tgtSid == org.c.sid))
                .group_by(org.c.name)
            ).all()
            for name, n in rows:
                if name:
                    org_counts[name] = org_counts.get(name, 0) + n
    out["organization"] = dict(sorted(org_counts.items(), key=lambda kv: kv[1], reverse=True))
    return out


# ----------------------------------------------------------------------
# Hybrid candidate generation (tasks 4.2/4.3 wiring)
# ----------------------------------------------------------------------
# change: api-latency-optimization — the per-table/per-signal recall
# queries are independent read-only waits and run concurrently on a
# bounded pool; results merge in the same deterministic table order as
# the sequential path (parity is asserted by the integration test).
# Kill switch: RISKI_PARALLEL_SIGNALS=0 restores the sequential path.
_HYBRID_EXECUTOR = None


def _hybrid_executor():
    global _HYBRID_EXECUTOR
    if _HYBRID_EXECUTOR is None:
        from concurrent.futures import ThreadPoolExecutor

        _HYBRID_EXECUTOR = ThreadPoolExecutor(
            max_workers=12, thread_name_prefix="hybrid"
        )
    return _HYBRID_EXECUTOR


def _parallel_signals_enabled() -> bool:
    import os as _os

    return _os.getenv("RISKI_PARALLEL_SIGNALS", "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _run_all(tasks: List):
    """Run (name, callable) tasks; returns results in submission order.
    Concurrent on the bounded pool, or sequentially when disabled. A
    failing task yields None for its slot instead of failing the batch."""
    tasks = [(name, fn) for name, fn in tasks]
    if _parallel_signals_enabled():
        futures = [(name, _hybrid_executor().submit(fn)) for name, fn in tasks]
        out = []
        for _name, fut in futures:
            try:
                out.append(fut.result())
            except Exception as exc:  # noqa: BLE001 - degrade per task
                import logging

                logging.getLogger("riski.hybrid").warning(
                    "hybrid task %s failed: %s", _name, exc
                )
                out.append(None)
        return out
    out = []
    for name, fn in tasks:
        try:
            out.append(fn())
        except Exception as exc:  # noqa: BLE001
            import logging

            logging.getLogger("riski.hybrid").warning(
                "hybrid task %s failed: %s", name, exc
            )
            out.append(None)
    return out


def _table_recall(conn, table, query, nv_embedding, query_embedding,
                  per_signal, parsed, stop_terms,
                  use_lexical, use_name_vecs, use_content):
    """Per-table recall task: own connection, filters, signals, fusion and
    provenance assembly. Returns (table, fused, required, lex, nv, vc,
    nv_dist, vc_dist, names) or raises."""
    tbl = Table(table, MetaData(), autoload_with=conn)
    extra, required = build_candidate_filters(tbl, parsed, conn)

    lex: List[str] = []
    if use_lexical:
        with timed_block(f"hybrid.lexical[{table}]"):
            lex = [k for k, _n, _s in lexical_candidates(
                conn, query, tbl, per_signal, extra_where=extra, stop_terms=stop_terms)]
    nv: List[str] = []
    nv_dist: Dict[str, float] = {}
    if use_name_vecs:
        with timed_block(f"hybrid.name_vecs[{table}]"):
            pairs = name_vector_candidates(conn, nv_embedding, tbl, per_signal, extra_where=None)
            nv = [k for k, _d in pairs]
            nv_dist = dict(pairs)
    vc: List[str] = []
    vc_dist: Dict[str, float] = {}
    if use_content and table == "File":
        with timed_block(f"hybrid.content_vecs[{table}]"):
            pairs = content_vector_candidates(
                conn, query_embedding, per_signal, extra_where=extra, file_tbl=tbl
            )
            vc = [k for k, _d in pairs]
            vc_dist = dict(pairs)

    fused = rrf_fuse([l for l in (lex, nv, vc) if l])
    names = _names_for(conn, tbl, list(fused)[: per_signal * 2])
    return table, fused, required, lex, nv, vc, nv_dist, vc_dist, names


@timed
def hybrid_candidates(
    conn,
    query: str,
    query_embedding: Sequence[float],
    top_k: int,
    filters: Optional[List[Dict[str, Any]]] = None,
    signals: Optional[Dict[str, bool]] = None,
    per_signal: int = DEFAULT_CANDIDATES_PER_SIGNAL,
    query_embedding_stripped: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """Generate fused candidates per item table.

    ``query_embedding_stripped`` is an embedding of the stop-term-stripped
    query, used for the name-vector signal so both sides of the comparison
    exclude the same non-discriminative terms (design decision 6). When
    omitted, the main ``query_embedding`` is used as-is.

    Returns ``{
      "matched_entities": [{"id": "{Type}_{oparlKey}", "type": ..., "oparlKey": ...,
                            "name": ..., "score": rrf}],
      "file_candidates":  [(oparlKey, fused_score, content_distance_or_None)],
    }``. ``file_candidates`` is ordered by fused score, capped at top_k.
    """
    signals = signals or {}
    use_lexical = signals.get("lexical", True)
    use_name_vecs = signals.get("name_vectors", True)
    use_content = signals.get("content_vectors", True)
    parsed = parse_filters(filters)
    stop_terms = load_stop_terms()
    nv_embedding = query_embedding_stripped if query_embedding_stripped is not None else query_embedding

    matched: List[Dict[str, Any]] = []
    file_fused: Dict[str, float] = {}
    file_signals: Dict[str, Dict[str, Any]] = {}

    engine = conn.engine
    tasks = []
    for table in CANDIDATE_TABLES:
        def _task(table=table):
            with engine.connect() as task_conn:
                return _table_recall(
                    task_conn, table, query, nv_embedding, query_embedding,
                    per_signal, parsed, stop_terms,
                    use_lexical, use_name_vecs, use_content,
                )
        tasks.append((f"recall[{table}]", _task))

    results = _run_all(tasks)

    for result in results:  # submission order == CANDIDATE_TABLES order
        if result is None:
            continue  # task failed: that table contributes nothing
        (table, fused, required, lex, nv, vc, nv_dist, vc_dist, names) = result
        if required is not None:
            fused = {k: v for k, v in fused.items() if k in required}
        if not fused:
            continue

        # per-candidate signal provenance: which signals found it, with the
        # distance where the signal provides one (lower = better)
        lex_set, nv_set, vc_set = set(lex), set(nv), set(vc)
        for oparl_key, score in fused.items():
            signals_hit: Dict[str, Any] = {}
            if oparl_key in lex_set:
                signals_hit["lexical"] = True
            if oparl_key in nv_set:
                signals_hit["name"] = round(nv_dist[oparl_key], 4)
            if oparl_key in vc_set:
                signals_hit["content"] = round(vc_dist[oparl_key], 4)
            if table == "File":
                file_fused[oparl_key] = score
                file_signals[oparl_key] = signals_hit
            if oparl_key in names or table == "File":
                matched.append({
                    "id": f"{table}_{oparl_key}",
                    "type": table,
                    "oparlKey": oparl_key,
                    "name": names.get(oparl_key),
                    "score": round(score, 5),
                    "signals": signals_hit,
                })

    matched.sort(key=lambda m: m["score"], reverse=True)
    file_candidates = sorted(file_fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return {
        "matched_entities": matched,
        "file_candidates": [
            {"oparlKey": k, "score": s, "signals": file_signals.get(k, {})}
            for k, s in file_candidates
        ],
    }
