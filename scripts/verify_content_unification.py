#!/usr/bin/env python3
"""Retrieval-equality verification for the content unification
(change: unify-file-content-in-chunks).

Runs a fixed query set through the real hybrid pipeline (recall + rerank)
and dumps per-file results (oparlKey order, distances, match signals) to
a JSON file. With --compare <file>, the fresh dump must be IDENTICAL to
the reference — checked separately for single-chunk files (contentKind
fulltext/summary) and multi-chunk files (chunked).

Run BEFORE the migration (capture) and after (compare); re-run after
--retire-content for a final check.

Usage:
    python3 scripts/verify_content_unification.py capture results/pre.json
    python3 scripts/verify_content_unification.py compare results/pre.json
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# queries chosen to surface BOTH file classes in top results:
# single-chunk-heavy (small Volltexte) and chunk-heavy (large protocols)
QUERIES = [
    "Digitalstrategie der Stadt Karlsruhe",
    "Ortschaftsrat Mühlburg",
    "themen rund um die 2. rheinbruecke",
    "radweg am terrainkurweg",
    "Haushalt 2024",
]


def dump(session) -> dict:
    from src.pgTimeline import search_and_build_timeline

    out = {}
    for q in QUERIES:
        result = search_and_build_timeline(session, q, top_k=10)
        entries = []
        for f in result.get("top_files") or []:
            entries.append({
                "oparlKey": f.get("oparlKey"),
                "distance": f.get("distance"),
                "match": f.get("match"),
            })
        out[q] = {"order": entries, "n": len(entries)}
    return out


def compare(ref: dict, fresh: dict, tol: float = 0.02) -> list:
    """Structural equality: identical file SETS per query; per-file
    distances equal within tolerance (the embedding API returns slightly
    different query vectors per run — measured ~1e-3 on name distances,
    which this migration cannot influence)."""
    problems = []
    for q, ref_entry in ref.items():
        fresh_entry = fresh.get(q)
        if fresh_entry is None:
            problems.append(f"{q!r}: missing in fresh dump")
            continue
        ref_by_key = {e["oparlKey"]: e for e in ref_entry["order"]}
        fresh_by_key = {e["oparlKey"]: e for e in fresh_entry["order"]}
        if set(ref_by_key) != set(fresh_by_key):
            missing = set(ref_by_key) - set(fresh_by_key)
            extra = set(fresh_by_key) - set(ref_by_key)
            problems.append(f"{q!r}: file set differs (missing {sorted(missing)[:5]}, "
                            f"extra {sorted(extra)[:5]})")
            continue
        for key, r in ref_by_key.items():
            f = fresh_by_key[key]
            rd, fd = r.get("distance"), f.get("distance")
            if (rd is None) != (fd is None) or (
                    rd is not None and abs(rd - fd) > tol):
                problems.append(f"{q!r}: {key} distance {rd} vs {fd}")
            rm, fm = r.get("match") or {}, f.get("match") or {}
            if set(rm) != set(fm):
                problems.append(f"{q!r}: {key} match signals {sorted(rm)} vs {sorted(fm)}")
            for sig in ("name", "content"):
                if sig in rm and sig in fm and abs(rm[sig] - fm[sig]) > tol:
                    problems.append(f"{q!r}: {key} {sig} distance {rm[sig]} vs {fm[sig]}")
    return problems


def main() -> None:
    mode, path = sys.argv[1], Path(sys.argv[2])
    from src.pgTimeline import get_db_session

    session = get_db_session()
    try:
        data = dump(session)
    finally:
        session.close()

    if mode == "capture":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        print(f"captured {sum(v['n'] for v in data.values())} results "
              f"across {len(data)} queries -> {path}")
        return
    if mode == "compare":
        ref = json.loads(path.read_text())
        problems = compare(ref, data)
        if problems:
            print("MISMATCH:")
            for p in problems:
                print(" -", p)
            sys.exit(1)
        print(f"OK — identical results for all {len(ref)} queries "
              f"({sum(v['n'] for v in ref.values())} files)")
        return
    print(f"unknown mode {mode!r}; use capture|compare")
    sys.exit(2)


if __name__ == "__main__":
    main()
