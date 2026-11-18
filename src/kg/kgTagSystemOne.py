"""SystemOne tag assignment: all ris-ki tags in ONE call per document.

The decision model (d3:2b locally, clef:27b-cloud via ``--endpoint
ollama``/``olc``) answers one noul question per tag against the
document head text — a single POST carries all 23 tags and returns a
noul score 0..1 per tag that maps directly to the assignment
confidence (spec: confidence per tag; strictness threshold).

Qualifier sub-questions (Neubau/Sanierung/Erweiterung/Rückbau for the
construction tags) are appended to the same call and only assigned
when their parent tag fired.

Usage::

    python -m src.kg.kgTagSystemOne --limit 20 --endpoint olc
    python -m src.kg.kgTagSystemOne --endpoint ollama   # local d3 (slower)
    python -m src.kg.kgTagSystemOne --min-confidence 0.6
"""

from __future__ import annotations

try:  # script-mode import bootstrap
    import _bootstrap  # noqa: F401
except ImportError:
    pass

import argparse
import re
from typing import Any

from sqlalchemy import text

from src.db import get_engine, get_logger
from src.kg.kgRemote import KgRemote
from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker
from src.kg.kgVocab import load_vocab

log = get_logger("riski.kg.tags.sysone")

DEFAULT_STORE = "results/kg_statements.sqlite"
MIN_CONFIDENCE = 0.5
HEAD_MAX_CHARS = 6000

_CONSTRUCTION_TAGS = {"Building Construction", "Road construction"}
_QUALIFIER_QUESTIONS = {
    "qual_neubau": ("Wird im Dokument eine NEUBAU-Maßnahme (Neubau/Ersterrichtung) beschrieben?",
                    "Neubau"),
    "qual_sanierung": ("Wird eine SANIERUNG (Rekonstruktion/Erneuerung eines Bestands) beschrieben? "
                       "Achtung: 'Sanierung' heißt Rekonstruktion, nicht laufende Instandhaltung.",
                       "Sanierung"),
    "qual_erweiterung": ("Wird eine ERWEITERUNG eines Bestands beschrieben?", "Erweiterung"),
    "qual_rueckbau": ("Wird ein RÜCKBAU/Rückgang/Abriss beschrieben?", "Rückbau"),
    "qual_ausbau": ("Wird ein AUSBAU einer bestehenden Straße beschrieben?", "Ausbau"),
}


def text_head(conn: Any, doc_key: str) -> str | None:
    """Combined chunk text of a document (oparlKey), head-capped."""
    rows = conn.execute(
        text(
            """
            SELECT fc.text FROM "File_chunks" fc
            JOIN "File" f ON f.sid = fc."file_sid"
            WHERE f."oparlKey" = :docKey ORDER BY fc.chunk_index LIMIT 5
            """
        ),
        {"docKey": doc_key},
    ).fetchall()
    if not rows:
        teaser = conn.execute(
            text('SELECT COALESCE(teaser, \'\') FROM "File" WHERE "oparlKey" = :k'),
            {"k": doc_key},
        ).scalar()
        return (teaser or "")[:2000] or None
    joined = "".join((r[0] or "") for r in rows)
    return joined[:HEAD_MAX_CHARS] or None


class SysOneTagger:
    """One SystemOne round-trip per document against the tag table."""

    def __init__(self, remote: KgRemote, vocab: dict, min_confidence: float = MIN_CONFIDENCE):
        self.remote = remote
        self.vocab = vocab
        self.min_confidence = min_confidence
        self._questions_cache: dict[str, dict] | None = None

    def _tag_questions(self) -> dict[str, dict]:
        if self._questions_cache is None:
            questions = {}
            for tag, spec in self.vocab["file_tags"].items():
                questions[f"tag_{tag}"] = {
                    "type": "noul",
                    "instructions": (
                        f"Behandelt das Dokument das Thema {tag}? "
                        f"({str(spec.get('description', ''))[:160]})"
                    ),
                    "criteria": {"true": "Ja, zutreffend", "false": "Nein, nicht zutreffend"},
                }
            questions.update(
                {
                    q: {"type": "noul", "instructions": instr,
                        "criteria": {"true": "Ja", "false": "Nein"}}
                    for q, (instr, _) in _QUALIFIER_QUESTIONS.items()
                }
            )
            self._questions_cache = questions
        return self._questions_cache

    def assign(self, head: str) -> dict[str, dict]:
        """Return {tag: {confidence, qualifier}} for fireing tags."""
        answers = self.remote.systemone(head, self._tag_questions())
        out: dict[str, dict] = {}
        for key, answer in answers.items():
            if not isinstance(answer, dict):
                continue
            noul = answer.get("noul")
            if noul is None:
                continue
            try:
                noul = float(noul)
            except (TypeError, ValueError):
                continue
            if key.startswith("tag_"):
                tag = key[len("tag_"):]
                if noul >= self.min_confidence and tag in self.vocab["file_tags"]:
                    out[tag] = {"confidence": round(noul, 3), "qualifier": None}
            elif noul >= self.min_confidence and key in _QUALIFIER_QUESTIONS:
                out.setdefault("_qualifiers", {})[
                    _QUALIFIER_QUESTIONS[key][1]
                ] = round(noul, 3)
        qualifiers = out.pop("_qualifiers", {})
        for tag, hit in out.items():
            if tag in _CONSTRUCTION_TAGS:
                for qual, qnoul in qualifiers.items():
                    if qual in ("Neubau", "Sanierung", "Erweiterung", "Rückbau") or (
                        tag == "Road construction" and qual == "Ausbau"
                    ):
                        hit["qualifier"] = qual
                        hit["qual_conf"] = qnoul
                        break
        return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--endpoint", default="olc")
    parser.add_argument("--limit", type=int, default=0, help="at most N documents")
    parser.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE)
    args = parser.parse_args()

    engine = get_engine(readonly=True)
    conn = engine.connect()
    store = KgStore(args.store)
    vocab = load_vocab()
    remote = KgRemote(args.endpoint)

    docs = store.conn.execute(
        """
        SELECT DISTINCT dm.doc_key AS doc_key, d.filename, d.name
        FROM file_meta dm
        LEFT JOIN pair_documents d
          ON d.pair_key = dm.pair_key AND d.doc_key = dm.doc_key
        WHERE NOT EXISTS (SELECT 1 FROM file_tags ft WHERE ft.doc_key = dm.doc_key)
        ORDER BY dm.doc_key
        """
    ).fetchall()
    ticker = StatusTicker()
    ticker.section("tags.sysone")
    ticker.tick(f"docs to tag: {len(docs)}", force=True)

    # vocabulary sync → SQLite (yaml is the single source of truth):
    # tag descriptions AND qualifiers are upserted on every run, so new
    # yaml entries land in the store without manual steps
    for tag, spec in vocab["file_tags"].items():
        if spec.get("description"):
            store.upsert_tag(tag, spec["description"])
    for tag, quals in (vocab.get("qualifiers") or {}).items():
        for qual, descr in quals.items():
            store.upsert_qualifier(tag, qual, descr)
    store.commit()
    allowed = {tag: set(quals) for tag, quals in (vocab.get("qualifiers") or {}).items()}

    tagger = SysOneTagger(remote, vocab, min_confidence=args.min_confidence)
    stats = {
        "docs": 0, "tagged": 0, "untexted": 0, "assignments": 0,
        "errors": 0, "rejected_qualifiers": 0,
    }
    for row in docs:
        if args.limit and stats["docs"] >= args.limit:
            break
        head = text_head(conn, row["doc_key"])
        if not head:
            stats["untexted"] += 1
            continue
        try:
            hits = tagger.assign(head)
        except Exception as exc:  # noqa: BLE001
            stats["errors"] += 1
            log.warning("sysone tagging failed for %s: %s", row["doc_key"], exc)
            continue
        for tag, hit in hits.items():
            qual = hit.get("qualifier")
            grounded = None
            if qual and allowed:
                if store.upsert_doc_qualifier(
                    row["doc_key"], tag, qual, hit.get("qual_conf", hit["confidence"]),
                    "sysone", allowed=allowed,
                ):
                    grounded = qual  # only grounded values reach file_tags
                else:
                    stats["rejected_qualifiers"] += 1
            store.upsert_file_tag(
                row["doc_key"], tag, hit["confidence"], grounded, "sysone"
            )
            stats["assignments"] += 1
        if hits:
            stats["tagged"] += 1
        stats["docs"] += 1
        ticker.tick(
            f"docs={stats['docs']} tagged={stats['tagged']} assn={stats['assignments']}"
        )
        if stats["docs"] % 10 == 0:
            store.commit()  # checkpoint

    store.commit()
    ticker.tick(f"done: {stats}", force=True)
    conn.close()
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
