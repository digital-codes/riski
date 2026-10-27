"""Backfill Organization.classification via name-regex rules.

Change: intent-router (data-enrichment delta). Follows the pgCategorise
pattern: additive, idempotent, re-runnable. Writes ONLY organizations whose
classification is NULL and trims surrounding whitespace from names.
Existing classifications are never overwritten.

Run:
    python src/pgAddOrgClassification.py --dry-run
    python src/pgAddOrgClassification.py
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import argparse
import re
from typing import Optional

from sqlalchemy import text

from src.db import get_engine

# Name-regex rules -> classification value. First match wins; evaluated in
# listed order (most specific first). Values follow the style of the OParl
# provided classifications ("Beschließender Ausschuss", "Beirat und Stiftung").
# Karlsruhe rules — the live rules come from the instance config
# (rules.org_classification + rules.org_classification_fallback, change:
# instance-agnostic-config); these constants are the defaults.
CLASSIFICATION_RULES = [
    (r"^ortschaftsrat\b", "Ortschaftsrat"),
    (r"ausschuss", "Ausschuss"),
    (r"beirat", "Beirat und Stiftung"),
    (r"^gemeinderat\b", "Gemeinderat"),
    (r"^ortsverwaltung\b", "Ortsverwaltung"),
    (r"^dezernat\b", "Dezernat"),
    (r"\beamt\b|amt für|amt$", "Amt"),
    (r"^eigenbetrieb\b", "Eigenbetrieb"),
    (r"fraktion", "Fraktion"),
    (r"gmbh|ggmbh|gmbh \(| ag\b|verbund|stadtwerke|volkswohnung|betriebe", "Beteiligungsgesellschaft"),
    (r"^stabsstelle\b", "Stabsstelle"),
    (r"^personalrat\b", "Personalrat"),
]

FALLBACK_CLASSIFICATION = "Sonstiges"


def _configured_rules():
    """(pattern, label) rules + fallback from the instance config; the
    module constants above are the Karlsruhe defaults."""
    from src.instanceConfig import section

    rules_cfg = section("rules")
    entries = rules_cfg.get("org_classification")
    if not entries:
        return CLASSIFICATION_RULES, FALLBACK_CLASSIFICATION
    rules = [(e["pattern"], e["label"]) for e in entries
             if isinstance(e, dict) and e.get("pattern") and e.get("label")]
    fallback = rules_cfg.get("org_classification_fallback") or FALLBACK_CLASSIFICATION
    return (rules or CLASSIFICATION_RULES), fallback


def derive_classification(name: Optional[str]) -> Optional[str]:
    """Map an organization name to a classification value (first rule match,
    else fallback). Case-insensitive; None input yields None."""
    if not name or not name.strip():
        return None
    value = name.strip()
    rules, fallback = _configured_rules()
    for pattern, classification in rules:
        if re.search(pattern, value, re.IGNORECASE):
            return classification
    return fallback


def run(engine=None, dry_run: bool = False, count: Optional[int] = None) -> dict:
    """Trim whitespace in organization names and backfill NULL
    classifications. Returns a report dict."""
    engine = engine or get_engine()
    report = {"trimmed": 0, "classified": 0, "dry_run": dry_run, "changes": []}

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                'SELECT sid, name, classification FROM "Organization" '
                "ORDER BY sid"
                + (f" LIMIT {int(count)}" if count else "")
            )
        ).fetchall()

        for sid, name, classification in rows:
            trimmed = (name or "").strip()
            if trimmed and trimmed != name:
                report["trimmed"] += 1
                report["changes"].append((sid, name, trimmed, classification))
                if not dry_run:
                    conn.execute(
                        text('UPDATE "Organization" SET "name" = :n WHERE sid = :s'),
                        {"n": trimmed, "s": sid},
                    )
            if classification is None and trimmed:
                new_classification = derive_classification(trimmed)
                if new_classification:
                    report["classified"] += 1
                    report["changes"].append(
                        (sid, trimmed, f"classification={new_classification}", None)
                    )
                    if not dry_run:
                        conn.execute(
                            text(
                                'UPDATE "Organization" SET "classification" = :c '
                                "WHERE sid = :s"
                            ),
                            {"c": new_classification, "s": sid},
                        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument("--count", type=int, default=None, help="limit rows processed")
    args = parser.parse_args()

    report = run(dry_run=args.dry_run, count=args.count)
    mode = "DRY RUN" if args.dry_run else "APPLIED"
    print(f"[{mode}] trimmed names: {report['trimmed']}, "
          f"classifications backfilled: {report['classified']}")
    for sid, before, after, _old in report["changes"][:40]:
        print(f"  sid={sid}: {before!r} -> {after!r}")
    if len(report["changes"]) > 40:
        print(f"  ... and {len(report['changes']) - 40} more")


if __name__ == "__main__":
    main()
