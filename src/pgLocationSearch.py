"""Location-scoped retrieval (change: add-location-intent).

Retrieves documents for a resolved location (street/district) through the
geo association tables instead of hybrid recall: all non-boilerplate-gated
agenda items and files linked to the location become candidates —
deterministically, independent of embedding similarity or spelling variants.

Files are capped at ``top_k`` (ordered by name similarity to the query, then
recency) and pass through the same rerank stage as a hybrid search; the
stage-1 result contract (top_files, matched_entities, facets,
applied_filters) is identical, so timeline/graph/summarize/map consume the
answer unchanged.
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

from typing import Any, Dict, List

import sqlalchemy as sa
from sqlalchemy import MetaData, Table, select

# location type -> association tables (file refs created by pgAddFileGeoRefs,
# agenda refs by pgAddStreetRefs / pgAddDistrictRefs)
GEO_ASSOC = {
    "street": {
        "agenda": "Streets_items_AgendaItems",
        "file": "Streets_items_Files",
        "loc_col": "street_id",
    },
    "district": {
        "agenda": "Districts_items_AgendaItems",
        "file": "Districts_items_Files",
        "loc_col": "district_id",
    },
}

AGENDA_ITEM_CAP = 50
RERANK_ACCEPT = 0.8  # same acceptance cutoff as search_stage


def _gate_filter(tbl, q):
    """Exclude gate_status='boilerplate' rows (same rule as pgGeo)."""
    col = tbl.c.get("gate_status")
    if col is None:
        return q
    return q.where(sa.or_(col.is_(None), col != "boilerplate"))


def _linked_rows(conn, assoc_name, loc_col, loc_id, entity_tbl, name_col,
                 query_norm):
    """Rows of one association table joined to their entity: each result
    row carries all entity columns plus ``sim`` (the entity name's trigram
    similarity to the query — deterministic fused order for the top_k cap,
    recency and sid as tie-breaks)."""
    assoc = Table(assoc_name, MetaData(), autoload_with=conn)
    join_cond = (assoc.c.file_id == entity_tbl.c.sid
                 if "file_id" in assoc.c
                 else assoc.c.agendaitem_id == entity_tbl.c.sid)
    stmt = (
        select(entity_tbl, sa.func.similarity(
            sa.func.lower(name_col), query_norm).label("sim"))
        .select_from(entity_tbl.join(assoc, join_cond))
        .where(assoc.c[loc_col] == loc_id)
        .order_by(sa.desc("sim"), entity_tbl.c.sid)
    )
    stmt = _gate_filter(assoc, stmt)
    return conn.execute(stmt).all()


def _latest_meeting_dates(conn):
    """Max meeting start_date per file sid (change D6: broad location
    answers are truncated newest-first by attached meeting)."""
    fm = Table("File__meeting__Meeting", MetaData(), autoload_with=conn)
    meeting = Table("Meeting", MetaData(), autoload_with=conn)
    stmt = (
        select(fm.c.srcSid, sa.func.max(meeting.c.start_date).label("d"))
        .select_from(fm.join(meeting, fm.c.tgtSid == meeting.c.sid))
        .group_by(fm.c.srcSid)
    )
    return {sid: d for sid, d in conn.execute(stmt)}


def candidate_files(conn, locations, query_norm, top_k):
    """Files linked to any resolved location, deduplicated and capped at
    top_k, ordered by attached-meeting recency (newest first; files without
    a meeting link fall back to their publication date so they do not
    vanish). Returns (capped_rows, total_visible_count)."""
    file_tbl = Table("File", MetaData(), autoload_with=conn)
    by_sid: Dict[Any, Any] = {}
    for loc in locations:
        geo = GEO_ASSOC.get(loc.get("type"))
        if not geo:
            continue
        for row in _linked_rows(conn, geo["file"], geo["loc_col"], loc["id"],
                                file_tbl, file_tbl.c.name, query_norm):
            prev = by_sid.get(row.sid)
            if prev is None or row.sim > prev[1]:
                by_sid[row.sid] = (row, float(row.sim))
    meeting_dates = _latest_meeting_dates(conn)

    def _recency_key(t):
        row = t[0]
        d = meeting_dates.get(row.sid) or row.date
        return (-(d.toordinal() if d is not None else 0), row.sid)

    rows = sorted(by_sid.values(), key=_recency_key)
    return rows[:top_k], len(rows)


def candidate_agenda_items(conn, locations, query_norm, cap=AGENDA_ITEM_CAP):
    """Agenda items linked to any resolved location, deduplicated, ordered
    by name similarity to the query, capped."""
    agenda_tbl = Table("AgendaItem", MetaData(), autoload_with=conn)
    by_sid: Dict[Any, Any] = {}
    for loc in locations:
        geo = GEO_ASSOC.get(loc.get("type"))
        if not geo:
            continue
        for row in _linked_rows(conn, geo["agenda"], geo["loc_col"], loc["id"],
                                agenda_tbl, agenda_tbl.c.name, query_norm):
            prev = by_sid.get(row.sid)
            if prev is None or row.sim > prev[1]:
                by_sid[row.sid] = (row, float(row.sim))
    rows = sorted(by_sid.values(), key=lambda t: (-t[1], t[0].sid))
    return rows[:cap]


def _rerank_file(session, query: str, file_tbl, oparl_key: str) -> float:
    """Rerank score for one file. The location path has no content-vector
    recall, hence no best-chunk index — the reranker input is File.content
    (same as search_stage's legacy path). Returns None when the file has no
    content — the caller keeps such files, mirroring search_stage."""
    from src.pgTimeline import RERANK_MODE, call_reranking_chat_model, call_reranking_model

    row = session.execute(
        select(file_tbl.c.content).where(file_tbl.c.oparlKey == oparl_key)
    ).first()
    content = row[0] if row and row[0] else None
    if content is None:
        return None
    if RERANK_MODE == "chat":
        return call_reranking_chat_model(query, content)
    scores = call_reranking_model(query, [content], top_n=1)
    return scores[0] if scores else None


def location_search_stage(session, query: str, locations: List[Dict[str, Any]],
                          top_k: int = 10, summarize: bool = True) -> Dict[str, Any]:
    """Stage-1-shaped answer for a resolved location (see module docstring).

    ``locations`` is the resolver's accepted list: [{type, id, name, score}].
    """
    from src.pgHybridSearch import facets
    from src.pgTimeline import RERANK_MODE

    query_norm = (query or "").strip().lower()
    engine = session.bind
    with engine.connect() as conn:
        file_rows, total_files = candidate_files(conn, locations, query_norm,
                                                 top_k)
        agenda_rows = candidate_agenda_items(conn, locations, query_norm)
        facets_data = facets(conn)
    file_tbl = Table("File", MetaData(), autoload_with=engine)

    matched_entities: List[Dict[str, Any]] = []
    for ai, sim in agenda_rows:
        matched_entities.append({
            "id": f"AgendaItem_{ai.oparlKey}",
            "type": "AgendaItem",
            "oparlKey": ai.oparlKey,
            "name": ai.name,
            "score": round(sim, 5),
            "signals": {"location": True},
        })

    # rerank the capped candidate files, same acceptance rule as search_stage
    top_files: List[Dict[str, Any]] = []
    for f, sim in file_rows:
        if RERANK_MODE is not None:
            rscore = _rerank_file(session, query, file_tbl, f.oparlKey)
            if rscore is None or not isinstance(rscore, (int, float)) or rscore < RERANK_ACCEPT:
                continue
        top_files.append({
            "sid": f.sid,
            "oparlKey": f.oparlKey,
            "name": f.name,
            "fileName": f.filename,
            "downloadurl": f.downloadurl,
            "oparlId": f.oparlId,
            "date": f.date,
            "distance": None,
            "match": {"location": True},
        })

    for f_ in top_files:
        matched_entities.append({
            "id": f"File_{f_['oparlKey']}",
            "type": "File",
            "oparlKey": f_["oparlKey"],
            "name": f_["name"],
            "score": None,
            "signals": {"location": True},
        })

    result = {
        "query": query,
        "top_files": top_files,
        "matched_entities": matched_entities,
        "facets": facets_data,
        "applied_filters": [],
        "notes": [],
    }
    if total_files > len(top_files):
        loc_names = ", ".join(loc["name"] for loc in locations)
        result["notes"].append(
            f"{total_files} Dateien zu '{loc_names}' gefunden; die neuesten "
            f"{len(top_files)} werden angezeigt. Grenzen Sie die Anfrage "
            "ein (Zeitraum, Thema) oder schliessen Sie Dokumente in der "
            "Dokumentenliste aus."
        )
    if summarize:
        from src.pgResultSummarizer import ResultSummarizer

        ResultSummarizer(session).summarize(result)
    return result
