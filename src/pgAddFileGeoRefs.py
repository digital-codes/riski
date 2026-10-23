"""Georeference matching for Files (change: add-map-view, task 4.1/4.2).

Links streets and districts to Files whose `name` or `teaser` mentions
them (boundary-valid literal matching, same rules as the agenda-item geo
refs in `pgAddStreetRefs`/`pgAddDistrictRefs` via `local_geo_matching`).

Creates `Streets_items_Files` / `Districts_items_Files` association
tables. Also prunes stale agenda-item geo links: links whose stored
`name_match` no longer matches the agenda item's current name (OParl
upserts can rename items, leaving phantom references — e.g. a
Bebauungsplan title pointing a "Stadtwald" item at Stupferich).
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import argparse
import re
import sys
import time
from datetime import datetime

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, DateTime, delete, select, text

from src.db import get_engine
from src.local_geo_matching import literal_name_spans, name_matches, prepare_street_matcher

STREET_FILE_ASSOC = "Streets_items_Files"
DISTRICT_FILE_ASSOC = "Districts_items_Files"


def _match_evidence(text_: str, entity_name: str) -> str | None:
    """Excerpt around the first occurrence of *entity_name* — the evidence
    stored in name_match so the reason for a link stays visible."""
    spans = literal_name_spans(text_, entity_name)
    if not spans:
        return None
    start, end = spans[0]
    excerpt = text_[max(0, start - 60):end + 60].replace("\n", " ").strip()
    return f"…{excerpt}…"[:255]

_MATCHERS = {
    STREET_FILE_ASSOC: ("Street", "street_id"),
    DISTRICT_FILE_ASSOC: ("District", "district_id"),
}


def _ensure_assoc_table(engine, name: str, entity_col: str) -> Table:
    md = MetaData()
    tbl = Table(
        name, md,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column(entity_col, Integer, nullable=False),
        Column("file_id", Integer, nullable=False),  # File.sid
        Column("name_match", String(255), nullable=False),
        Column("created_at", DateTime, nullable=True),
        extend_existing=True,
    )
    md.create_all(engine, checkfirst=True)
    return tbl


def _load_entities(engine, table: str):
    with engine.connect() as conn:
        tbl = Table(table, MetaData(), autoload_with=conn)
        return conn.execute(select(tbl.c.id, tbl.c.name)).all()


def _iter_files(engine, limit: int | None, batch_size: int = 2000):
    """Yield (file_sid, name, teaser) batches."""
    md = MetaData()
    f = Table("File", md, autoload_with=engine)
    last_sid = 0
    with engine.connect() as conn:
        while True:
            stmt = (
                select(f.c.sid, f.c.name, f.c.teaser)
                .where(f.c.sid > last_sid)
                .order_by(f.c.sid)
                .limit(batch_size)
            )
            rows = conn.execute(stmt).fetchall()
            if not rows:
                return
            yield rows
            last_sid = rows[-1].sid
            if limit and last_sid >= limit:
                return


# Venue boilerplate ("Bürgersaal, Rathaus am Marktplatz" / "Bürgersaal des
# Rathauses auf dem Marktplatz" — incl. the Bürgerssaal typo) appears in
# every meeting protocol teaser and would link every protocol to the
# streets its venue sits on — stripped before matching. Requires the
# Rathaus context, so genuine content mentions of the Marktplatz survive.
_VENUE_NOISE = re.compile(
    r"(Bürgerssa?al\s*[,\s]+\s*)?Rath(aus|auses)(\s+(?:am|auf dem))?\s+Marktplatz\b",
    re.IGNORECASE,
)


def match_files(engine, limit: int | None = None, dry_run: bool = False,
                rebuild: bool = False) -> dict:
    """Match street/district names against File name + teaser, write the
    file geo association tables. Idempotent: existing (entity, file) pairs
    are skipped. With *rebuild*, the tables are wiped first — use after a
    matching-mechanism change so no stale mixture persists."""
    if rebuild and not dry_run:
        with engine.begin() as conn:
            for assoc_name in _MATCHERS:
                conn.execute(text(f'DELETE FROM "{assoc_name}"'))
            print("  file geo tables wiped (rebuild)")
    stats = {}
    matchers = {}
    for assoc_name, (entity_table, entity_col) in _MATCHERS.items():
        entities = _load_entities(engine, entity_table)
        # THE one geo-matching mechanism (same as pgAddStreetRefs):
        # precompiled boundary-aware combined matcher from local_geo_matching
        matcher = prepare_street_matcher(entities)
        matchers[assoc_name] = {
            "tbl": _ensure_assoc_table(engine, assoc_name, entity_col),
            "entity_col": entity_col,
            "matcher": matcher,
        }

    existing_cache: dict[str, set] = {name: set() for name in matchers}
    if not dry_run and not rebuild:
        for assoc_name, m in matchers.items():
            with engine.connect() as conn:
                rows = conn.execute(select(m["tbl"].c[m["entity_col"]], m["tbl"].c.file_id)).all()
            existing_cache[assoc_name] = {(r[0], r[1]) for r in rows}

    scanned = matched = 0
    pending: dict[str, list[dict]] = {name: [] for name in matchers}
    last_report = time.time()

    def flush(assoc_name: str) -> None:
        if dry_run or not pending[assoc_name]:
            return
        m = matchers[assoc_name]
        with engine.begin() as conn:
            conn.execute(m["tbl"].insert(), pending[assoc_name])
        pending[assoc_name].clear()

    for batch in _iter_files(engine, limit):
        for file_sid, name, teaser in batch:
            scanned += 1
            # venue boilerplate first: "Bürgersaal, Rathaus am Marktplatz"
            # appears in every protocol teaser and must not create links
            text_ = _VENUE_NOISE.sub("", f"{name or ''}\n{teaser or ''}")
            if len(text_) < 3:
                continue
            name_field = name or ""
            for assoc_name, m in matchers.items():
                # THE shared geo-matching mechanism (local_geo_matching),
                # identical to the agenda-item refs — no separate logic
                for match in m["matcher"].matches(text_):
                    pair = (match.item_id, file_sid)
                    if pair in existing_cache[assoc_name]:
                        continue
                    existing_cache[assoc_name].add(pair)
                    matched += 1
                    # evidence: where the reference was found, with context —
                    # so the reason for a link stays visible in the table
                    source = "name" if literal_name_spans(name_field, match.name) else "teaser"
                    evidence = _match_evidence(text_, match.name) or match.name
                    pending[assoc_name].append(
                        {m["entity_col"]: match.item_id, "file_id": file_sid,
                         "name_match": f"[{source}] {evidence}"[:255],
                         "created_at": datetime.now()}
                    )
                    if len(pending[assoc_name]) >= 500:
                        flush(assoc_name)
        for assoc_name in matchers:
            flush(assoc_name)
        if time.time() - last_report > 30:
            print(f"  scanned {scanned} files, {matched} new links so far...", flush=True)
            last_report = time.time()

    for assoc_name in matchers:
        stats[assoc_name] = len(existing_cache[assoc_name])
    stats["scanned"] = scanned
    stats["new_links"] = matched
    return stats


def prune_stale_agenda_refs(engine, dry_run: bool = False) -> dict:
    """Delete agenda-item geo links that are no longer valid: a link is
    valid only if the street/district name still matches the agenda
    item's CURRENT name. OParl upserts can rename items, leaving phantom
    references (e.g. a Bebauungsplan title pointing a "Stadtwald" item at
    district Stupferich)."""
    stats = {}
    for assoc_name, entity_col, entity_table in (
        ("Streets_items_AgendaItems", "street_id", "Street"),
        ("Districts_items_AgendaItems", "district_id", "District"),
    ):
        md = MetaData()
        assoc = Table(assoc_name, md, autoload_with=engine)
        entity = Table(entity_table, md, autoload_with=engine)
        agenda = Table("AgendaItem", md, autoload_with=engine)

        stale_ids = []
        with engine.connect() as conn:
            rows = conn.execute(
                select(assoc.c.id, entity.c.name, agenda.c.name)
                .select_from(
                    assoc.join(entity, assoc.c[entity_col] == entity.c.id)
                    .join(agenda, assoc.c.agendaitem_id == agenda.c.sid)
                )
            ).all()
        for link_id, entity_name, agenda_name in rows:
            if not name_matches(agenda_name or "", entity_name or ""):
                stale_ids.append(link_id)
        stats[assoc_name] = len(stale_ids)
        if stale_ids and not dry_run:
            with engine.begin() as conn:
                conn.execute(delete(assoc).where(assoc.c.id.in_(stale_ids)))
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="File georeference matching + stale geo-link pruning")
    ap.add_argument("--limit", type=int, default=None, help="Max files to scan (testing)")
    ap.add_argument("--dry-run", action="store_true", help="Report matches without writing")
    ap.add_argument("--prune", action="store_true", help="Also prune stale agenda-item geo links")
    ap.add_argument("--prune-only", action="store_true", help="Only prune, skip file matching")
    ap.add_argument("--rebuild", action="store_true", help="Wipe the file geo tables before matching (use after matching-mechanism changes)")
    args = ap.parse_args(argv)

    engine = get_engine()
    if not args.prune_only:
        stats = match_files(engine, limit=args.limit, dry_run=args.dry_run, rebuild=args.rebuild)
        for key, val in stats.items():
            print(f"  {key}: {val}")
    if args.prune or args.prune_only:
        prune_stats = prune_stale_agenda_refs(engine, dry_run=args.dry_run)
        for key, val in prune_stats.items():
            print(f"  pruned {key}: {val}" + (" (dry run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
