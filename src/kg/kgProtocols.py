"""Attach verified meeting protocols to pairs as response documents.

Stage 1b of the kg pipeline (design D9 amendment, 2026-11-17). The corpus
carries response documents in two structural places:

* per-TOP protocol files attached to agenda items ("Protokoll GR … TOP n"
  — 244 files on Gemeinderat agenda items)
* meeting-level results protocols (`Meeting__resultsProtocol__File` —
  142 GR files, mostly attendance-only "Anwesenheit (Protokoll)")

A protocol is attached to a pair with role ``response`` ONLY when BOTH
verification checks pass (verified baseline: 219/244 top-number matches,
54/81 outcome matches on the live corpus):

1. **TOP match** — the protocol text (head chunks) references the agenda
   item's TOP number (pattern ``Punkt <n> der Tagesordnung``).
2. **Result match** — the outcome wording in the protocol's
   ``Beschluss`` section is compatible with the pair's outcome.

Unverified protocols stay unattached (never attributed) and are counted
in the run summary — the statement layer only sees attributed evidence.

Usage::

    python -m src.kg.kgProtocols                  # full run (resumable)
    python -m src.kg.kgProtocols --sample 10      # attach at most N pairs
"""

from __future__ import annotations

try:  # script-mode import bootstrap
    import _bootstrap  # noqa: F401
except ImportError:
    pass

import argparse
import re
from typing import Any, Iterable

from sqlalchemy import text

from src.db import get_engine, get_logger
from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker
from src.kg.kgVocab import load_vocab, resolve_mapping

log = get_logger("riski.kg.protocols")

DEFAULT_STORE = "results/kg_statements.sqlite"

TOP_RE = re.compile(r"(?i)Punkt\s*([0-9IVX]+(?:\.[0-9]+)?)\s*der Tagesordnung")
FILE_TOP_RE = re.compile(r"(?i)protokoll\b.*?(\d{2}\.\d{2}\.\d{4}).*?\bTOP\s*-?\s*([0-9]+)")
BESCHLUSS_RE = re.compile(r"(?is)Beschluss:?\s*\n+([A-Za-zÄÖÜäöüß\.\-, \t]+)")
OUTCOME_WORD_ORDER = [
    # order matters for word-in-sentence disambiguation; longest first
    "kenntnisnahme",
    "verwiesen in fachausschuss",
    "zurückgestellt",
    "zugestimmt",
    "abgelehnt",
    "beschlossen",
    "vertagt",
    "verwiesen",
    "erledigt",
]
OUTCOME_TO_KEY = {
    "kenntnisnahme": "kenntnisnahme",
    "verwiesen in fachausschuss": "verwiesen",
    "verwiesen": "verwiesen",
    "zurückgestellt": "vertagt",
    "vertagt": "vertagt",
    "zugestimmt": "zugestimmt",
    "abgelehnt": "abgelehnt",
    "beschlossen": "beschlossen",
    "erledigt": "erledigt",
}


def outcome_word_scope(head: str) -> str:
    """Extract the Beschluss section following the TOP header."""
    hit = BESCHLUSS_RE.search(head)
    if hit:
        return hit.group(1)
    # no explicit Beschluss line: fall back to everything after the
    # TOP header line, capped (keeps noise low)
    m = TOP_RE.search(head)
    if m:
        return head[m.end(): m.end() + 2000]
    return head[:1200]


def detect_outcome(scope: str) -> str | None:
    """First compatible outcome word in the scope."""
    lowered = scope.lower()
    for word in OUTCOME_WORD_ORDER:
        if word == "verwiesen in fachausschuss":
            if re.search(r"verwi?esen (\(|in)? ?(den )?fachausschuss", lowered):
                return OUTCOME_TO_KEY[word]
            continue
        if re.search(rf"(?:^|[^a-zäöüß]){re.escape(word)}(?:en|t)?\b", lowered):
            return OUTCOME_TO_KEY[word]
    return None


def protocol_text(conn: Any, file_sid: int) -> str | None:
    """Head text (~first 4000 chars) of a file's chunks."""
    rows = conn.execute(
        text(
            'SELECT text FROM "File_chunks" WHERE "file_sid" = :sid ORDER BY chunk_index'
        ),
        {"sid": file_sid},
    ).fetchall()
    if not rows:
        return None
    return "".join((r[0] or "")[:4000] for r in rows)


def verify_protocol(
    head: str | None,
    number: str | None,
    outcome: str | None,
) -> tuple[bool, bool]:
    """Check TOP-number + Beschluss-outcome compatibility.

    Returns ``(top_match, result_match)``. A pair is offered the
    protocol when both are true.
    """
    head = head or ""
    top_hit = TOP_RE.search(head)
    top_match = bool(top_hit) and (not number or top_hit.group(1) == number)
    result_match = False
    ward = detect_outcome(outcome_word_scope(head))
    if ward and outcome:
        result_match = ward == outcome
    return top_match, result_match


# ----------------------------------------------------------------------
def pair_candidates(store: KgStore) -> Iterable[Any]:
    """Pairs still at status 'identified' (resume-safe)."""
    return store.pairs_by_status("identified")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--sample", type=int, default=0, help="at most N pairs")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    engine = get_engine(readonly=True)
    conn = engine.connect()
    store = KgStore(args.store)
    vocab = load_vocab()
    ticker = StatusTicker()
    ticker.section("protocols")

    stats = {
        "pairs_scanned": 0,
        "protocols_seen": 0,
        "top_match": 0,
        "outcome_match": 0,
        "attached": 0,
        "outcome_derived": 0,
        "not_attached": 0,
    }

    _pair_meta_sql = text(
        """
        SELECT po.sid AS paper_sid, m.sid AS meeting_sid, m.start_date AS start_date
        FROM "Paper" po
        JOIN "Meeting" m ON m."oparlId" = :meetingKey
        WHERE po."oparlId" = :paperKey
        """
    )

    _agenda_sql = text(
        """
        SELECT a.sid, a."number", a.result
        FROM "Paper__consultation__Consultation" pc
        JOIN "Consultation" c ON c.sid = pc."tgtSid"
        JOIN "AgendaItem" a ON a.sid = c."agendaItemSid"
        WHERE pc."srcSid" = :paperSid AND c."meetingSid" = :meetingSid
        ORDER BY c.sid
        """
    )

    # protocol files located by NAME pattern only (most corpus files carry
    # no structural link): "Protokoll GR <date> TOP <n>" — loaded once,
    # keyed by (date, TOP number)
    _all_prots_sql = text(
        """
        SELECT f.sid, f."oparlKey" AS doc_key, f.name, f.filename, f."oparlId"
        FROM "File" f
        WHERE f.name ~* 'protokoll.*top'
        """
    )

    # ---- one-time registry of protocol files by (date, TOP number) ----
    from datetime import datetime as dt

    prot_registry: dict[tuple, list] = {}
    for f in conn.execute(_all_prots_sql):
        m = FILE_TOP_RE.search(f.name or "")
        if not m:
            continue
        try:
            d = dt.strptime(m.group(1), "%d.%m.%Y").date()
        except ValueError:
            continue
        prot_registry.setdefault((d, m.group(2)), []).append(f)

    for pair in pair_candidates(store):
        if stats["pairs_scanned"] and args.limit and stats["pairs_scanned"] >= args.limit:
            break
        stats["pairs_scanned"] += 1
        if args.sample and stats["pairs_scanned"] > args.sample:
            break
        ticker.tick(
            f"scanned={stats['pairs_scanned']} attached={stats['attached']} "
            f"rejected={stats['not_attached']}"
        )
        meta = conn.execute(
            _pair_meta_sql,
            {"paperKey": pair["paper_key"], "meetingKey": pair["meeting_key"]},
        ).fetchone()
        if meta is None:
            continue

        agenda = conn.execute(
            _agenda_sql,
            {"paperSid": meta.paper_sid, "meetingSid": meta.meeting_sid},
        ).fetchone()
        outcome = pair["outcome"]
        if agenda is None:
            continue

        # regularize the outcome key (config vocabulary)
        out_key = resolve_mapping(outcome, vocab["results"])[0] if outcome else None
        # reverse direction (2026-11-18): pairs WITHOUT an outcome can get
        # one derived from the protocol's Beschluss wording — the
        # "Entscheidung" consultation mass was unused because of the
        # outcome gate. The derived outcome is stored with signal
        # 'protocol' after successful verification.
        outcome_pending_resolution = out_key is None

        start = meta.start_date.date() if hasattr(meta.start_date, "date") else meta.start_date
        # 1) structural path A: protocols attached to the agenda item itself
        candidates = conn.execute(
            text(
                """
                SELECT f.sid, f."oparlKey" AS doc_key, f.name, f.filename, f."oparlId"
                FROM "AgendaItem__auxiliaryFile__File" af
                JOIN "File" f ON f.sid = af."tgtSid"
                WHERE af."srcSid" = :agendaSid AND f.name ~* 'protokoll|niederschrift'
                """
            ),
            {"agendaSid": agenda.sid},
        ).fetchall()
        # 1b) structural path B (2026-11-18): per-TOP protocol files linked
        # directly to the PAPER (File__paper__Paper — 3346 papers carry
        # "Protokoll GR/… TOP n" extracts; this was the missing mass)
        candidates += conn.execute(
            text(
                """
                SELECT f.sid, f."oparlKey" AS doc_key, f.name, f.filename, f."oparlId"
                FROM "File__paper__Paper" xp
                JOIN "File" f ON f.sid = xp."tgtSid"
                WHERE xp."srcSid" = :paperSid AND f.name ~* 'protokoll|niederschrift'
                """
            ),
            {"paperSid": meta.paper_sid},
        ).fetchall()
        # 2) name-registry path: "Protokoll ... TOP n" of the same meeting
        candidates += prot_registry.get((start, agenda.number), [])

        seen: set = set()
        for f in candidates:  # type: ignore[name-defined]
            if f.doc_key in seen:
                continue
            seen.add(f.doc_key)
            stats["protocols_seen"] += 1
            head = protocol_text(conn, f.sid)
            top_match, result_match = verify_protocol(head, agenda.number, out_key)
            # session guard (committee protocols share TOP numbering):
            # the protocol must belong to the pair's session — either the
            # meeting date appears in the text or the name carries it
            date_strs = [
                start.strftime("%d.%m.%Y"), start.strftime("%d. %B %Y"),
                start.strftime("%d. %m. %Y"),
            ]
            date_ok = not (top_match and result_match) or any(
                (d in (head or "")) or (d in (f.name or "")) for d in date_strs
            ) or "GR" in (f.name or "")
            if top_match:
                stats["top_match"] += 1
            if result_match:
                stats["outcome_match"] += 1
            head_text = head or ""
            if outcome_pending_resolution and top_match and date_ok:
                # derive the outcome from the protocol's Beschluss wording
                scope = outcome_word_scope(head_text)
                derived = detect_outcome(scope)
                if derived:
                    store.upsert_pair(
                        pair_key=pair["pair_key"],
                        paper_key=pair["paper_key"],
                        meeting_key=pair["meeting_key"],
                        outcome=derived,
                        confidence=0.7,
                        signal="protocol",
                    )
                    out_key, outcome_pending_resolution = derived, False
                    stats["outcome_derived"] += 1
            if top_match and result_match and date_ok:
                store.upsert_document(
                    pair["pair_key"],
                    {"doc_key": f.doc_key, "doc_id": f.oparlId, "name": f.name,
                     "filename": f.filename, "role": "response"},
                )
                store.upsert_file_meta(pair["pair_key"], f.doc_key, 0)
                stats["attached"] += 1
            else:
                stats["not_attached"] += 1

    # status progression: pairs keep status 'identified' until statements
    store.commit()
    ticker.tick(f"done: {stats}", force=True)
    import json

    with open("results/kg_protocols_stats.json", "w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=2, sort_keys=False)
    conn.close()
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
