"""Local SQLite prototype store for the kg extraction pipeline.

Tables (see design.md D1/D8):

* ``pairs``           — one row per identified request/response pair; the
                        ``status`` column drives resumability
* ``pair_documents``  — full input-document list per pair (document id,
                        file name, role: request / modification / response /
                        attachment)
* ``pair_files_meta`` — per-file counters used by the statistics report
                        (chunk counts, etc.)
* ``tags``            — ris-ki tag vocabulary (tag + description)
* ``file_tags``       — document → tag assignments with confidence and
                        qualifier
* ``statements``      — extracted statements (stage: request/response)
* ``crosschecks``     — round-trip verdicts per pair

All writes are upserts keyed on stable keys so interrupted runs can be
simply re-run without duplicating rows.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pairs (
    pair_key     TEXT PRIMARY KEY,   -- <paper_oparl_id>|<meeting_oparl_id>
    paper_key    TEXT NOT NULL,
    meeting_key  TEXT NOT NULL,
    meeting_date TEXT,
    request_type TEXT,
    outcome      TEXT,
    confidence   REAL,
    signal       TEXT,               -- tier that decided: column|regex|vector|llm
    status       TEXT NOT NULL DEFAULT 'identified',
    UNIQUE (paper_key, meeting_key)
);

CREATE TABLE IF NOT EXISTS pair_documents (
    pair_key  TEXT NOT NULL,
    doc_key   TEXT NOT NULL,        -- oparl id
    doc_id    TEXT,
    filename  TEXT,
    name      TEXT,
    role      TEXT,                 -- request|modification|response|attachment
    PRIMARY KEY (pair_key, doc_key)
);

CREATE TABLE IF NOT EXISTS file_meta (
    pair_key   TEXT NOT NULL,
    doc_key    TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (pair_key, doc_key)
);

CREATE TABLE IF NOT EXISTS tags (
    tag         TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS file_tags (
    doc_key    TEXT NOT NULL,
    tag        TEXT NOT NULL,
    confidence REAL NOT NULL,
    qualifier  TEXT,
    provenance TEXT,
    PRIMARY KEY (doc_key, tag)
);

CREATE TABLE IF NOT EXISTS statements (
    pair_key      TEXT NOT NULL,
    stage         TEXT NOT NULL,    -- request|response
    doc_key       TEXT,
    fields_json   TEXT NOT NULL,
    PRIMARY KEY (pair_key, stage, doc_key)
);

CREATE TABLE IF NOT EXISTS crosschecks (
    pair_key TEXT PRIMARY KEY,
    verdict  TEXT NOT NULL,         -- passed|failed
    reason   TEXT
);

CREATE TABLE IF NOT EXISTS pair_links (
    prev_pair_key TEXT NOT NULL,
    next_pair_key TEXT NOT NULL,
    relation      TEXT NOT NULL,    -- 'next'
    PRIMARY KEY (prev_pair_key, next_pair_key)
);
"""


class KgStore:
    """Small typed convenience wrapper around sqlite3.

    The store is created on demand; every mutating method is an upsert so
    re-running a stage is always safe.
    """

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.execute("PRAGMA journal_mode = WAL")

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------
    # pairs
    # ------------------------------------------------------------------
    def upsert_pair(self, **kw: Any) -> None:
        """Insert or update a pair row keyed on ``pair_key``."""
        values = {
            "pair_key": kw["pair_key"],
            "paper_key": kw["paper_key"],
            "meeting_key": kw["meeting_key"],
            "meeting_date": kw.get("meeting_date"),
            "request_type": kw.get("request_type"),
            "outcome": kw.get("outcome"),
            "confidence": kw.get("confidence"),
            "signal": kw.get("signal"),
            "status": kw.get("status"),
        }
        self.conn.execute(
            """
            INSERT INTO pairs (pair_key, paper_key, meeting_key, meeting_date,
                               request_type, outcome, confidence, signal, status)
            VALUES (:pair_key, :paper_key, :meeting_key, :meeting_date,
                    :request_type, :outcome, :confidence, :signal,
                    COALESCE(:status, 'identified'))
            ON CONFLICT (pair_key) DO UPDATE SET
                meeting_date = COALESCE(excluded.meeting_date, pairs.meeting_date),
                request_type = COALESCE(excluded.request_type, pairs.request_type),
                outcome      = COALESCE(excluded.outcome, pairs.outcome),
                confidence   = COALESCE(excluded.confidence, pairs.confidence),
                signal       = COALESCE(excluded.signal, pairs.signal)
            """,
            values,
        )

    def set_pair_status(self, pair_key: str, status: str) -> None:
        self.conn.execute(
            "UPDATE pairs SET status = ? WHERE pair_key = ?",
            (status, pair_key),
        )

    def get_pair(self, pair_key: str) -> sqlite3.Row | None:
        row = self.conn.execute(
            "SELECT * FROM pairs WHERE pair_key = ?", (pair_key,)
        ).fetchone()
        return row

    def ensure_pre_stage(self) -> None:
        """Add ``pre_stage`` column to an existing store (idempotent)."""
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(pairs)")]
        if "pre_stage" not in cols:
            self.conn.execute(
                "ALTER TABLE pairs ADD COLUMN pre_stage INTEGER NOT NULL DEFAULT 0"
            )
            self.conn.commit()

    def set_pre_stage(self, pair_key: str) -> None:
        self.conn.execute(
            "UPDATE pairs SET pre_stage = 1 WHERE pair_key = ?", (pair_key,)
        )

    def upsert_link(self, prev_key: str, next_key: str, relation: str = "next") -> None:
        self.conn.execute(
            """
            INSERT INTO pair_links (prev_pair_key, next_pair_key, relation)
            VALUES (?, ?, ?)
            ON CONFLICT (prev_pair_key, next_pair_key) DO UPDATE SET
                relation = excluded.relation
            """,
            (prev_key, next_key, relation),
        )

    def paper_chains(self) -> list[sqlite3.Row]:
        """Papers (paper_key) with more than one pair, ordered by date."""
        return self.conn.execute(
            """
            SELECT paper_key, COUNT(*) AS n FROM pairs
            GROUP BY paper_key HAVING n > 1
            """
        ).fetchall()

    def paper_pairs(self, paper_key: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM pairs WHERE paper_key = ?
            ORDER BY meeting_date, pair_key
            """,
            (paper_key,),
        ).fetchall()

    def pairs_by_status(self, status: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM pairs WHERE status = ?", (status,)
        ).fetchall()

    def pair_counts_by_status(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM pairs GROUP BY status"
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}

    # ------------------------------------------------------------------
    # documents
    # ------------------------------------------------------------------
    def upsert_document(self, pair_key: str, doc: dict[str, Any]) -> None:
        """Insert or update the pair's document entry on ``(pair, doc)``."""
        values = {
            "pair_key": pair_key,
            "doc_key": doc.get("doc_key"),
            "doc_id": doc.get("doc_id"),
            "filename": doc.get("filename"),
            "name": doc.get("name"),
            "role": doc.get("role"),
        }
        self.conn.execute(
            """
            INSERT INTO pair_documents (pair_key, doc_key, doc_id, filename,
                                        name, role)
            VALUES (:pair_key, :doc_key, :doc_id, :filename, :name, :role)
            ON CONFLICT (pair_key, doc_key) DO UPDATE SET
                doc_id   = COALESCE(excluded.doc_id, pair_documents.doc_id),
                filename = COALESCE(excluded.filename, pair_documents.filename),
                name     = COALESCE(excluded.name, pair_documents.name),
                role     = COALESCE(excluded.role, pair_documents.role)
            """,
            values,
        )

    def documents_for_pair(self, pair_key: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM pair_documents WHERE pair_key = ? ORDER BY role, doc_key",
            (pair_key,),
        ).fetchall()

    def upsert_file_meta(self, pair_key: str, doc_key: str, chunk_count: int) -> None:
        self.conn.execute(
            """
            INSERT INTO file_meta (pair_key, doc_key, chunk_count)
            VALUES (?, ?, ?)
            ON CONFLICT (pair_key, doc_key) DO UPDATE SET
                chunk_count = excluded.chunk_count
            """,
            (pair_key, doc_key, chunk_count),
        )

    # ------------------------------------------------------------------
    # tags
    # ------------------------------------------------------------------
    def upsert_tag(self, tag: str, description: str) -> None:
        self.conn.execute(
            """
            INSERT INTO tags (tag, description) VALUES (?, ?)
            ON CONFLICT (tag) DO UPDATE SET description = excluded.description
            """,
            (tag, description),
        )

    def tags(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM tags ORDER BY tag").fetchall()

    def upsert_file_tag(
        self,
        doc_key: str,
        tag: str,
        confidence: float,
        qualifier: str | None,
        provenance: str | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO file_tags (doc_key, tag, confidence, qualifier, provenance)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (doc_key, tag) DO UPDATE SET
                confidence = excluded.confidence,
                qualifier  = excluded.qualifier,
                provenance = excluded.provenance
            """,
            (doc_key, tag, confidence, qualifier, provenance),
        )

    # ------------------------------------------------------------------
    # statements
    # ------------------------------------------------------------------
    def upsert_statement(
        self, pair_key: str, stage: str, doc_key: str | None, fields_json: str
    ) -> None:
        # SQLite treats NULLs as distinct in PKs — normalize None -> ''
        doc_key = doc_key or ""
        self.conn.execute(
            """
            INSERT INTO statements (pair_key, stage, doc_key, fields_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (pair_key, stage, doc_key) DO UPDATE SET
                fields_json = excluded.fields_json
            """,
            (pair_key, stage, doc_key, fields_json),
        )

    # ------------------------------------------------------------------
    # cross-checks
    # ------------------------------------------------------------------
    def upsert_crosscheck(self, pair_key: str, verdict: str, reason: str | None) -> None:
        self.conn.execute(
            """
            INSERT INTO crosschecks (pair_key, verdict, reason)
            VALUES (?, ?, ?)
            ON CONFLICT (pair_key) DO UPDATE SET
                verdict = excluded.verdict, reason = excluded.reason
            """,
            (pair_key, verdict, reason),
        )

    # ------------------------------------------------------------------
    # summary reporting
    # ------------------------------------------------------------------
    def chunk_distribution(self) -> dict[str, int]:
        """Histogram of chunk counts for the statistics report."""
        rows = self.conn.execute(
            """
            SELECT CASE WHEN chunk_count <= 5 THEN '<=5'
                        ELSE '>5' END AS bucket, COUNT(*) AS n
            FROM file_meta GROUP BY bucket
            """
        ).fetchall()
        return {r["bucket"]: r["n"] for r in rows}

    def commit(self) -> None:
        self.conn.commit()
