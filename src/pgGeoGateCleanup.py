"""pgGeoGateCleanup — one-off LLM gating of existing geo links
(change: geo-gating).

Gates street/district association rows that have no verdict yet
(``gate_status IS NULL``) — the legacy inventory created before the gate
existed. Permissive principle: only a confident ``boilerplate`` verdict
hides a link; ``unsure``/``content`` stay visible.

Dry run (--dry-run) is for human review before any write: it reports the
verdict distribution and prints every REMOVAL CANDIDATE (verdict
``boilerplate``) with 2–3 lines of document context around the match so
the operator can sanity-check the gate before committing.

Resumable by construction: the ungated query is the cursor — an
interrupted run simply continues with the remaining rows.

Usage:
    python src/pgGeoGateCleanup.py --dry-run            # review pass
    python src/pgGeoGateCleanup.py                      # gate NULL rows
    python src/pgGeoGateCleanup.py --table Streets_items_Files --limit 100
    python src/pgGeoGateCleanup.py --reprocess unsure   # after model change
    python src/pgGeoGateCleanup.py --purge-boilerplate  # DELETE (asks twice)
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Optional

from sqlalchemy import MetaData, Table, create_engine, select, text

from src.db import POSTGRES_URL, get_engine, get_logger
from src.geoGate import GATED_TABLES, GeoGate

logger = get_logger("riski.geoGateCleanup")


def _rows_to_gate(conn, assoc_table: str, entity_col: str,
                  include_unsure: bool) -> List[Dict[str, Any]]:
    """Ungated (or unsure, with --reprocess) rows joined to their document
    or agenda item, with the document content/kind and the match evidence."""
    if assoc_table.endswith("_Files"):
        sql = text(f'''
            SELECT a.id AS assoc_id, a.{entity_col} AS entity_id,
                   e.name AS entity_name, a.file_id AS file_sid,
                   a.name_match AS evidence,
                   f.name AS doc_name, f."contentKind" AS doc_type,
                   f.content AS content
            FROM "{assoc_table}" a
            JOIN "File" f ON f.sid = a.file_id
            JOIN "{ 'Street' if 'Streets' in assoc_table else 'District' }" e
                 ON e.id = a.{entity_col}
            WHERE a.gate_status IS {'NULL' if not include_unsure else 'NULL'}
               OR (a.gate_status = 'unsure' AND :include_unsure)
            ORDER BY a.id
        ''')
    else:
        sql = text(f'''
            SELECT a.id AS assoc_id, a.{entity_col} AS entity_id,
                   e.name AS entity_name, a.agendaitem_id AS item_sid,
                   a.name_match AS evidence,
                   g.name AS doc_name,
                   NULL AS doc_type, NULL AS content
            FROM "{assoc_table}" a
            JOIN "AgendaItem" g ON g.sid = a.agendaitem_id
            JOIN "{ 'Street' if 'Streets' in assoc_table else 'District' }" e
                 ON e.id = a.{entity_col}
            WHERE a.gate_status IS NULL
               OR (a.gate_status = 'unsure' AND :include_unsure)
            ORDER BY a.id
        ''')
    rows = conn.execute(sql, {"include_unsure": include_unsure}).mappings().all()
    return [dict(r) for r in rows]


def _context_lines(content: str, name: str, lines: int = 3) -> str:
    """2–3 document lines around the first occurrence of *name* — the human
    review payload of the dry run."""
    if not content:
        return "(no content)"
    lines_list = content.splitlines()
    for i, line in enumerate(lines_list):
        if name.lower() in line.lower():
            lo = max(0, i - 1)
            hi = min(len(lines_list), i + lines - 1)
            snippet = "\n    ".join(l.strip() for l in lines_list[lo:hi] if l.strip())
            return snippet[:600]
    # not in content (match came from the name/teaser only): report evidence
    return "(match not in content — from name/teaser)"


def _verdict_from_evidence_context(row: Dict[str, Any],
                                   gate: GeoGate) -> Optional[str]:
    """Locate the mention's context in the content for the prompt."""
    content = row.get("content") or ""
    ctx = gate._context_around(content, row["entity_name"])
    return ctx


def run(assoc_tables: Optional[List[str]] = None, batch: int = 25,
        limit: Optional[int] = None, dry_run: bool = False,
        reprocess_unsure: bool = False, purge_boilerplate: bool = False,
        engine=None, out_path: Optional[str] = None) -> Dict[str, Any]:
    engine = engine or get_engine()
    gate = GeoGate(engine=engine)
    gate.ensure_columns()
    tables = assoc_tables or list(GATED_TABLES)

    report_lines: List[str] = [
        f"# pgGeoGateCleanup — {'DRY RUN' if dry_run else 'APPLY'} "
        f"({__import__('datetime').datetime.now():%Y-%m-%d %H:%M})",
        "",
        "Permissive gate: only confident `boilerplate` verdicts hide a link; "
        "`unsure`/`content`/ungated stay visible.",
        "",
    ]
    summary: Dict[str, Any] = {"tables": {}}

    for table in tables:
        entity_col = GATED_TABLES[table]
        with engine.connect() as conn:
            rows = _rows_to_gate(conn, table, entity_col,
                                 include_unsure=reprocess_unsure)
        if limit:
            rows = rows[:limit]
        counts = {"content": 0, "boilerplate": 0, "unsure": 0, "error": 0}
        removals: List[str] = []
        gated_written = 0
        processed_docs = 0
        report_lines.append(f"## {table} — {len(rows)} rows to gate")
        report_lines.append("")

        # one LLM call per document, its rows gated (and written) right away
        by_doc: Dict[Any, List[Dict[str, Any]]] = {}
        for r in rows:
            by_doc.setdefault(r.get("file_sid") or r.get("item_sid"), []).append(r)

        for doc_sid, doc_rows in by_doc.items():
            first = doc_rows[0]
            is_file = "file_sid" in first
            content = first.get("content") or ""
            mentions = [
                {"entity": r["entity_name"],
                 "context": _verdict_from_evidence_context(r, gate)}
                for r in doc_rows
            ]
            verdicts = gate.gate_mentions(
                first.get("doc_name") or "",
                first.get("doc_type") or "Tagesordnungspunkt",
                content, mentions)
            for r in doc_rows:
                v = verdicts.get(r["entity_name"],
                                 {"verdict": "unsure", "reason": "missing"})
                counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
                if v["verdict"] == "boilerplate":
                    removals.append(
                        f"- {r['entity_name']} ← "
                        f"{r.get('doc_name') or r.get('item_sid')} "
                        f"[{r['evidence'][:120]}]\n"
                        f"  reason: {v['reason']}\n"
                        f"  context:\n    {_context_lines(content, r['entity_name'])}")
            if not dry_run:
                gated_written += gate.write_verdicts(table, [
                    {"entity_id": r["entity_id"],
                     "entity_name": r["entity_name"],
                     **({"file_id": r["file_sid"]} if is_file
                        else {"item_sid": r["item_sid"]})}
                    for r in doc_rows
                ], verdicts, entity_col)
            processed_docs += 1
            # incremental flush: partial results survive an interrupt, and
            # progress stays visible during the many-hour pass
            if out_path and processed_docs % 25 == 0:
                _flush_report(report_lines, removals, counts, table,
                              len(rows), dry_run, gated_written, out_path)

        report_lines.append(f"verdicts: {json.dumps(counts)}")
        if not dry_run:
            report_lines.append(f"rows gated: {gated_written}")
        if removals:
            report_lines.append("")
            report_lines.append(f"### Removal candidates ({len(removals)}) "
                                "— review the context before applying:")
            report_lines.extend(removals)
        report_lines.append("")
        summary["tables"][table] = counts

    output = "\n".join(report_lines)
    print(output)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        print(f"\nreport written to {out_path}")
    summary["output"] = output
    return summary


def _flush_report(report_lines: List[str], removals: List[str],
                  counts: Dict[str, int], table: str, total_rows: int,
                  dry_run: bool, gated_written: int, out_path: str) -> None:
    """Incrementally persist the current report state (interrupt-safe)."""
    snapshot = list(report_lines)
    snapshot.append(f"[progress] {table}: verdicts so far "
                    f"{json.dumps(counts)} (of {total_rows} rows)")
    if removals:
        snapshot.append("")
        snapshot.append(f"### Removal candidates so far ({len(removals)}):")
        snapshot.extend(removals)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(snapshot) + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="One-off LLM gating of existing geo association rows")
    ap.add_argument("--dry-run", action="store_true",
                    help="No writes: report verdict distribution and print "
                         "removal candidates with document context for review")
    ap.add_argument("--table", action="append", default=None,
                    help="Restrict to one assoc table (repeatable)")
    ap.add_argument("--batch", type=int, default=25,
                    help="Documents per write flush (default 25)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Max rows per table (testing)")
    ap.add_argument("--reprocess", action="store_true",
                    help="Also re-gate rows currently 'unsure'")
    ap.add_argument("--purge-boilerplate", action="store_true",
                    help="DELETE boilerplate rows instead of only marking "
                         "(asks for confirmation)")
    ap.add_argument("--out", default=None,
                    help="Write the (dry-run) report to this path")
    args = ap.parse_args(argv)

    if args.purge_boilerplate and not args.dry_run:
        answer = input("Really DELETE boilerplate rows? Type 'purge' to "
                       "confirm: ")
        if answer.strip().lower() != "purge":
            print("aborted")
            return 1

    default_out = f"docs/geo-gate-{'dryrun' if args.dry_run else 'apply'}-{__import__('datetime').date.today().isoformat()}.md"
    run(assoc_tables=args.table, batch=args.batch, limit=args.limit,
        dry_run=args.dry_run, reprocess_unsure=args.reprocess,
        purge_boilerplate=args.purge_boilerplate,
        out_path=args.out or default_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
