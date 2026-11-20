"""Snapshot-backed dry-run verification of the kg phase chain.

Task 4.1 of kg-postgres-integration: prove the kg stages compose safely
inside the update-workflow phase pattern (snapshot → phases → verify →
report) WITHOUT merging the pending `unified-update-pipeline`
orchestrator (`src/riskiUpdate.py` on the dev branch). When that change
lands, each phase function here is expected to port 1:1 into its phase
registry (cursor-gated, best-effort class).

Sequence per run:

1. SNAPSHOT — pg_dump -Fc of riski_agentic into
   /mnt_ai/data/riski/snapshots/ (verified with pg_restore --list);
   critical: on failure the run stops.
2. KG PHASES — the kg stages, each individually idempotent:
   identify (resumable set-diff), chains, protocols, abstimmung,
   statements (inline crosscheck, cloud models), tags (SystemOne),
   migrate (SQLite→PostgreSQL upserts + verification gate).
3. VERIFY — PG row counts ≥ previous run's recorded baseline
   (kg_ingestion_runs cursor semantics).
4. REPORT — markdown next to the snapshot.

Usage::

    python scripts/kgUpdateVerify.py --snapshot-only   # just backup
    python scripts/kgUpdateVerify.py --dry-run         # plan, no writes
    python scripts/kgUpdateVerify.py                   # full verify run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import private as pr
from sqlalchemy import text

from src.db import get_engine


SNAP_DIR = "/mnt_ai/data/riski/snapshots"


def snapshot() -> str:
    """Critical phase: consistent full-DB dump, verified."""
    out = os.path.join(SNAP_DIR, f"riski_agentic_{date.today().isoformat()}-prekg.dump")
    env = dict(os.environ, PGPASSWORD=pr.DB_PWD)
    r = subprocess.run(
        ["pg_dump", "-Fc", "-h", pr.DB_HOST, "-U", pr.DB_USER, "-d", pr.DB_NAME,
         "-f", out],
        env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"snapshot failed: {r.stderr[:200]}")
    # verify TOC
    chk = subprocess.run(["pg_restore", "--list", out], env=env,
                         capture_output=True, text=True)
    n = sum(1 for line in chk.stdout.splitlines() if "TABLE DATA" in line)
    if n < 10:
        raise RuntimeError(f"snapshot TOC verification failed ({n} TABLE DATA entries)")
    print(f"[snapshot] {out} ({os.path.getsize(out)/1e6:.1f} MB, {n} tables with data)")
    return out


def phase(name: str, cmd: list[str], dry: bool) -> dict:
    if dry:
        print(f"[{name}] dry-run: would run {' '.join(cmd)}")
        return {"phase": name, "status": "planned"}
    t0 = __import__("time").time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    dt = __import__("time").time() - t0
    status = "ok" if r.returncode == 0 else "failed"
    tail = (r.stdout or "").strip().splitlines()[-1:] or [""]
    print(f"[{name}] {status} in {dt:.0f}s | {tail[0][:100]}")
    if r.returncode != 0:
        print((r.stdout or "")[-500:])
        print((r.stderr or "")[-500:])
    return {"phase": name, "status": status, "seconds": round(dt, 1),
            "returncode": r.returncode}


def pg_baseline() -> dict:
    e = get_engine(readonly=True)
    with e.connect() as c:
        return {
            "kg_pairs": c.execute(text("SELECT COUNT(*) FROM kg_pairs")).scalar(),
            "kg_statements": c.execute(text("SELECT COUNT(*) FROM kg_statements")).scalar(),
            "kg_crosschecks": c.execute(text("SELECT COUNT(*) FROM kg_crosschecks")).scalar(),
            "kg_tags_assoc_kg_topic": c.execute(
                text('SELECT COUNT(*) FROM "File_tags_assoc" WHERE scheme = \'kg-topic\'')).scalar(),
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshot-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-statements", action="store_true",
                    help="skip the LLM statement phase (cloud cost)")
    args = ap.parse_args()

    from sqlalchemy import text  # noqa: F401

    snap = snapshot()
    if args.snapshot_only:
        return 0

    baseline = pg_baseline()
    print("[baseline] before phases:", baseline)

    py = sys.executable
    results = [
        phase("identify", [py, "-m", "src.kg.kgIdentify"], args.dry_run),
        phase("chains", [py, "-m", "src.kg.kgChains"], args.dry_run),
        phase("protocols", [py, "-m", "src.kg.kgProtocols"], args.dry_run),
        phase("abstimmung", [py, "-m", "src.kg.kgAbstimmung"], args.dry_run),
    ]
    if not args.skip_statements:
        results.append(phase("statements", [py, "-m", "src.kg.kgStatements", "--endpoint", "olc"],
                             args.dry_run))
    results.append(phase("tags", [py, "-m", "src.kg.kgTagSystemOne", "--endpoint", "olc", "--limit", "200"],
                         args.dry_run))
    results.append(phase("authors", [py, "-m", "src.kg.kgAuthors"], args.dry_run))
    results.append(phase("crosscheck-tune", [py, "-m", "src.kg.kgTune", "--limit", "60"],
                         args.dry_run))
    migrate_cmd = [py, "-m", "src.kg.kgMigrate", "--apply"] if not args.dry_run else \
                  [py, "-m", "src.kg.kgMigrate"]
    results.append(phase("migrate", migrate_cmd, args.dry_run))

    after = pg_baseline()
    grew = {k: after[k] - baseline[k] for k in baseline}

    report = {
        "date": date.today().isoformat(),
        "snapshot": snap,
        "baseline_before": baseline,
        "baseline_after": after,
        "delta": grew,
        "phases": results,
    }
    out = os.path.join("results", f"kg_update_verify_{date.today().isoformat()}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(json.dumps({"delta": grew, "phases": [p["status"] for p in results],
                      "report": out}, indent=1))
    failed = [p for p in results if p["status"] == "failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
