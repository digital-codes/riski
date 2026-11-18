"""Attach per-TOP ballot screenshots ('Abstimmung%') to pairs.

Evidence class (report addendum 2): 2,299 'Abstimmung...' files —
KPanel/QUINTA screenshot extracts with TOP number, session timestamp
and the vote tallies (JA/NEIN/ENTHALTUNG counts + party seat maps).
Name carries the TOP in ~97 % of cases; 1,298 are paper-linked
(`File__paper__Paper`), 1,739 unattached (name-TOP + text-date registry
path).

Attachment gate (spec: protocol verification — adapted, the screenshot
IS the result):

1. **TOP match** — file name or text names the pair's agenda-item TOP.
2. **Session match** — the text's session timestamp (e.g. "21 Oct 2025",
   ISO/name date, "DD.MM.YYYY") equals the pair's meeting date, OR the
   file is directly linked to the pair's paper AND the TOP matches.
3. **Vote-count plausibility cross-check** — numeric counts are OCR
   blobs and may suffer clipped digits ("8 vs 0"), so the parsed
   JA/NEIN majority is cross-checked against the pair's textual outcome
   (`zugestimmt`/`beschlossen` → JA should dominate; `abgelehnt` → NEIN
   should dominate). A contradiction (or undecidable tie) keeps the
   attachment but writes a warning into the verify note — the screenshot
   is the evidence, the parsed numbers are downstream hints only.

All writes are upserts on (pair, doc) — **no rerun of kgIdentify is
needed**: the stage only adds response documents to EXISTING pairs
(the statement-extraction queue must be restarted afterwards to pick
up the new response-bearing pairs).

Usage::

    python -m src.kg.kgAbstimmung --endpoint olc
    python -m src.kg.kgAbstimmung --limit 50
    python -m src.kg.kgAbstimmung --report results/kg_abstimmung_stats.json
"""

from __future__ import annotations

try:  # script-mode import bootstrap
    import _bootstrap  # noqa: F401
except ImportError:
    pass

import argparse
import json
import re
from datetime import date as date_type, datetime as dt
from typing import Any

from sqlalchemy import text

from src.db import get_engine, get_logger
from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker
from src.kg.kgVocab import load_vocab, resolve_mapping

log = get_logger("riski.kg.abstimmung")

DEFAULT_STORE = "results/kg_statements.sqlite"

TOP_NAME_RE = re.compile(r"(?i)top\s*-?_?\s*(\d+(?:\.\d+)?)")

# session timestamps in the screenshot text: "16:54 21 Oct 2025",
# "18:00 17 Dec 2024", or ISO/date-like strings
_TEXT_DATE_PATTERNS = [
    re.compile(r"(\d{1,2}:\d{2}\s+)?(\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})", re.I),
    re.compile(r"(\d{2}\.\d{2}\.\d{4})"),
    re.compile(r"(\d{4}-\d{2}-\d{2})"),
]
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
           "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

# screenshot layouts vary: markdown headings ("## JA\n45") and the
# pipe/space variants ("| ## JA | | 45 |" after chunking) — accept both by
# looking for the label followed (within a short window) by a number
_VOTE_RE = re.compile(r"(?is)\b(JA|NEIN|ENTHALTUNG)\b[^0-9]{0,40}(\d{1,3})\b")


def parse_text_date(txt: str) -> date_type | None:
    for pat in _TEXT_DATE_PATTERNS:
        m = pat.search(txt[:1200])
        if not m:
            continue
        raw = m.group(2) if m.groups() and len(m.groups()) >= 2 else m.group(0)
        parts = raw.split()
        if len(parts) >= 2:
            for p in parts:
                if p.isalpha() and p[:3].lower() in _MONTHS:
                    day = next((int(x) for x in parts if x.isdigit()), 0)
                    year = next((int(x) for x in parts if x.isdigit() and len(x) == 4), 0)
                    try:
                        return date_type(year, _MONTHS[p[:3].lower()], day)
                    except ValueError:
                        return None
        if re.match(r"\d{2}\.\d{2}\.\d{4}", raw):
            return dt.strptime(raw, "%d.%m.%Y").date()
        if re.match(r"\d{4}-\d{2}-\d{2}", raw):
            return date_type.fromisoformat(raw)
    return None


def parse_votes(txt: str) -> dict[str, int | None]:
    """JA/NEIN/ENTHALTUNG counts from the screenshot chunk text.

    OCR-participating values are returned as parsed; the caller decides
    trust (majority plausibility vs. textual outcome).
    """
    votes: dict[str, int | None] = {"JA": None, "NEIN": None, "ENTHALTUNG": None}
    for m in _VOTE_RE.finditer(txt):
        label = m.group(1).upper()
        try:
            votes[label] = int(m.group(2))
        except ValueError:
            continue
    return votes


def vote_majority(votes: dict[str, int | None]) -> str | None:
    ja, nein = votes.get("JA"), votes.get("NEIN")
    if ja is None or nein is None or ja == nein:
        return None
    return "mehrheit_ja" if ja > nein else "mehrheit_nein"


OUTCOME_EXPECTATION = {
    # pair outcome key → which side must dominate
    "zugestimmt": "mehrheit_ja",
    "beschlossen": "mehrheit_ja",
    "abgelehnt": "mehrheit_nein",
}


def crosscheck_counts(
    votes: dict[str, int | None], out_key: str | None
) -> tuple[str, str]:
    """Compare numeric majority with the textual outcome.

    Returns (verdict, note): verdict 'ok' | 'warn' | 'n/a'.
    """
    expected = OUTCOME_EXPECTATION.get(out_key or "")
    majority = vote_majority(votes)
    if not expected or majority is None:
        return "n/a", (
            "OCR-votes " + ", ".join(f"{k}={votes.get(k)}" for k in ("JA", "NEIN", "ENTHALTUNG"))
        )
    if majority == expected:
        return "ok", (
            f"OCR-votes consistent ({majority}): "
            + ", ".join(f"{k}={votes.get(k)}" for k in ("JA", "NEIN", "ENTHALTUNG"))
        )
    # contradiction: clipped digits most plausible cause — keep, warn
    return "warn", (
        f"OCR-votes CONTRADICT outcome '{out_key}' ({majority} vs {expected}); "
        "likely clipped digits — counts kept as hint only: "
        + ", ".join(f"{k}={votes.get(k)}" for k in ("JA", "NEIN", "ENTHALTUNG"))
    )


def file_text(conn: Any, file_sid: int, cap: int = 2000) -> str:
    rows = conn.execute(
        text(
            'SELECT text FROM "File_chunks" WHERE "file_sid" = :sid ORDER BY chunk_index'
        ),
        {"sid": file_sid},
    ).fetchall()
    return "".join((r[0] or "") for r in rows)[:cap]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--report", default="results/kg_abstimmung_stats.json")
    args = parser.parse_args()

    engine = get_engine(readonly=True)
    conn = engine.connect()
    store = KgStore(args.store)
    vocab = load_vocab()
    ticker = StatusTicker()
    ticker.section("abstimmung")

    stats = {
        "pairs_scanned": 0, "candidates_seen": 0, "top_match": 0,
        "session_match": 0, "attached": 0, "votes_ok": 0, "votes_warn": 0,
        "votes_na": 0, "not_attached": 0,
    }

    _pair_meta_sql = text(
        """
        SELECT po.sid AS paper_sid, m.sid AS meeting_sid, m.start_date AS start_date
        FROM "Paper" po JOIN "Meeting" m ON m."oparlId" = :meetingKey
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
        LIMIT 1
        """
    )
    # candidate class A: paper-linked Abstimmung files
    _paper_files_sql = text(
        """
        SELECT f.sid, f."oparlKey" AS doc_key, f.name, f.filename, f."oparlId",
               f.date AS f_date
        FROM "File__paper__Paper" xp JOIN "File" f ON f.sid = xp."tgtSid"
        WHERE xp."srcSid" = :paperSid AND f.name LIKE 'Abstimm%'
        """
    )
    # candidate class B: registry by (meeting date, TOP) — unattached or
    # meeting-attached screenshots
    _all_abst_sql = text(
        """
        SELECT f.sid, f."oparlKey" AS doc_key, f.name, f.filename, f."oparlId",
               f.date AS f_date
        FROM "File" f WHERE f.name LIKE 'Abstimm%'
        """
    )

    # name registry: TOP → files; File.date is deterministic session
    # metadata (verified: equals the meeting date on samples) and is the
    # primary session signal when the text screenshot lacks a date
    top_by_name: dict[str, list] = {}
    all_files = conn.execute(_all_abst_sql).fetchall()
    for f in all_files:
        m = TOP_NAME_RE.search(f.name or "")
        if not m:
            continue
        top_by_name.setdefault(m.group(1).lstrip("0"), []).append(f)

    pairs = store.pairs_by_status("identified")
    if args.limit:
        pairs = pairs[: args.limit]
    for pair in pairs:
        stats["pairs_scanned"] += 1
        ticker.tick(
            f"scanned={stats['pairs_scanned']} attached={stats['attached']} "
            f"warn={stats['votes_warn']}"
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
        if agenda is None or agenda.number is None:
            continue
        start = (
            meta.start_date.date() if hasattr(meta.start_date, "date") else meta.start_date
        )
        out_key = (
            resolve_mapping(pair["outcome"], vocab["results"])[0]
            if pair["outcome"] else None
        )

        session_iso = start.isoformat() if start else ""
        session_de = (
            start.strftime("%d.%m.%Y") if start else ""
        )
        session_textual = f"{start.day} {start.strftime('%b')} {start.year}" if start else ""

        candidates = conn.execute(_paper_files_sql, {"paperSid": meta.paper_sid}).fetchall()
        # registry path B: unattached or meeting-attached files with the TOP
        candidates += [
            f for f in top_by_name.get(agenda.number.lstrip("0"), [])
            if f.doc_key not in {c.doc_key for c in candidates}
        ]
        seen: set = set()
        for f in candidates:
            if f.doc_key in seen:
                continue
            seen.add(f.doc_key)
            stats["candidates_seen"] += 1
            head = file_text(conn, f.sid)
            top_match = TOP_NAME_RE.search(f.name or "") and (
                TOP_NAME_RE.search(f.name).group(1).lstrip("0")
                == agenda.number.strip()
                or agenda.number.strip() == top_by_name.get("")
            )
            if not top_match:
                tm = TOP_NAME_RE.search(head or "")
                top_match = bool(tm) and tm.group(1).lstrip("0") == agenda.number.lstrip("0")
            if top_match:
                stats["top_match"] += 1
            text_date = parse_text_date(head or "")
            f_date = (
                f.f_date.date() if getattr(f, "f_date", None) is not None and hasattr(f.f_date, "date")
                else f.f_date
            )
            session_match = bool(
                (text_date and start and text_date == start)
                or (f_date and start and f_date == start)
                or (session_iso and session_iso in (head or ""))
                or (session_de and session_de in (f.name or ""))
                or (session_textual and session_textual.lower() in (head or "").lower())
            )
            if session_match:
                stats["session_match"] += 1
            if top_match and session_match:
                votes = parse_votes(head or "")
                verdict, note = crosscheck_counts(votes, out_key)
                stats[f"votes_{verdict}"] = stats.get(f"votes_{verdict}", 0) + 1
                store.upsert_document(
                    pair["pair_key"],
                    {"doc_key": f.doc_key, "doc_id": f.oparlId, "name": f.name,
                     "filename": f.filename, "role": "response"},
                )
                store.upsert_file_meta(pair["pair_key"], f.doc_key, 0)
                store.set_verify_note(pair["pair_key"], f.doc_key, f"{verdict}: {note}")
                stats["attached"] += 1
            else:
                stats["not_attached"] += 1

    store.commit()
    ticker.tick(f"done: {stats}", force=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=2)
    conn.close()
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
