"""Snapshot/restore helpers for the update pipeline (change:
unified-update-pipeline, capability: update-orchestration).

The snapshot is a *manual recovery point*, not an auto-rollback: the
pipeline heals by retrying (all phases are idempotent), and the restore
path exists for the operator. Both operations are defensive:

- ``create_snapshot`` dumps with ``pg_dump -Fc`` into the configured
  snapshot directory and verifies the dump by reading its table of
  contents (must contain data-table entries).
- ``restore_snapshot`` restores the dump in place (the instance's
  pg_hba.conf admits the app role ONLY to the app database itself, so a
  shadow-restore database is impossible): sessions are terminated,
  ``pg_restore --clean --if-exists`` replays the dump with a filtered
  TOC, and the result is verified. The reversible-restore guarantee
  comes from the dump file kept on disk (never dropped), not from a
  pre-rename shadow database.

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
    # localhost → 127.0.0.1: this host's pg_hba.conf fails ::1 ident-auth
    # while 127.0.0.1 (what psycopg2 effectively uses) is password-auth
    host = "127.0.0.1" if DB_HOST in ("localhost", "::1", None) else DB_HOST
    return ["-h", host, "-U", DB_USER]


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
    return os.getenv("RISKI_PG_ADMIN_DB", DB_NAME)


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
    """Restore *dump_path* into *db_name*, defensively.

    The instance's pg_hba.conf admits the app role ONLY to the app
    database itself (per-database rules) — creating/connecting a fresh
    ``<db>_restore_<ts>`` database is impossible from here, and the
    current database cannot be renamed by its own session (SQL-level
    restriction). The reversible-restore guarantee therefore comes from
    the DUMP FILE kept on disk (never dropped), not from a shadow
    database:

    1. verify the dump's TOC (extension statements filtered),
    2. terminate other sessions on *db_name*,
    3. ``pg_restore --clean --if-exists --no-owner --no-privileges``
       (filtered TOC) directly into *db_name*,
    4. verify the main tables are present afterwards.

    Stop-dependent applications first (README "Snapshots and restore");
    connections are terminated as a safeguard.
    """
    dump_path = Path(dump_path)
    if not dump_path.exists():
        raise SnapshotError(f"dump not found: {dump_path}")
    toc = _filtered_toc(dump_path, runner)

    # terminate other client sessions (best-effort: autovacuum workers
    # cannot be signaled without superuser — they are harmless here)
    try:
        _psql(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = current_database() "
            "AND backend_type = 'client backend' AND pid <> pg_backend_pid()",
            runner,
        )
    except SnapshotError as exc:  # noqa: PERF203 - continue with restore
        print(f"note: session termination skipped ({exc})")

    list_file = dump_path.with_suffix(".toc.clean.list")
    list_file.write_text(toc, encoding="utf-8")
    cmd = [
        "pg_restore", *_base_cmd(),
        "--clean", "--if-exists",
        "--no-owner", "--no-privileges",
        "-L", str(list_file),
        "-d", db_name, str(dump_path),
    ]
    rc, out, err = runner(cmd, _pg_env())
    if rc != 0:
        raise SnapshotError(
            f"pg_restore into {db_name} failed (rc={rc}): {err or out}"
        )

    # verify the database really contains the main tables afterwards
    table_list = ", ".join(f"'{t}'" for t in VERIFY_TABLES)
    verify_sql = (
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = 'public' AND c.relname IN ({table_list})"
    )
    out = _psql(verify_sql, runner)
    if out.strip() == "0":
        raise SnapshotError(
            f"restored {db_name} contains none of the expected tables "
            f"{VERIFY_TABLES} — check the dump"
        )
    return f"{dump_path}.toc.clean.list"
