"""Identify the authoring party of request documents.

Stage 3 of the kg pipeline. Party names are NOT consistent across the
corpus (docs/kg_building.md: composition changes over time), so
extraction follows the era-valid variant vocabulary in
``config/kg_vocabulary.yaml`` (`party_variants`):

* scan the paper name + head document text for variant patterns
* normalize to the canonical label (CDU, SPD, GRÜNE, …)
* era validity: variants may be restricted to a date range via the
  ``era`` entry (list of [from, to] date strings, exclusive None)
* unknowns stay empty (spec: never guess a party)
* provenance records which pattern decided the label

Usage::

    python -m src.kg.kgAuthors --limit 100
    python -m src.kg.kgAuthors --list-parties
"""

from __future__ import annotations

try:  # script-mode import bootstrap
    import _bootstrap  # noqa: F401
except ImportError:
    pass

import argparse
import json
import re
from datetime import date
from typing import Any

from sqlalchemy import text

from src.db import get_engine, get_logger
from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker
from src.kg.kgVocab import load_vocab

log = get_logger("riski.kg.authors")

DEFAULT_STORE = "results/kg_statements.sqlite"

_HEADER_MAX_CHARS = 4000


def era_allows(era: Any, when: date | None) -> bool:
    """Era validation: ``era`` = null, or list of [from, to] strings."""
    if era is None:
        return True
    if when is None:
        return False
    for span in era:
        if not span:
            return True
        start = date.fromisoformat(span[0]) if span[0] else None
        end = date.fromisoformat(span[1]) if span[1] else None
        if (start is None or when >= start) and (end is None or when <= end):
            return True
    return False


def author_from_text(
    corpus: str,
    when: date | None,
    party_variants: dict,
) -> tuple[str | None, str]:
    """Resolve the party label from a text corpus.

    Returns ``(label, matched_pattern)`` or ``(None, "")`` if nothing
    matched — an empty author is a valid result (spec: never guess).
    """
    for label, spec in party_variants.items():
        if not era_allows(spec.get("era"), when):
            continue
        for pattern in spec.get("variants", []):
            if re.search(pattern, corpus):
                return label, pattern
    return None, ""


def request_text(conn: Any, paper_key: str) -> tuple[str, date | None]:
    """Paper name + head document text + the paper's date."""
    row = conn.execute(
        text(
            'SELECT name, date FROM "Paper" WHERE "oparlId" = :pk LIMIT 1'
        ),
        {"pk": paper_key},
    ).fetchone()
    parts = [row.name] if row and row.name else []
    when = None
    if row and row.date:
        d = str(row.date)[:10]
        try:
            when = date.fromisoformat(d)
        except ValueError:
            when = None
    heads = conn.execute(
        text(
            """
            SELECT fc.text FROM "File_chunks" fc
            JOIN "Paper__auxiliaryFile__File" pf ON pf."tgtSid" = fc."file_sid"
            JOIN "Paper" p ON p.sid = pf."srcSid"
            WHERE p."oparlId" = :pk ORDER BY fc.chunk_index LIMIT 3
            """
        ),
        {"pk": paper_key},
    ).fetchall()
    parts += [(h[0] or "")[:_HEADER_MAX_CHARS] for h in heads]
    return "".join(parts), when


def identify_author(
    conn: Any, pair: dict, vocab: dict
) -> tuple[str | None, str, str | None]:
    """Author extraction for one pair (spec: author identification)."""
    corpus, when = request_text(conn, pair["paper_key"])
    if not corpus:
        return None, "", None
    label, pattern = author_from_text(corpus, when, vocab["party_variants"])
    if label is None:
        return None, "", None
    return label, pattern, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--limit", type=int, default=0, help="at most N pairs")
    parser.add_argument("--commit-every", type=int, default=10, help="checkpoint commit interval")
    parser.add_argument("--list-parties", action="store_true")
    args = parser.parse_args()

    engine = get_engine(readonly=True)
    conn = engine.connect()
    store = KgStore(args.store)
    vocab = load_vocab()

    if args.list_parties:
        for party in vocab["party_variants"]:
            print(party)
        return 0

    pairs = store.pairs_by_status("identified")
    # author identification applies to REQUEST items only
    # (Beschlussvorlage Informationsvorlage are administration documents)
    request_classes = {
        k: e["class"]
        for k, e in vocab["papertypes"].items()
        if e.get("class") in ("request", "modification")
    }
    stats = {"pairs": 0, "authors_found": 0, "unknown": 0, "skipped_class": 0}
    ticker = StatusTicker()
    ticker.section("authors")
    for pair in pairs:
        if args.limit and stats["pairs"] >= args.limit:
            break
        if pair["request_type"] not in request_classes:
            stats["skipped_class"] += 1
            continue
        stats["pairs"] += 1
        ticker.tick(
            f"pairs={stats['pairs']} found={stats['authors_found']} "
            f"unknown={stats['unknown']}"
        )
        try:
            label, pattern, _note = identify_author(conn, dict(pair), vocab)
        except ValueError:
            label, pattern = None, ""
        # store canonical label into pair_documents (doc role request) and
        # the statement stage picks it up from the pair record
        if label:
            stats["authors_found"] += 1
            store.conn.execute(
                """
                INSERT INTO statements (pair_key, stage, doc_key, fields_json)
                VALUES (?, 'author', NULL, ?)
                ON CONFLICT (pair_key, stage, doc_key) DO UPDATE SET
                    fields_json = excluded.fields_json
                """,
                (
                    pair["pair_key"],
                    json.dumps(
                        {
                            "author": label,
                            "pattern": pattern,
                            "meeting_date": pair["meeting_date"],
                            "provenance": "party_variants",
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
        else:
            stats["unknown"] += 1
        if args.commit_every and stats["pairs"] % args.commit_every == 0:
            store.commit()

    store.commit()
    ticker.tick(f"done: {stats}", force=True)
    conn.close()
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
