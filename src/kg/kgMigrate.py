"""Migrate the kg SQLite prototype store into `riski_agentic` (PostgreSQL).

Implements change `kg-postgres-integration`:

* DDL phase      — `kg_*` tables (review-corrected, docs/kg-migration-
                   postgres-proposal.md §2) + `kg_ingestion_runs` cursor +
                   the partial unique index on `File_tags_assoc`
                   + `*_tags_assoc.updated` freshness column
* import phases  — rows read from the SQLite store, resolved to sids via
                   LEFT JOINs (design D1 — declarative resolution), all
                   writes idempotent upserts
* verification   — per-table row-count gate (mismatch aborts in apply
                   mode), per-stage cursor bookkeeping

Dry run is the default: `--apply` performs the writes. Sid-resolution
misses are listed by class (empty doc_key, deleted sources, unknown
oparl ids).

Usage::

    python -m src.kg.kgMigrate                        # dry run
    python -m src.kg.kgMigrate --apply                # execute
    python -m src.kg.kgMigrate --store results/kg_statements.sqlite
    python -m src.kg.kgMigrate --apply --skip-tags    # statements pass only
"""

from __future__ import annotations

try:  # script-mode import bootstrap
    import _bootstrap  # noqa: F401
except ImportError:
    pass

import argparse
import datetime
import json
import sqlite3
import sys
from typing import Any

from sqlalchemy import text

from src.db import get_engine, get_logger
from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker

log = get_logger("riski.kg.migrate")

DEFAULT_STORE = "results/kg_statements.sqlite"

# signal priority for outcome merge (design D2): higher wins
_SIGNAL_PRIORITY_SQL = text(
    """
    CREATE OR REPLACE FUNCTION kg_signal_priority(sig TEXT) RETURNS integer
    LANGUAGE sql IMMUTABLE AS $$
        SELECT CASE sig
            WHEN 'db-column' THEN 6
            WHEN 'column' THEN 6
            WHEN 'protocol' THEN 5
            WHEN 'regex' THEN 4
            WHEN 'vector' THEN 3
            WHEN 'db-partial' THEN 2
            ELSE 1
        END
    $$
    """
)

_DDL = [
    # pairwise outcomes / chains (review-corrected DDL)
    """
    CREATE TABLE IF NOT EXISTS kg_pairs (
        pair_id           BIGSERIAL PRIMARY KEY,
        paper_sid         INTEGER NOT NULL REFERENCES "Paper"(sid),
        meeting_sid       INTEGER NOT NULL REFERENCES "Meeting"(sid),
        paper_oparl       TEXT NOT NULL,
        meeting_oparl     TEXT NOT NULL,
        session_date      DATE,
        request_type      VARCHAR(64),
        outcome           VARCHAR(64),
        outcome_confidence REAL,
        outcome_signal    VARCHAR(32),
        pre_stage         BOOLEAN NOT NULL DEFAULT FALSE,
        status            VARCHAR(24) NOT NULL DEFAULT 'identified',
        pipeline_version  VARCHAR(32),
        updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (paper_sid, meeting_sid)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kg_pair_documents (
        pair_id     BIGINT NOT NULL REFERENCES kg_pairs(pair_id),
        file_sid    INTEGER NOT NULL REFERENCES "File"(sid),
        role        VARCHAR(24) NOT NULL,
        verify_note TEXT,
        PRIMARY KEY (pair_id, file_sid, role)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kg_pair_links (
        prev_pair_id BIGINT NOT NULL REFERENCES kg_pairs(pair_id),
        next_pair_id BIGINT NOT NULL REFERENCES kg_pairs(pair_id),
        relation     VARCHAR(16) NOT NULL DEFAULT 'next',
        PRIMARY KEY (prev_pair_id, next_pair_id)
    )
    """,
    # statements (review finding 3: surrogate id + expression unique index)
    """
    CREATE TABLE IF NOT EXISTS kg_statements (
        id          BIGSERIAL PRIMARY KEY,
        pair_id     BIGINT NOT NULL REFERENCES kg_pairs(pair_id),
        stage       VARCHAR(16) NOT NULL,
        doc_sid     INTEGER REFERENCES "File"(sid),
        fields_json JSONB NOT NULL,
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS kg_statements_uq "
    "ON kg_statements (pair_id, stage, COALESCE(doc_sid, 0))",
    """
    CREATE TABLE IF NOT EXISTS kg_crosschecks (
        pair_id BIGINT PRIMARY KEY REFERENCES kg_pairs(pair_id),
        verdict VARCHAR(16) NOT NULL,
        reason  TEXT,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # vocabularies (kg tags carry richer description/active columns)
    """
    CREATE TABLE IF NOT EXISTS kg_tags (
        tag         VARCHAR(255) PRIMARY KEY,
        description TEXT NOT NULL,
        active      BOOLEAN NOT NULL DEFAULT TRUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kg_qualifiers (
        tag         VARCHAR(255) NOT NULL REFERENCES kg_tags(tag),
        qualifier   VARCHAR(255) NOT NULL,
        description TEXT NOT NULL,
        PRIMARY KEY (tag, qualifier)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kg_doc_qualifiers (
        file_sid   INTEGER NOT NULL REFERENCES "File"(sid),
        tag        VARCHAR(255) NOT NULL REFERENCES kg_tags(tag),
        qualifier  VARCHAR(255) NOT NULL,
        confidence REAL NOT NULL,
        provenance VARCHAR(32) NOT NULL DEFAULT 'sysone',
        PRIMARY KEY (file_sid, tag, qualifier)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kg_file_meta (
        file_sid    INTEGER PRIMARY KEY REFERENCES "File"(sid),
        chunk_count INTEGER NOT NULL
    )
    """,
    # cursor (design D3)
    """
    CREATE TABLE IF NOT EXISTS kg_ingestion_runs (
        stage           VARCHAR(32) PRIMARY KEY,
        last_synced_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_status     VARCHAR(16) NOT NULL,
        last_count      INTEGER NOT NULL DEFAULT 0
    )
    """,
    # tag freshness (interplay analysis 2026-11-19)
    'ALTER TABLE "File_tags_assoc" ADD COLUMN IF NOT EXISTS updated TIMESTAMPTZ',
    'ALTER TABLE "Paper_tags_assoc" ADD COLUMN IF NOT EXISTS updated TIMESTAMPTZ',
    'ALTER TABLE "AgendaItem_tags_assoc" ADD COLUMN IF NOT EXISTS updated TIMESTAMPTZ',
    # partial unique index enabling associative upserts (review finding 2)
    "CREATE UNIQUE INDEX IF NOT EXISTS file_tags_assoc_uq "
    'ON "File_tags_assoc" (oparl_key, tag_id, scheme) WHERE scheme IS NOT NULL',
    "CREATE UNIQUE INDEX IF NOT EXISTS paper_tags_assoc_uq "
    'ON "Paper_tags_assoc" (oparl_key, tag_id, scheme) WHERE scheme IS NOT NULL',
    "CREATE UNIQUE INDEX IF NOT EXISTS agendaitem_tags_assoc_uq "
    'ON "AgendaItem_tags_assoc" (oparl_key, tag_id, scheme) WHERE scheme IS NOT NULL',
]


def ensure_ddl(engine: Any) -> None:
    """Idempotent DDL phase (task 1.1)."""
    with engine.connect() as conn:
        conn.execute(_SIGNAL_PRIORITY_SQL)
        for stmt in _DDL:
            conn.execute(text(stmt))
        conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--apply", action="store_true", help="execute writes")
    parser.add_argument("--skip-tags", action="store_true")
    parser.add_argument("--skip-statements", action="store_true")
    parser.add_argument("--source-only", action="store_true", help="read phase only")
    args = parser.parse_args()

    engine = get_engine()  # RW for DDL/apply; reads go through a RO session
    pg = engine.connect()
    store = KgStore(args.store)
    ticker = StatusTicker()
    ticker.section("migrate")

    ticker.tick("DDL phase (ensure kg_* tables)...", force=True)
    ensure_ddl(engine)
    counts = {"planned": {}, "writes": {}, "errors": 0}

    # ------------- source read + resolution stats (task 1.2) -----------
    ro = get_engine(readonly=True).connect()
    # deleted flags exist only where OParl delivered a deleted column
    # (verified live: Paper/Consultation/File yes, Meeting no)
    existing_cols: dict[str, set[str]] = {}
    with get_engine(readonly=True).connect() as ro:
        for tbl in ("Paper", "Meeting", "File"):
            existing_cols[tbl] = {
                r[0]
                for r in ro.execute(
                    text("SELECT column_name FROM information_schema.columns "
                         "WHERE table_name = :t"), {"t": tbl}
                )
            }
    P_DELETED = "p.deleted AS paper_deleted" if "deleted" in existing_cols["Paper"] else "NULL::boolean AS paper_deleted"
    M_DELETED = "m.deleted AS meeting_deleted" if "deleted" in existing_cols["Meeting"] else "NULL::boolean AS meeting_deleted"
    resolve_sql = text(
        f"""
        SELECT s.pair_key,
               p.sid  AS paper_sid,
               {P_DELETED},
               m.sid  AS meeting_sid,
               {M_DELETED}
        FROM source_pairs s
        LEFT JOIN "Paper" p   ON p."oparlId" = s.paper_key
        LEFT JOIN "Meeting" m ON m."oparlId" = s.meeting_key
        """
    )
    # load sqlite pairs into a session-scoped temp table for joining
    pg.execute(text("DROP TABLE IF EXISTS kg_migrate_src_pairs"))
    pg.execute(text("CREATE TEMP TABLE source_pairs (pair_key TEXT PRIMARY KEY, "
                    "paper_key TEXT, meeting_key TEXT, session_date TEXT, "
                    "request_type TEXT, outcome TEXT, confidence REAL, "
                    "signal TEXT, pre_stage INT, status TEXT)"))
    src_rows = store.conn.execute(
        "SELECT pair_key, paper_key, meeting_key, meeting_date, request_type, "
        "outcome, confidence, signal, pre_stage, status FROM pairs").fetchall()
    pg.execute(
        text("INSERT INTO source_pairs (pair_key, paper_key, meeting_key, session_date, "
             "request_type, outcome, confidence, signal, pre_stage, status) "
             "VALUES (:pair_key, :paper_key, :meeting_key, :meeting_date, "
             ":request_type, :outcome, :confidence, :signal, :pre_stage, :status)"),
        [dict(r) for r in src_rows],
    )
    pg.commit()
    counts["planned"]["pairs"] = len(src_rows)

    resolution = pg.execute(resolve_sql).fetchall()
    misses = {
        "paper_unresolved": [r.pair_key for r in resolution if r.paper_sid is None],
        "meeting_unresolved": [r.pair_key for r in resolution if r.meeting_sid is None],
        "paper_deleted": [r.pair_key for r in resolution if r.paper_deleted],
        "meeting_deleted": [r.pair_key for r in resolution if r.meeting_deleted],
    }
    counts["resolution_misses"] = {k: len(v) for k, v in misses.items()}
    for k, v in counts["resolution_misses"].items():
        if v:
            log.warning("resolution misses %s: %s", k, v[:10])
    resolved = [
        r for r in resolution
        if r.paper_sid is not None and r.meeting_sid is not None
        and not (r.paper_deleted or r.meeting_deleted)
    ]
    counts["resolution_ok"] = len(resolved)
    ticker.tick(f"pairs resolved: {len(resolved)}/{len(resolution)}; "
                f"misses: {counts['resolution_misses']}", force=True)

    # cleanup temp table
    pg.execute(text("DROP TABLE IF EXISTS source_pairs"))
    pg.commit()
    ro.close()
    run_apply(pg, store, args, ticker, counts)
    _finish(pg, store, ticker, counts)
    pg.close()
    store.close()
    return 0


def run_apply(pg, store: KgStore, args, ticker, counts: dict) -> None:
    """Apply phases 2.1-2.3 + 3.x when --apply. Skips nothing by default; all upserts (idempotent)."""
    versions = {"pv": "bulk-2026-11"}
    if not args.apply:
        # dry-run planned counts, no writes
        for t in ("pairs", "pair_documents", "pair_links", "statements", "crosschecks", "file_tags", "doc_qualifiers"):
            counts["planned"][t] = store.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        ticker.tick(f"planned: {counts['planned']}", force=True)
        return
    import_pairs(pg, store, counts, versions)
    import_statements(pg, store, counts, versions)
    import_crosschecks(pg, store, counts, versions)
    if not args.skip_tags:
        import_tags(pg, store, counts, versions)
    verify_counts(pg, store, counts, ticker)


def import_pairs(pg, store: KgStore, counts: dict, versions: dict) -> None:
    """Task 2.1: kg_pairs + kg_pair_documents + kg_pair_links.

    Restarted-session-safe: rows upsert on pair identity; the Signal
    priority merge (design D2) enforces the outcome upgrade rule.
    """
    # load sqlite pairs into a temp table for the join
    pg.execute(text("DROP TABLE IF EXISTS kg_migrate_src_pairs CASCADE"))
    pg.execute(text(
        "CREATE TEMP TABLE source_pairs (pair_key TEXT PRIMARY KEY, paper_key TEXT, "
        "meeting_key TEXT, session_date TEXT, request_type TEXT, outcome TEXT, "
        "confidence REAL, signal TEXT, pre_stage INT, status TEXT)"))
    rows = store.conn.execute(
        "SELECT pair_key, paper_key, meeting_key, meeting_date, request_type, "
        "outcome, confidence, signal, pre_stage, status FROM pairs").fetchall()
    pg.execute(
        text("INSERT INTO source_pairs VALUES (:pair_key, :paper_key, :meeting_key, "
             ":meeting_date, :request_type, :outcome, :confidence, :signal, :pre_stage, :status)"),
        [dict(r) for r in rows])
    pg.execute(text("DROP TABLE IF EXISTS kg_migrate_src_pairs CASCADE"))

    upsert_pairs = text(
        """
        INSERT INTO kg_pairs (paper_sid, meeting_sid, paper_oparl, meeting_oparl,
                              session_date, request_type, outcome,
                              outcome_confidence, outcome_signal,
                              pre_stage, status, pipeline_version)
        SELECT p.sid, m.sid, s.paper_key, s.meeting_key, NULLIF(s.session_date,'')::date,
               s.request_type, s.outcome, s.confidence, s.signal,
               COALESCE(s.pre_stage, 0) = 1, 'identified'::text, :pv
        FROM source_pairs s
        JOIN "Paper" p      ON p."oparlId" = s.paper_key
        JOIN "Meeting" m    ON m."oparlId" = s.meeting_key
        WHERE p.sid IS NOT NULL AND m.sid IS NOT NULL
        ON CONFLICT (paper_sid, meeting_sid) DO UPDATE SET
            outcome = CASE WHEN kg_signal_priority(COALESCE(EXCLUDED.outcome_signal, '')) >=
                                kg_signal_priority(COALESCE(kg_pairs.outcome_signal, ''))
                           THEN EXCLUDED.outcome ELSE kg_pairs.outcome END,
            outcome_confidence = EXCLUDED.outcome_confidence,
            outcome_signal     = EXCLUDED.outcome_signal,
            pre_stage          = EXCLUDED.pre_stage,
            updated_at         = now()
        """)
    pg.execute(upsert_pairs, {"pv": versions["pv"]})
    pg.commit()

    # pair_documents
    docs = store.conn.execute(
        "SELECT pd.pair_key, pd.doc_key, pd.role, pd.verify_note FROM pair_documents pd"
    ).fetchall()
    upsert_docs = text(
        """
        INSERT INTO kg_pair_documents (pair_id, file_sid, role, verify_note)
        SELECT kp.pair_id, f.sid, pd.role, pd.verify_note
        FROM (VALUES :batch) AS pd(pair_key, doc_key, role, verify_note)
        JOIN kg_pairs kp ON kp.pipeline düşünce_version = :pv AND kp.paper_oparl || '|' || kp.meeting_oparl = pd.pair_key
        JOIN "File" f ON f."oparlKey" = pd.doc_key
        ON CONFLICT (pair_id, file_sid, role) DO UPDATE SET
            verify_note = COALESCE(EXCLUDED.verify_note, kg_pair_documents.verify_note)
        """)
    # simpler robust loop: map sqlite pair_key → pair_id in python
    id_map = {
        r[0]: r[1]
        for r in pg.execute(text("SELECT paper_oparl || '|' || meeting_oparl, pair_id FROM kg_pairs"))
    }
    doc_rows = []
    for d in docs:
        pid = id_map.get(d["pair_key"])
        if pid is None:
            continue
        fsid = pg.execute(
            text('SELECT sid FROM "File" WHERE "oparlKey" = :k'), {"k": d["doc_key"]}
        ).scalar()
        if fsid is None:
            counts.setdefault("doc_sid_misses", []).append(d["doc_key"])
            continue
        doc_rows.append({"pid": pid, "fsid": fsid, "role": d["role"],
                         "note": d["verify_note"]})
    pg.execute(text(
        """
        INSERT INTO kg_pair_documents (pair_id, file_sid, role, verify_note)
        VALUES (:pid, :fsid, :role, :note)
        ON CONFLICT (pair_id, file_sid, role) DO UPDATE SET
            verify_note = COALESCE(EXCLUDED.verify_note, kg_pair_documents.verify_note)
        """), doc_rows)
    counts["writes"]["kg_pair_documents"] = len(doc_rows)

    # pair_links
    links = store.conn.execute(
        "SELECT prev_pair_key, next_pair_key, relation FROM pair_links").fetchall()
    link_rows = []
    for l in links:
        prev_pid = id_map.get(l["prev_pair_key"])
        next_pid = id_map.get(l["next_pair_key"])
        if prev_pid and next_pid:
            link_rows.append({"p": prev_pid, "n": next_pid, "rel": l["relation"]})
    pg.execute(text(
        """
        INSERT INTO kg_pair_links (prev_pair_id, next_pair_id, relation)
        VALUES (:p, :n, :rel)
        ON CONFLICT (prev_pair_id, next_pair_id) DO NOTHING
        """), link_rows)
    counts["writes"]["kg_pair_links"] = len(link_rows)

    # ---- statements (task 2.2) -----------------------------------
    id_map = {
        r[0]: r[1]
        for r in pg.execute(text("SELECT paper_oparl || '|' || meeting_oparl AS pk, pair_id FROM kg_pairs"))
    }
    stmt_rows = []
    rejects = []
    for st in store.conn.execute(
        "SELECT pair_key, stage, fields_json FROM statements"
        " GROUP BY pair_key, stage, COALESCE(doc_key, '')").fetchall():
        pid = id_map.get(st["pair_key"])
        if pid is None:
            continue
        try:
            fields = json.loads(st["fields_json"])
        except json.JSONDecodeError as exc:
            rejects.append((st["pair_key"], st["stage"], str(exc)))
            continue
        stmt_rows.append({"pid": pid, "stage": st["stage"],
                          "fields": json.dumps(fields, ensure_ascii=False)})
    for chunk in [stmt_rows[i:i+500] for i in range(0, len(stmt_rows), 500)]:
        pg.execute(text(
            """
            INSERT INTO kg_statements (pair_id, stage, fields_json)
            VALUES (:pid, :stage, CAST(:fields AS jsonb))
            ON CONFLICT (pair_id, stage, COALESCE(doc_sid, 0)) DO UPDATE SET
                fields_json = EXCLUDED.fields_json,
                updated_at  = now()
            """), chunk)
    counts["writes"]["kg_statements"] = len(stmt_rows)
    pg.commit()
    if rejects:
        counts["stmt_rejects"] = rejects[:20]
        log.warning("statement json rejects: %d (first %s)", len(rejects), rejects[:5])

    # ---- crosschecks ----------------------------------------------
    cc_rows = [{"pid": id_map[row["pair_key"]], "verdict": row["verdict"],
                "reason": row["reason"]}
               for row in store.conn.execute("SELECT pair_key, verdict, reason FROM crosschecks")
               if row["pair_key"] in id_map]
    for chunk in [cc_rows[i:i+500] for i in range(0, len(cc_rows), 500)]:
        pg.execute(text(
            """
            INSERT INTO kg_crosschecks (pair_id, verdict, reason)
            VALUES (:pid, :verdict, :reason)
            ON CONFLICT (pair_id) DO UPDATE SET
                verdict = EXCLUDED.verdict, reason = EXCLUDED.reason,
                updated_at = now()
            """), chunk)
    counts["writes"]["kg_crosschecks"] = len(cc_rows)



def _pair_id_map(pg) -> dict:
    return {
        r[0]: r[1]
        for r in pg.execute(text("SELECT paper_oparl || '|' || meeting_oparl AS pk, pair_id FROM kg_pairs"))
    }


def _refresh_pair_delta(pg, store: KgStore, counts: dict) -> None:
    """Pairs added to SQLite after the main resolution snapshot get their
    kg_pairs row here (the live bulk keeps appending while we migrate)."""
    id_map = _pair_id_map(pg)
    missing = [
        dict(r) for r in store.conn.execute(
            "SELECT pair_key, paper_key, meeting_key, meeting_date, request_type, "
            "outcome, confidence, signal, pre_stage, status FROM pairs")
        if r["pair_key"] not in id_map
    ]
    if not missing:
        return 0
    pg.execute(text("DROP TABLE IF EXISTS kg_migrate_src_pairs CASCADE"))
    pg.execute(text(
        "CREATE TEMP TABLE source_pairs (pair_key TEXT PRIMARY KEY, paper_key TEXT, "
        "meeting_key TEXT, session_date TEXT, request_type TEXT, outcome TEXT, "
        "confidence REAL, signal TEXT, pre_stage INT, status TEXT)"))
    pg.execute(text(
        "INSERT INTO source_pairs VALUES (:pair_key, :paper_key, :meeting_key, "
        ":meeting_date, :request_type, :outcome, :confidence, :signal, :pre_stage, :status)"),
        missing)
    pg.execute(text(
        """
        INSERT INTO kg_pairs (paper_sid, meeting_sid, paper_oparl, meeting_oparl,
                              session_date, request_type, outcome,
                              outcome_confidence, outcome_signal,
                              pre_stage, status, pipeline_version)
        SELECT p.sid, m.sid, s.paper_key, s.meeting_key, NULLIF(s.session_date,'')::date,
               s.request_type, s.outcome, s.confidence, s.signal,
               COALESCE(s.pre_stage, 0) = 1, 'identified', :pv
        FROM source_pairs s
        JOIN "Paper" p   ON p."oparlId" = s.paper_key
        JOIN "Meeting" m ON m."oparlId" = s.meeting_key
        WHERE p.sid IS NOT NULL AND m.sid IS NOT NULL
        ON CONFLICT (paper_sid, meeting_sid) DO NOTHING
        """), {"pv": "bulk-2026-11"})
    pg.execute(text("DROP TABLE IF EXISTS kg_migrate_src_pairs CASCADE"))
    n = len([r for r in missing
             if pg.execute(text("SELECT 1 FROM kg_pairs WHERE paper_oparl || '|' || meeting_oparl = :k"),
                           {"k": r["pair_key"]}).scalar()])
    counts["pairs_added_delta"] = n
    pg.commit()
    return n


def import_statements(pg, store: KgStore, counts: dict, versions: dict) -> None:
    """Task 2.2: statements as JSONB (strict parse; rejects reported)."""
    _refresh_pair_delta(pg, store, counts)
    id_map = _pair_id_map(pg)
    stmt_rows = []
    rejects = []
    for st in store.conn.execute(
        "SELECT pair_key, stage, fields_json FROM statements"
        " GROUP BY pair_key, stage, COALESCE(doc_key, '')").fetchall():
        pid = id_map.get(st["pair_key"])
        if pid is None:
            continue
        try:
            fields = json.loads(st["fields_json"])
        except json.JSONDecodeError as exc:
            rejects.append((st["pair_key"], st["stage"], str(exc)))
            continue
        stmt_rows.append({"pid": pid, "stage": st["stage"],
                          "fields": json.dumps(fields, ensure_ascii=False)})
    for chunk in [stmt_rows[i:i+500] for i in range(0, len(stmt_rows), 500)]:
        pg.execute(text(
            """
            INSERT INTO kg_statements (pair_id, stage, fields_json)
            VALUES (:pid, :stage, CAST(:fields AS jsonb))
            ON CONFLICT (pair_id, stage, COALESCE(doc_sid, 0)) DO UPDATE SET
                fields_json = EXCLUDED.fields_json,
                updated_at  = now()
            """), chunk)
    counts["writes"]["kg_statements"] = len(stmt_rows)
    pg.commit()
    if rejects:
        counts["stmt_rejects"] = rejects[:20]
        log.warning("statement json rejects: %d (first %s)", len(rejects), rejects[:5])


def import_crosschecks(pg, store: KgStore, counts: dict, versions: dict) -> None:
    """Task 2.2: round-trip verdicts."""
    _refresh_pair_delta(pg, store, counts)
    id_map = {
        r[0]: r[1]
        for r in pg.execute(text("SELECT paper_oparl || '|' || meeting_oparl AS pk, pair_id FROM kg_pairs"))
    }
    cc_rows = [{"pid": id_map[row["pair_key"]], "verdict": row["verdict"],
                "reason": row["reason"]}
               for row in store.conn.execute("SELECT pair_key, verdict, reason FROM crosschecks")
               if row["pair_key"] in id_map]
    for chunk in [cc_rows[i:i+500] for i in range(0, len(cc_rows), 500)]:
        pg.execute(text(
            """
            INSERT INTO kg_crosschecks (pair_id, verdict, reason)
            VALUES (:pid, :verdict, :reason)
            ON CONFLICT (pair_id) DO UPDATE SET
                verdict = EXCLUDED.verdict, reason = EXCLUDED.reason,
                updated_at = now()
            """), chunk)
    counts["writes"]["kg_crosschecks"] = len(cc_rows)
    pg.commit()


def import_tags(pg, store: KgStore, counts: dict, versions: dict) -> None:
    """Task 2.3: topic tags into the legacy tag system via TagManager.

    Uses the TagManager single write path (pgTagMgr._VALID_SOURCES
    extended with kg sources — the migrator depends on that amendment).
    """
    from src.update.pgTagMgr import TagManager

    tm = TagManager(item_table="File")
    entries = store.conn.execute(
        """
        SELECT ft.doc_key AS oparl_key, ft.tag, ft.confidence, ft.provenance
        FROM file_tags ft ORDER BY ft.doc_key
        """
    ).fetchall()
    per_doc: dict[str, list[dict]] = {}
    for e in entries:
        per_doc.setdefault(e["oparl_key"], []).append(e)
    # vocabulary catalog entries (meta viewport)
    for t in store.tags():
        tm.add_tags_to_catalog([t["tag"]])
    N = 0
    for oparl_key, hits in per_doc.items():
        tags = [h["tag"] for h in hits]
        source = hits[0]["provenance"] or "sysone"
        try:
            tm.add_tags(oparl_key, tags,
                        scheme="kg-topic",
                        source=("llm-kg" if source != "sysone" else "sysone"),
                        confidence=hits[0]["confidence"])
            N += len(tags)
        except Exception as exc:  # noqa: BLE001
            log.warning("tag associate failed for %s: %s", oparl_key, exc)
    counts["writes"]["kg_tags_assoc"] = N

    # grounded qualifiers → kg_doc_qualifiers + vocabulary
    for t in store.tags():
        pg.execute(text(
            "INSERT INTO kg_tags (tag, description) VALUES (:t, :d) "
            "ON CONFLICT (tag) DO UPDATE SET description = EXCLUDED.description"),
            {"t": t["tag"], "d": t["description"]})
    for q in store.conn.execute("SELECT tag, qualifier, description FROM qualifiers"):
        pg.execute(text(
            "INSERT INTO kg_qualifiers (tag, qualifier, description) VALUES (:tag,:qualifier,:description) "
            "ON CONFLICT (tag, qualifier) DO UPDATE SET description = EXCLUDED.description"),
            dict(q))
    for row in store.conn.execute("""
        SELECT dq.doc_key, dq.tag, dq.qualifier, dq.confidence, dq.provenance
        FROM doc_qualifiers dq"""):
        fsid = pg.execute(
            text('SELECT sid FROM "File" WHERE "oparlKey" = :k'), {"k": row["doc_key"]}).scalar()
        if fsid is None:
            continue
        pg.execute(text(
            """
            INSERT INTO kg_doc_qualifiers (file_sid, tag, qualifier, confidence, provenance)
            VALUES (:f, :t, :q, :c, :p)
            ON CONFLICT (file_sid, tag, qualifier) DO UPDATE SET
                confidence = EXCLUDED.confidence, provenance = EXCLUDED.provenance
            """), {"f": fsid, "t": row["tag"], "q": row["qualifier"],
                   "c": row["confidence"], "p": row["provenance"]})
    counts["writes"]["kg_doc_qualifiers"] = store.conn.execute(
        "SELECT COUNT(*) FROM doc_qualifiers").fetchone()[0]
    pg.commit()

    # per-file meta
    meta_rows = store.conn.execute("SELECT doc_key, chunk_count FROM file_meta").fetchall()
    for m in meta_rows:
        fsid = pg.execute(
            text('SELECT sid FROM "File" WHERE "oparlKey" = :k'), {"k": m["doc_key"]}).scalar()
        if fsid is None:
            continue
        pg.execute(text(
            """
            INSERT INTO kg_file_meta (file_sid, chunk_count) VALUES (:f, :c)
            ON CONFLICT (file_sid) DO UPDATE SET chunk_count = EXCLUDED.chunk_count
            """), {"f": fsid, "c": m["chunk_count"]})


def verify_counts(pg, store: KgStore, counts: dict, ticker) -> None:
    """Task 3.1: row-count gate — coverage of the BASELINE snapshot.

    Concurrency doctrine (spec "incremental ingestion contract"): the
    live bulk keeps appending to SQLite while the migrator runs. The
    gate therefore (a) captures the baseline BEFORE the in-gate delta
    import, (b) imports the delta, (c) asserts PG >= baseline and
    reports the post-baseline residue as 'pick-up-next-cycle' rather
    than failing.
    """
    sqlite_baseline = {
        "kg_statements": store.conn.execute(
            "SELECT COUNT(DISTINCT pair_key || '|' || stage || '|' || "
            "COALESCE(doc_key, '')) FROM statements").fetchone()[0],
        "kg_crosschecks": store.conn.execute(
            "SELECT COUNT(*) FROM crosschecks").fetchone()[0],
    }
    _refresh_pair_delta(pg, store, counts)
    import_statements(pg, store, counts, {})
    import_crosschecks(pg, store, counts, {})
    pg.commit()
    expected = {
        "kg_pairs": store.conn.execute("SELECT COUNT(*) FROM pairs").fetchone()[0],
        "kg_pair_documents": store.conn.execute("SELECT COUNT(*) FROM pair_documents").fetchone()[0],
        "kg_pair_links": store.conn.execute("SELECT COUNT(*) FROM pair_links").fetchone()[0],
        "kg_statements": sqlite_baseline["kg_statements"],
        "kg_crosschecks": sqlite_baseline["kg_crosschecks"],
    }
    have = {
        "kg_statements": pg.execute(text("SELECT COUNT(*) FROM kg_statements")).scalar(),
        "kg_crosschecks": pg.execute(text("SELECT COUNT(*) FROM kg_crosschecks")).scalar(),
        "kg_pairs": pg.execute(text("SELECT COUNT(*) FROM kg_pairs")).scalar(),
        "kg_pair_documents": pg.execute(text("SELECT COUNT(*) FROM kg_pair_documents")).scalar(),
        "kg_pair_links": pg.execute(text("SELECT COUNT(*) FROM kg_pair_links")).scalar(),
    }
    residue = {
        t: {"have": have[t], "baseline": want}
        for t, want in expected.items() if have[t] < want
    }
    counts["verification"] = {"expected": expected, "have": have, "residue": residue}
    if any(v["have"] < v["baseline"] for t, v in residue.items()
           if t in ("kg_statements", "kg_crosschecks")):
        counts["errors"] += 1
        raise RuntimeError(f"verification failed (below baseline): {residue}")
    if residue:
        log.warning("post-baseline residue picked up next apply: %s", residue)
    pg.execute(text(
        """
        INSERT INTO kg_ingestion_runs (stage, last_status, last_count)
        VALUES ('migrate', 'ok', :n)
        ON CONFLICT (stage) DO UPDATE SET
            last_synced_at = now(), last_status = 'ok', last_count = EXCLUDED.last_count
        """), {"n": expected["kg_pairs"]})
    pg.commit()
    ticker.tick(f"verification ok: {expected}", force=True)


def _finish(pg, store, ticker, counts: dict) -> None:
    store.commit()
    ticker.tick(f"done: writes={counts['writes']} resolution={counts['resolution_ok']}"
                f" misses={ {k: v for k, v in counts['resolution_misses'].items() if v} }",
                force=True)


if __name__ == "__main__":
    raise SystemExit(main())
