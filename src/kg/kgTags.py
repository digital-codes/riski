"""Assign ris-ki file tags to identified pair documents.

Stage 2 of the kg pipeline (capability: ``kg-statement-extraction`` /
tag classification). For every document of an identified pair the
document head text (all chunks concatenated, capped) is classified
against the ris-ki tag descriptions:

* tier 3 (vector): bge-m3 embedding of tag description vs. document
  head text; cosine similarity turned into a conservative confidence
* strict threshold: nothing below ``MIN_CONFIDENCE`` is written —
  no forced low-confidence tags
* optional qualifiers pick the phrase words hinted by the tag
  ('Sanierung' → qualifier "Sanierung", etc.)
* untagged documents are counted in the console summary (never forced)

Usage::

    python -m src.kg.kgTags --limit 50          # first N pair docs
    python -m src.kg.kgTags --endpoint ollama   # default
    python -m src.kg.kgTags --list-untagged
"""

from __future__ import annotations

try:  # script-mode import bootstrap
    import _bootstrap  # noqa: F401
except ImportError:
    pass

import argparse
import math
import re
from typing import Any

from sqlalchemy import text

from src.db import get_engine, get_logger
from src.kg.kgRemote import KgRemote
from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker
from src.kg.kgVocab import load_vocab

log = get_logger("riski.kg.tags")

DEFAULT_STORE = "results/kg_statements.sqlite"
MIN_CONFIDENCE = 0.55
HEAD_MAX_CHARS = 12000

# qualifier vocabulary per tag (vocabulary file: qualifier_hint)
QUALIFIER_MAP = {
    "Building Construction": True,  # parse qualifiers from hint
    "Road construction": True,
}


def text_head(conn: Any, doc_key: str) -> str | None:
    """Combined chunk text of a document (oparlKey), head-capped."""
    rows = conn.execute(
        text(
            """
            SELECT fc.text FROM "File_chunks" fc
            JOIN "File" f ON f.sid = fc."file_sid"
            WHERE f."oparlKey" = :docKey ORDER BY fc.chunk_index
            LIMIT 6
            """
        ),
        {"docKey": doc_key},
    ).fetchall()
    if not rows:
        # fall back to File.teaser
        teaser = conn.execute(
            text('SELECT COALESCE(teaser, \'\') FROM "File" WHERE "oparlKey" = :k'),
            {"k": doc_key},
        ).scalar()
        return teaser or None
    joined = "".join((r[0] or "") for r in rows)
    return joined[:HEAD_MAX_CHARS] or None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def qualifier_for(tag: str, spec: dict, text_value: str) -> str | None:
    """Detect a tag qualifier phrase in the document text."""
    hint = spec.get("qualifier_hint") or spec.get("qualifier_hint")
    if not hint:
        return None
    # ambiguous forms map onto canonical qualifiers
    canonical = re.split(r"\s*\|\s*", hint)
    lowered = text_value.lower()
    first = None
    for cand in canonical:
        appears = bool(
            re.search(rf"(?:^|[^a-zA-Zäöüß]){re.escape(cand.split()[0])}", lowered)
        ) or (cand.lower() in lowered)
        if appears:
            if first is None:
                first = cand
    return first


class TagAssigner:
    def __init__(
        self, conn: Any, store: KgStore, vocab: dict, remote: KgRemote,
        min_confidence: float = MIN_CONFIDENCE,
    ):
        self.conn = conn
        self.store = store
        self.vocab = vocab
        self.remote = remote
        self.min_confidence = min_confidence
        self.tagvecs: dict[str, list[float]] = {}
        for tag, spec in vocab["file_tags"].items():
            self.tagvecs[tag] = remote.embed(spec["description"])

    def assign(self, doc_key: str, head: str) -> dict[str, float]:
        """Return accepted {tag: confidence} for one document."""
        vec = self.remote.embed(head)
        sims = {t: _cosine(vec, tv) for t, tv in self.tagvecs.items()}
        accepted = {
            t: round(c, 3)
            for t, c in sims.items()
            if c >= self.min_confidence
        }
        return dict(sorted(accepted.items(), key=lambda kv: -kv[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--endpoint", default="ollama")
    parser.add_argument("--limit", type=int, default=0, help="at most N pair docs")
    parser.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE)
    parser.add_argument("--list-untagged", action="store_true")
    args = parser.parse_args()

    engine = get_engine(readonly=True)
    conn = engine.connect()
    store = KgStore(args.store)
    vocab = load_vocab()
    remote = KgRemote(args.endpoint)
    remote.available_models()  # accessibility check

    assigner = TagAssigner(
        conn, store, vocab, remote, min_confidence=args.min_confidence
    )

    docs = store.conn.execute(
        """
        SELECT DISTINCT dm.doc_key AS doc_key, dm.pair_key AS pair_key
        FROM file_meta dm
        JOIN pairs p ON p.pair_key = dm.pair_key
        WHERE p.status = 'identified'
        ORDER BY dm.doc_key
        """
    ).fetchall()

    stats = {"docs": 0, "tagged": 0, "untagged": 0, "assignments": 0}
    ticker = StatusTicker()
    ticker.section("tags")
    for row in docs:
        if args.limit and stats["docs"] >= args.limit:
            break
        head = text_head(conn, row["doc_key"])
        if not head:
            stats["untagged"] += 1
            continue
        accepted = assigner.assign(row["doc_key"], head)
        for tag, conf in accepted.items():
            spec = vocab["file_tags"].get(tag, {})
            qual = qualifier_for(tag, spec, head) if spec else None
            store.upsert_file_tag(row["doc_key"], tag, conf, qual, "vector")
            stats["assignments"] += 1
        if accepted:
            stats["tagged"] += 1
        else:
            stats["untagged"] += 1
        stats["docs"] += 1
        ticker.tick(f"docs={stats['docs']} tagged={stats['tagged']} untagged={stats['untagged']}")
        if args.commit_every and stats["docs"] % args.commit_every == 0:
            store.commit()

    store.commit()
    ticker.tick(f"done: {stats}", force=True)
    conn.close()
    store.close()
    if args.list_untagged:
        rows = store.conn.execute(
            "SELECT doc_key, COUNT(*) c FROM file_tags GROUP BY doc_key"
        ).fetchall()
        print("tagged docs:", len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
