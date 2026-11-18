"""Escalation layers (tier 2/3) for the kg pair identification.

Candidates that the structural traversal left with an unresolved
outcome (signal ``db-partial``) are escalated here:

* tier 2 ``regex`` — outcome wording patterns from
  ``config/kg_vocabulary.yaml`` applied over paper name, agenda item and
  file teasers (deterministic, no model calls).
* tier 3 ``vector`` — bge-m3 cosine similarity of the document head
  chunk against small hand-labeled anchor texts per outcome.

LLM escalation (tier 4) is NOT part of this stage — see kgTagSystemOne /
kgStatements which run controlled LLM calls later in the pipeline.

Usage::

    python -m src.kg.kgEscalate                     # both tiers, resumable
    python -m src.kg.kgEscalate --tier 2            # only the regex pass
    python -m src.kg.kgEscalate --endpoint ollama    # (default) tier 3
"""

from __future__ import annotations

try:  # script-mode import bootstrap
    import _bootstrap  # noqa: F401
except ImportError:
    pass

import argparse
import math
from typing import Any

from sqlalchemy import text

from src.db import get_engine, get_logger
from src.kg.kgRemote import KgRemote
from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker
from src.kg.kgVocab import load_vocab, resolve_mapping

log = get_logger("riski.kg.escalate")

DEFAULT_STORE = "results/kg_statements.sqlite"
VECTOR_THRESHOLD = 0.65  # cosine acceptance for the vector tier


_PAPER_NAME_SQL = text(
    """
    SELECT name FROM "Paper" WHERE "oparlId" = :paperKey
    """
)

_CONSULT_TEXTS_SQL = text(
    """
    SELECT a.name  AS agenda_name,
           a.result AS agenda_result,
           string_agg(f.name || ' ' || COALESCE(f.teaser, ''), ' ')
               AS file_texts
    FROM "Paper__consultation__Consultation" pc
    JOIN "Consultation" c ON c.sid = pc."tgtSid"
    LEFT JOIN "AgendaItem" a ON a.sid = c."agendaItemSid"
    LEFT JOIN "AgendaItem__auxiliaryFile__File" af ON af."srcSid" = a.sid
    LEFT JOIN "File" f ON f.sid = af."tgtSid"
    WHERE pc."srcSid" = :paperSid AND a.sid IS NOT NULL
    GROUP BY a.sid, a.name, a.result
    ORDER BY a.sid
    """
)

_HEAD_CHUNK_SQL = text(
    """
    SELECT fc.text
    FROM "File_chunks" fc
    JOIN "File" f ON f.sid = fc."file_sid"
    WHERE f."oparlKey" = :docKey
    ORDER BY fc.chunk_index
    LIMIT 1
    """
)

_PAPER_FILE_TEXTS_SQL = text(
    """
    SELECT string_agg(f.name || ' ' || COALESCE(f.teaser, ''), ' ')
    FROM "Paper__auxiliaryFile__File" pf
    JOIN "File" f ON f.sid = pf."tgtSid"
    WHERE pf."srcSid" = :paperSid
    """
)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


class Escalator:
    def __init__(
        self,
        conn: Any,
        store: KgStore,
        vocab: dict,
        remote: KgRemote | None = None,
    ):
        self.conn = conn
        self.store = store
        self.vocab = vocab
        self.remote = remote
        self._anchors: dict[str, list[float]] | None = None

    # ------------------------------------------------------------------
    def _texts_for(self, paper_key: str) -> str:
        """All names/teasers available for a paper — tier-2 input."""
        parts = []
        paper_sid = self.conn.execute(
            text('SELECT sid FROM "Paper" WHERE "oparlId" = :pk'), {"pk": paper_key}
        ).scalar()
        name = self.conn.execute(_PAPER_NAME_SQL, {"paperKey": paper_key}).fetchone()
        if name and name[0]:
            parts.append(name[0])
        if paper_sid is not None:
            ftext = self.conn.execute(_PAPER_FILE_TEXTS_SQL, {"paperSid": paper_sid}).fetchone()
            if ftext and ftext[0]:
                parts.append(ftext[0])
            for row in self.conn.execute(_CONSULT_TEXTS_SQL, {"paperSid": paper_sid}):
                if row.agenda_name:
                    parts.append(row.agenda_name)
                if row.agenda_result:
                    parts.append(row.agenda_result)
                if row.file_texts:
                    parts.append(row.file_texts)
        return " ".join(parts)

    def tier2_regex(self, pair) -> tuple[str, float]:
        """Resolve the outcome from wording patterns over names (tier 2)."""
        hay = self._texts_for(pair["paper_key"])
        for out_key, _entry in self.vocab["results"].items():
            patterns = self.vocab["results"][out_key].get("variants", [])
            for pattern in patterns:
                from src.kg.kgVocab import _compile

                if _compile(pattern).search(hay):
                    return out_key, 0.6
        return None, 0.0

    # ------------------------------------------------------------------
    def _embed(self, text_value: str) -> list[float]:
        return self.remote.embed(text_value)

    def tier3_vector(self, pair) -> tuple[str, float]:
        """Outcome via embedding similarity against anchors (tier 3)."""
        if self._anchors is None:
            self._anchors = {}
            for out_key, anchors in self.vocab["outcome_anchors"].items():
                vecs = [self._embed(a) for a in anchors]
                # mean position of the anchor cluster
                dim = len(vecs[0])
                self._anchors[out_key] = [
                    sum(v[i] for v in vecs) / len(vecs) for i in range(dim)
                ]
        best_key, best_sim = None, 0.0
        for doc in self.store.documents_for_pair(pair["pair_key"]):
            row = self.conn.execute(_HEAD_CHUNK_SQL, {"docKey": doc["doc_key"]}).fetchone()
            if not row or not row[0]:
                continue
            vec = self._embed(row[0])
            for out_key, anchor in self._anchors.items():
                sim = _cosine(vec, anchor)
                if sim > best_sim:
                    best_key, best_sim = out_key, sim
        if best_key and best_sim >= VECTOR_THRESHOLD:
            return best_key, 0.7
        return None, 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--tier", type=int, choices=[2, 3], help="stop after tier N")
    parser.add_argument("--endpoint", default="ollama")
    parser.add_argument("--limit", type=int, default=0, help="escalate at most N pairs")
    args = parser.parse_args()

    vocab = load_vocab()
    engine = get_engine(readonly=True)
    conn = engine.connect()
    store = KgStore(args.store)

    pending = store.pairs_by_status("identified")
    remote = None
    if args.tier != 2:
        remote = KgRemote(args.endpoint)  # accessibility check up front
        remote.available_models()  # fail fast if the endpoint is down

    stats = {"pairs": 0, "tier2": 0, "tier3": 0, "unresolved": 0}
    ticker = StatusTicker()
    ticker.section("escalate")

    esc = Escalator(conn, store, vocab, remote=remote)
    for pair in pending:
        if args.limit and stats["pairs"] >= args.limit:
            break
        outcome = pair["outcome"]
        signal = pair["signal"]
        confidence = pair["confidence"]
        if outcome is None:
            out_key, conf = esc.tier2_regex(dict(pair))
            if out_key:
                stats["tier2"] += 1
                outcome, signal, confidence = out_key, "regex", conf
            elif args.tier != 2:
                out_key, conf = esc.tier3_vector(dict(pair))
                if out_key:
                    stats["tier3"] += 1
                    outcome, signal, confidence = out_key, "vector", conf
        if outcome is None:
            stats["unresolved"] += 1
        store.upsert_pair(
            pair_key=pair["pair_key"],
            paper_key=pair["paper_key"],
            meeting_key=pair["meeting_key"],
            outcome=outcome,
            confidence=confidence,
            signal=signal,
        )
        stats["pairs"] += 1
        ticker.tick(f"pairs={stats['pairs']} tier2={stats['tier2']} tier3={stats['tier3']}")

    store.commit()
    ticker.tick(f"done: {stats}", force=True)
    conn.close()
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
