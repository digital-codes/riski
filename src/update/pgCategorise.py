"""Category derivation for RIS-KI (change: categorization-indexing).

Implements the canonical tag vocabulary with provenance:
- source precedence for document-type tags
- canonicalization of Paper.paperType values

The derivation/backfill entry points are added in later tasks (3.x); this
module currently holds the pure helpers they build on.
"""

# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.<name>``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import re
from typing import Iterable, Optional, Tuple

from sqlalchemy import MetaData, Table, select

from src import remote
from src.db import get_engine
from src.update.pgTagMgr import TagManager

# ----------------------------------------------------------------------
# Canonical sources and document-type precedence (design decision 1)
# ----------------------------------------------------------------------
# Lower rank wins. confidence is the default trust per source.
SOURCE_CONFIDENCE = {
    "papertype": 1.0,
    "manual": 1.0,
    "oparl-keyword": 0.9,
    "name-regex": 0.7,
    "llm": 0.5,
}

SOURCE_PRECEDENCE = [
    "papertype",
    "oparl-keyword",
    "name-regex",
    "llm",
    "manual",
]

# document-type is the only scheme with a defined precedence; other
# schemes (topic, district, submitter, org) keep their source as-is.
_PRECEDENCE_RANK = {name: i for i, name in enumerate(SOURCE_PRECEDENCE)}


def precedence(source: str) -> int:
    """Rank of *source* in the document-type precedence order."""
    if source not in _PRECEDENCE_RANK:
        raise ValueError(f"Unknown tag source {source!r}")
    return _PRECEDENCE_RANK[source]


def resolve_precedence(sources: Iterable[str]) -> Optional[str]:
    """Return the highest-precedence source from *sources* (None if empty)."""
    known = [s for s in sources if s in _PRECEDENCE_RANK]
    if not known:
        return None
    return min(known, key=precedence)


def default_confidence(source: str) -> float:
    """Default confidence for a derivation source."""
    if source not in SOURCE_CONFIDENCE:
        raise ValueError(f"Unknown tag source {source!r}")
    return SOURCE_CONFIDENCE[source]


# ----------------------------------------------------------------------
# paperType canonicalization (spike 1.4: 100% coverage, ~30 Haushalt
# THH <n> product-code variants fold into the Haushalt category)
# ----------------------------------------------------------------------
_HAUSHALT_RE = re.compile(r"^Haushalt\b", re.IGNORECASE)
_HAUSHALT_CODE_RE = re.compile(r"^Haushalt\s+(?:THH\s+)?([0-9]{3,4})$", re.IGNORECASE)


def canonicalize_document_type(paper_type: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Map a ``Paper.paperType`` value to a canonical document-type tag.

    Returns ``(tag, haushalt_code)``. ``Haushalt THH <n>`` variants fold
    into the single ``Haushalt`` category with the THH code preserved as an
    association attribute. Unmapped/empty input yields ``(None, None)``.
    """
    if not paper_type or not paper_type.strip():
        return None, None
    value = paper_type.strip()
    m = _HAUSHALT_CODE_RE.match(value)
    if m:
        return "Haushalt", m.group(1)
    if _HAUSHALT_RE.match(value):
        return "Haushalt", None
    return value, None


# ----------------------------------------------------------------------
# Derivation passes (tasks 3.1-3.3)
# ----------------------------------------------------------------------
DOCUMENT_TYPE_SCHEME = "document-type"

# Regex vocabularies reused from the pgAddTags analytics export.
from src.pgAddTags import AGENDA_GROUP_PATTERNS, FILE_GROUP_PATTERNS  # noqa: E402

_NAME_PATTERNS = {
    "AgendaItem": AGENDA_GROUP_PATTERNS,
    "File": FILE_GROUP_PATTERNS,
}


def _tag_manager(engine, item_table: str) -> TagManager:
    """TagManager on the writable engine; creates {item}_tags on demand."""
    # tags=[] (not None) triggers table creation without seeding entries.
    return TagManager(item_table, tags=[], engine=engine)


def derive_papertype_tags(engine, dry_run: bool = False, count: Optional[int] = None) -> dict:
    """Pass 1 (task 3.1): authoritative document-type tags from Paper.paperType.

    Canonicalizes via :func:`canonicalize_document_type` (``Haushalt THH n``
    folds into ``Haushalt``; the THH code is not persisted — it remains
    deterministically derivable from ``Paper.data``).
    """
    metadata = MetaData()
    paper = Table("Paper", metadata, autoload_with=engine)
    stmt = select(paper.c.sid, paper.c.oparlKey, paper.c.papertype).where(
        paper.c.papertype.isnot(None)
    )
    if count:
        stmt = stmt.limit(count)

    tm = _tag_manager(engine, "Paper")
    stats = {"scanned": 0, "tagged_items": 0, "skipped_empty": 0, "tags": {}}
    with engine.connect() as conn:
        for sid, oparl_key, papertype in conn.execute(stmt):
            stats["scanned"] += 1
            tag, _code = canonicalize_document_type(papertype)
            if tag is None:
                stats["skipped_empty"] += 1
                continue
            if not dry_run:
                tm.add_tags(
                    oparl_key, [tag], scheme=DOCUMENT_TYPE_SCHEME,
                    source="papertype", confidence=1.0,
                )
            stats["tags"][tag] = stats["tags"].get(tag, 0) + 1
            stats["tagged_items"] += 1
    return stats


def derive_name_regex_tags(
    engine,
    item_tables: Tuple[str, ...] = ("AgendaItem", "File"),
    dry_run: bool = False,
    count: Optional[int] = None,
) -> dict:
    """Pass 2 (task 3.2): document-type tags by regex over name columns.

    Reuses the pgAddTags pattern vocabularies (per item table). Names
    starting with ``-`` are skipped (pgAddTags convention for withdrawn
    items). Unmatched names are left to the LLM pass (task 3.3).
    """
    stats: dict = {"scanned": 0, "tagged_items": 0, "skipped_withdrawn": 0, "unmatched": 0, "tags": {}}
    for table in item_tables:
        patterns = _NAME_PATTERNS[table]
        metadata = MetaData()
        tbl = Table(table, metadata, autoload_with=engine)
        name_col = tbl.c.name
        stmt = select(tbl.c.sid, tbl.c.oparlKey, name_col).where(name_col.isnot(None))
        if count:
            stmt = stmt.limit(count)

        tm = _tag_manager(engine, table)
        with engine.connect() as conn:
            for sid, oparl_key, name in conn.execute(stmt):
                stats["scanned"] += 1
                if name.startswith("-"):
                    stats["skipped_withdrawn"] += 1
                    continue
                for tag, pattern in patterns.items():
                    if pattern.search(name):
                        if not dry_run:
                            tm.add_tags(
                                oparl_key, [tag], scheme=DOCUMENT_TYPE_SCHEME,
                                source="name-regex", confidence=0.7,
                            )
                        stats["tags"][tag] = stats["tags"].get(tag, 0) + 1
                        stats["tagged_items"] += 1
                        break
                else:
                    stats["unmatched"] += 1
    return stats


# LLM classification prompt (task 3.3): classify a teaser into the canonical
# document-type vocabulary, falling back to a topical tag when none fits.
LLM_SYSTEM_PROMPT = (
    "Du klassifizierst kurze Dokument-Zusammenfassungen (Teaser) aus einem "
    "Ratsinformationssystem. Antworte NUR mit einem JSON-Objekt der Form "
    '{"tag": "<Kategorie>"}. Wähle die Kategorie aus der vorgegebenen Liste, '
    "wenn eine passt; sonst wähle ein prägnantes deutsches Schlagwort (1-3 Wörter)."
)


def _candidate_vocabulary() -> list[str]:
    """Deterministic categories offered to the LLM (union of both vocabularies)."""
    return sorted(set(AGENDA_GROUP_PATTERNS) | set(FILE_GROUP_PATTERNS))


def _llm_classify(teaser: str, vocabulary: list[str]) -> Optional[str]:
    """Classify one teaser via the shared chat client; returns a tag or None."""
    import json as _json

    user = (
        f"Kategorien: {', '.join(vocabulary)}\n\n"
        f"Teaser: {teaser[:2000]}"
    )
    try:
        resp = remote.chat(
            [
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
        )
        content = resp.get("content", "")
        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end == -1:
            return None
        tag = _json.loads(content[start:end + 1]).get("tag")
        return tag.strip() if isinstance(tag, str) and tag.strip() else None
    except Exception as exc:  # noqa: BLE001 - backfill must survive API hiccups
        print(f"  LLM classification failed: {exc}")
        return None


def derive_llm_tags(
    engine,
    dry_run: bool = False,
    count: Optional[int] = None,
    force: bool = False,
) -> dict:
    """Pass 3 (task 3.3): batch LLM classification over ``File.teaser``.

    Only files whose name produced no regex match are escalated (teaser-first
    escalation keeps the prompt small). Re-runs skip already-LLM-tagged
    files unless *force* is set.
    """
    from sqlalchemy import exists as sa_exists

    from src.db import table_exists

    stats = {"scanned": 0, "tagged_items": 0, "already_tagged": 0, "failed": 0, "tags": {}}
    vocabulary = _candidate_vocabulary()

    file_tbl = Table("File", MetaData(), autoload_with=engine)
    stmt = (
        select(file_tbl.c.sid, file_tbl.c.oparlKey, file_tbl.c.name, file_tbl.c.teaser)
        .where(file_tbl.c.teaser.isnot(None))
    )
    if not force and table_exists("File_tags_assoc", engine=engine):
        assoc = Table("File_tags_assoc", MetaData(), autoload_with=engine)
        stmt = stmt.where(
            ~sa_exists(
                select(1)
                .select_from(assoc)
                .where(
                    assoc.c.oparl_key == file_tbl.c.oparlKey,
                    assoc.c.source == "llm",
                )
            ).correlate(file_tbl)
        )
    if count:
        stmt = stmt.limit(count)

    tm = _tag_manager(engine, "File")
    with engine.connect() as conn:
        rows = conn.execute(stmt).all()

    for sid, oparl_key, name, teaser in rows:
        stats["scanned"] += 1
        if name and name.startswith("-"):
            continue
        # Re-check the regex pass so LLM cost only applies to misses.
        matched = None
        if name:
            for tag, pattern in FILE_GROUP_PATTERNS.items():
                if pattern.search(name):
                    matched = tag
                    break
        if matched is not None:
            continue
        tag = _llm_classify(teaser, vocabulary)
        if tag is None:
            stats["failed"] += 1
            continue
        if not dry_run:
            tm.add_tags(
                oparl_key, [tag], scheme=DOCUMENT_TYPE_SCHEME,
                source="llm", confidence=0.5,
            )
        stats["tags"][tag] = stats["tags"].get(tag, 0) + 1
        stats["tagged_items"] += 1
    return stats


# ----------------------------------------------------------------------
# CLI (backfill entry point, task 3.5)
# ----------------------------------------------------------------------
def _print_stats(name: str, stats: dict) -> None:
    print(f"\n{name}")
    print(f"  scanned      : {stats.get('scanned', 0)}")
    print(f"  tagged items : {stats.get('tagged_items', 0)}")
    for key in ("skipped_empty", "skipped_withdrawn", "unmatched", "already_tagged", "failed"):
        if stats.get(key):
            print(f"  {key.replace('_', ' '):13s}: {stats[key]}")
    top = sorted(stats.get("tags", {}).items(), key=lambda kv: kv[1], reverse=True)[:15]
    if top:
        print("  tags         : " + ", ".join(f"{k} ({v})" for k, v in top))


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Category derivation and backfill")
    ap.add_argument("pass_name", choices=["papertype", "regex", "llm", "all"],
                    help="Which derivation pass to run")
    ap.add_argument("--dry-run", action="store_true", help="Do not write tags")
    ap.add_argument("--count", type=int, default=None, help="Limit rows per pass (testing)")
    ap.add_argument("--force", action="store_true", help="LLM pass: re-classify already-tagged files")
    args = ap.parse_args(argv)

    engine = get_engine()

    passes = {
        "papertype": derive_papertype_tags,
        "regex": derive_name_regex_tags,
        "llm": derive_llm_tags,
    }
    order = ["papertype", "regex", "llm"] if args.pass_name == "all" else [args.pass_name]
    for name in order:
        stats = passes[name](engine, dry_run=args.dry_run, count=args.count) if name != "llm" else \
            passes[name](engine, dry_run=args.dry_run, count=args.count, force=args.force)
        _print_stats(name, stats)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
