"""kgQueries — read access to the kg_* PostgreSQL layer for the app
(change: kg-app-integration).

Read-only helpers used by the API layer (apiServer) and the app-facing
kg features:

* ``statements_for_papers``  — grounding blocks per paper (request +
  response statements joined through kg_pairs; flagged fields excluded
  per the kgFlagFailures contract)
* ``related_by_tags``        — documents sharing ≥ 2 kg-topic tags with
  the given top documents (confidence-weighted, no model calls)
* ``file_name_for_key``      — display fields for a File oparl_key.

All queries are right for the live store (kg_* tables, 8,301 pairs) and
use read-only sessions.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from src.db import get_engine


def statements_for_papers(paper_sids: list[int]) -> dict[int, dict[str, Any]]:
    """Grounding blocks per paper sid.

    Returns ``{paper_sid: {"pair_id": …, "request": {…}, "response": {…},
    "flags": {…}}}`` — flagged fields are excluded from request/response
    (they live in the `_flagged` note block inside fields_json).
    """
    if not paper_sids:
        return {}
    e = get_engine(readonly=True)
    out: dict[int, dict[str, Any]] = {}
    with e.connect() as c:
        rows = c.execute(text(
            """
            SELECT kp.paper_sid, kp.pair_id, ks.stage, ks.fields_json
            FROM kg_statements ks JOIN kg_pairs kp ON kp.pair_id = ks.pair_id
            WHERE kp.paper_sid = ANY(:sids) AND ks.stage IN ('request', 'response')
            ORDER BY kp.paper_sid, ks.stage
            """), {"sids": paper_sids}).fetchall()
        # process inside the same open context — no post-close access

        for r in rows:
            fields = r[3] if isinstance(r[3], dict) else json_loads(r[3])
            entry = out.setdefault(r[0], {"pair_id": r[1]})
            flags = fields.pop("_flags", {})
            fields.pop("_flagged", None)
            # exclude flagged fields from the grounded values
            for f in flags:
                fields.pop(f, None)
            entry[stage_key(r[2])] = fields
            entry.setdefault("flags", {})
            if flags:
                entry["flags"][stage_key(r[2])] = flags
    return out


def stage_key(stage: str) -> str:
    return stage if stage in ("request", "response") else stage


def related_by_tags(
    top_files: list[tuple[str, float]],
    limit: int = 10,
    min_shared: int = 2,
) -> list[dict[str, Any]]:
    """Documents sharing ≥ min_shared kg-topic tags with the top files.

    ``top_files``: [(oparlKey, score)] of the search's best hits (score
    unused for scoring — relatedness is purely tag-based). Returns
    ``[{oparl_key, name, shared_tags: [names], score}]`` ordered by
    score desc, excluding the top documents themselves.

    Score = Σ over shared tags of (1 + confidence of the strongest
    assignment) — deterministic, no model calls.
    """
    if not top_files:
        return []
    keys = [k for k, _ in top_files]
    e = get_engine(readonly=True)
    with e.connect() as c:
        rows = c.execute(text(
            """
            WITH my_tags AS (
                SELECT a2.tag_id, MAX(a2.confidence) AS conf, MAX(t2.tag) AS tag_name
                FROM "File_tags_assoc" a2
                JOIN "File_tags" t2 ON t2.id = a2.tag_id
                WHERE a2.oparl_key = ANY(:keys) AND a2.scheme = 'kg-topic'
                GROUP BY a2.tag_id
            )
            SELECT a.oparl_key,
                   COUNT(DISTINCT a.tag_id) AS shared,
                   SUM(1 + COALESCE(my_tags.conf, 0.5)) AS score,
                   array_agg(DISTINCT my_tags.tag_name) AS shared_names
            FROM "File_tags_assoc" a
            JOIN my_tags ON my_tags.tag_id = a.tag_id
            WHERE a.oparl_key != ALL(:keys) AND a.scheme = 'kg-topic'
            GROUP BY a.oparl_key
            HAVING COUNT(DISTINCT a.tag_id) >= :min_shared
            ORDER BY score DESC
            LIMIT :limit
            """), {"keys": keys, "min_shared": min_shared, "limit": limit}).fetchall()
    related = [
        {"oparl_key": r[0], "shared": r[1], "score": float(r[2]),
         "shared_tags": list(r[3]), "name": None}
        for r in rows
    ]
    # resolve display names in one query
    if related:
        want = [r["oparl_key"] for r in related]
        with e.connect() as c:
            fs = c.execute(text(
                'SELECT "oparlKey", name, filename, date, teaser FROM "File" '
                'WHERE "oparlKey" = ANY(:ks)'), {"ks": want}).fetchall()
            fmap = {n[0]: n for n in fs}
        for r in related:
            fr = fmap.get(r["oparl_key"])
            if fr is None:
                continue
            r["name"] = fr[1] or fr[2] or fr[0]
            r["year"] = str(fr[3])[:4] if fr[3] else None
            r["teaser"] = fr[4]
            r["downloadurl"] = (f"/file-proxy/{fr[0].split('/')[-1]}") if fr[0] else None
    return [r for r in related if r["name"]]


def file_sid_for_key(keys: list[str]) -> dict[str, int | None]:
    """oparlKey → File.sid map for the given keys (None when missing)."""
    if not keys:
        return {}
    e = get_engine(readonly=True)
    with e.connect() as c:
        rows = c.execute(text(
            'SELECT "oparlKey", sid FROM "File" WHERE "oparlKey" = ANY(:ks)'),
            {"ks": keys}).fetchall()
    found = {r[0]: r[1] for r in rows}
    return {k: found.get(k) for k in keys}


def json_loads(raw: Any) -> dict:
    import json as _json
    if isinstance(raw, (str, bytes)):
        return _json.loads(raw)
    return dict(raw) if isinstance(raw, dict) else {}


_TOPIC_CACHE: dict | None = None


def topic_focus_for_query(query: str, threshold: float = 0.30) -> str | None:
    """Topic focus for the intent router (design D3, kg-app-integration).

    One query embed vs. 23 cached topic-description vectors — returns
    the best topic name above the threshold, else None. Vectors are
    computed once per process from `config/kg_vocabulary.yaml`
    (kgTagSchema seeded) via bge-m3 (shared embed endpoint) — the same
    embed call the hybrid search makes.
    """
    global _TOPIC_CACHE
    if _TOPIC_CACHE is None:
        from src.kg.kgVocab import load_vocab
        from src.remote import embed_batch
        vocab = load_vocab()
        tags = list((vocab.get("file_tags") or {}).items())
        descs = [str(spec.get("description", tag)) for tag, spec in tags]
        vecs = embed_batch(descs)  # ONE batched request (18s → <1s cold)
        _TOPIC_CACHE = {tag: (vec.tolist() if hasattr(vec, "tolist") else list(vec))
                        for (tag, _spec), vec in zip(tags, vecs)}
    if not _TOPIC_CACHE:
        return None
    try:
        from src.remote import embed as _embed
        qv = _embed(query)
    except Exception:  # pragma: no cover — embed unreachable
        return None
    best, best_sim = None, 0.0
    for tag, tv in _TOPIC_CACHE.items():
        dot = sum(x * y for x, y in zip(qv, tv))
        na = sum(x * x for x in qv) ** 0.5
        nb = sum(x * x for x in tv) ** 0.5
        sim = dot / (na * nb) if na and nb else 0.0
        if sim > best_sim:
            best, best_sim = tag, sim
    return best if best and best_sim >= threshold else None
