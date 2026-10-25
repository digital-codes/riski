"""Snapshot/restore helpers for the update pipeline (change:
unified-update-pipeline, capability: update-orchestration).

The snapshot is a *manual recovery point*, not an auto-rollback: the
pipeline heals by retrying (all phases are idempotent), and the restore
path exists for the operator. Both operations are defensive:

- ``create_snapshot`` dumps with ``pg_dump -Fc`` into the configured
  snapshot directory and verifies the dump by reading its table of
  contents (must contain data-table entries).
- ``restore_snapshot`` restores into a fresh ``<db>_restore_<ts>``
  database first, verifies it, then swaps via rename — the replaced
  database is kept as ``<db>_pre_restore_<ts>`` so a bad restore is
  itself reversible. Extension statements are filtered from the restore
  TOC (pgvector 0.8.x is not a trusted extension; the dump's duplicate
  ``CREATE EXTENSION`` lines make non-superuser restores fail — see
  README "Snapshots and restore").

All PostgreSQL interaction goes through an injectable *runner*
(``cmd -> (rc, stdout, stderr)``) so unit tests can verify the command
sequences without a live server.
"""

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from src.db import DB_HOST, DB_NAME, DB_PWD, DB_USER

Runner = Callable[[List[str], dict], Tuple[int, str, str]]

# tables expected in the TOC / restored database (main OParl tables)
VERIFY_TABLES = ("Paper", "File", "AgendaItem", "Meeting")

# extension statements a non-superuser restore chokes on (benign to skip:
# the extensions must pre-exist in the target database, see README)
_TOC_EXCLUDE_PATTERN = "EXTENSION"


class SnapshotError(RuntimeError):
    """A snapshot/restore step failed."""


def default_runner(cmd: List[str], env: dict) -> Tuple[int, str, str]:
    result = subprocess.run(
        cmd, env=env, capture_output=True, text=True, timeout=3600
    )
    return result.returncode, result.stdout, result.stderr


def _pg_env() -> dict:
    env = dict(os.environ)
    if DB_PWD:
        env["PGPASSWORD"] = DB_PWD
    return env


def _base_cmd() -> List[str]:
    return ["-h", DB_HOST, "-U", DB_USER]


def snapshot_path(db_name: str, target_dir: Path, timestamp: Optional[datetime] = None) -> Path:
    """Collision-free dump path: ``<db>_<date>[_<HHMM>].dump``."""
    ts = timestamp or datetime.now()
    candidate = target_dir / f"{db_name}_{ts:%Y-%m-%d}.dump"
    if candidate.exists():
        candidate = target_dir / f"{db_name}_{ts:%Y-%m-%d}_{ts:%H%M}.dump"
    return candidate


def _verify_toc(toc_output: str, what: str) -> None:
    """A usable dump lists its tables with a TABLE DATA section."""
    if not toc_output.strip():
        raise SnapshotError(f"{what}: empty table of contents")
    if "TABLE DATA" not in toc_output:
        raise SnapshotError(
            f"{what}: table of contents has no TABLE DATA entries — "
            "dump is unusable"
        )


def create_snapshot(
    db_name: str = DB_NAME,
    target_dir: str | Path = "/mnt_ai/data/riski/snapshots",
    runner: Runner = default_runner,
) -> Path:
    """Dump *db_name* (custom format) and verify the result. Returns the
    dump path; raises SnapshotError when the dump fails verification."""
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    dump_path = snapshot_path(db_name, target)

    cmd = ["pg_dump", *_base_cmd(), "-Fc", "-d", db_name, "-f", str(dump_path)]
    rc, out, err = runner(cmd, _pg_env())
    if rc != 0 or not dump_path.exists():
        raise SnapshotError(f"pg_dump failed (rc={rc}): {err or out}")

    verify_cmd = ["pg_restore", "--list", str(dump_path)]
    rc, out, err = runner(verify_cmd, _pg_env())
    if rc != 0:
        raise SnapshotError(f"pg_restore --list failed (rc={rc}): {err or out}")
    _verify_toc(out, str(dump_path))
    return dump_path


def _filtered_toc(dump_path: Path, runner: Runner) -> str:
    """TOC without the extension statements (README restore pattern)."""
    rc, out, err = runner(["pg_restore", "--list", str(dump_path)], _pg_env())
    if rc != 0:
        raise SnapshotError(f"pg_restore --list failed (rc={rc}): {err or out}")
    _verify_toc(out, str(dump_path))
    kept = [
        line for line in out.splitlines()
        if _TOC_EXCLUDE_PATTERN not in line and "COMMENT - " not in line
    ]
    return "\n".join(kept) + "\n"


def _admin_db() -> str:
    """Database the administrative SQL runs against (CREATE/DROP/RENAME of
    *other* databases). Override for deployments whose pg_hba.conf only
    admits the app role to the app database (README note); the admin db
    must not be the database being renamed/swapped."""
    return os.getenv("RISKI_PG_ADMIN_DB", "postgres")


def _psql(sql: str, runner: Runner, db: Optional[str] = None) -> str:
    """Run administrative SQL (default: the configured admin database)."""
    cmd = ["psql", *_base_cmd(), "-d", db or _admin_db(), "-Atc", sql]
    rc, out, err = runner(cmd, _pg_env())
    if rc != 0:
        raise SnapshotError(f"psql failed (rc={rc}): {err or out}")
    return out


def restore_snapshot(
    dump_path: str | Path,
    db_name: str = DB_NAME,
    runner: Runner = default_runner,
) -> str:
    """Restore *dump_path* over *db_name*, defensively.

    1. verify the dump's TOC,
    2. restore into a fresh ``<db>_restore_<ts>`` database (filtered TOC,
       ``--no-owner --no-privileges``),
    3. verify the restore target contains the main tables,
    4. terminate connections, rename current → ``<db>_pre_restore_<ts>``,
       rename target → ``<db>``.

    Returns the kept pre-restore database name. The live database is only
    replaced after a verified target exists; nothing is dropped.
    """
    dump_path = Path(dump_path)
    if not dump_path.exists():
        raise SnapshotError(f"dump not found: {dump_path}")
    toc = _filtered_toc(dump_path, runner)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    restore_db = f"{db_name}_restore_{ts}"
    pre_db = f"{db_name}_pre_restore_{ts}"

    _psql(f'CREATE DATABASE "{restore_db}" OWNER "{DB_USER}"', runner)

    list_file = dump_path.with_suffix(".toc.list")
    list_file.write_text(toc, encoding="utf-8")
    cmd = [
        "pg_restore", *_base_cmd(),
        "--no-owner", "--no-privileges",
        "-L", str(list_file),
        "-d", restore_db, str(dump_path),
    ]
    rc, out, err = runner(cmd, _pg_env())
    if rc != 0:
        raise SnapshotError(
            f"pg_restore into {restore_db} failed (rc={rc}): {err or out}"
        )

    # verify the target really contains the main tables before touching
    # the live database
    table_list = ", ".join(f"'{t}'" for t in VERIFY_TABLES)
    verify_sql = (
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = 'public' AND c.relname IN ({table_list})"
    )
    out = _psql(verify_sql, runner, db=restore_db)
    if out.strip() == "0":
        raise SnapshotError(
            f"restore target {restore_db} contains none of the expected "
            f"tables {VERIFY_TABLES} — not swapping"
        )

    # swap: exclusive access, then rename — old database is kept, not dropped
    _psql(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()",
        runner,
    )
    _psql(f'ALTER DATABASE "{db_name}" RENAME TO "{pre_db}"', runner)
    try:
        _psql(f'ALTER DATABASE "{restore_db}" RENAME TO "{db_name}"', runner)
    except SnapshotError:
        # undo the first rename so the live database stays live
        _psql(f'ALTER DATABASE "{pre_db}" RENAME TO "{db_name}"', runner)
        raise
    return pre_db
