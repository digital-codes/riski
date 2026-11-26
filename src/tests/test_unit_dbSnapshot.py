"""Unit tests for snapshot/restore helpers (update-orchestration).
Subprocess interaction is faked — no live PostgreSQL required."""

import os
from pathlib import Path

import pytest

from src.db import db_snapshot
from src.db.db_snapshot import (
    SnapshotError,
    _filtered_toc,
    create_snapshot,
    restore_snapshot,
    snapshot_path,
)

pytestmark = pytest.mark.unit

VALID_TOC = (
    ";\n; Archive created at 2026-11-26\n;\n"
    "215; 1259 16456 TABLE data public File riski\n"
    "216; 1259 16462 TABLE DATA public File riski\n"
    "217; 1259 16470 TABLE DATA public Paper riski\n"
    "220; 0 13816 COMMENT - EXTENSION \"vector\" riski\n"
    "221; 1259 16480 TABLE DATA public AgendaItem riski\n"
)
TOC_NO_DATA = "215; 1259 16456 TABLE public File riski\n"
DB = "riski_agentic"


def _dump_path(cmd):
    return Path(cmd[cmd.index("-f") + 1])


class FakeRunner:
    """Executes `pg_dump` (creates the file), answers `pg_restore --list`,
    and routes `psql` admin SQL; failing commands can be selected."""

    def __init__(self, toc=VALID_TOC, fail_psql=None, fail_restore=False,
                 verify_count="4"):
        self.calls = []
        self.toc = toc
        self.verify_count = verify_count
        self.fail_restore = fail_restore
        self.fail_psql = set(fail_psql or [])  # 1-based psql call indices
        self._psql_n = 0

    def __call__(self, cmd, env):
        self.calls.append((list(cmd), dict(env)))
        name = cmd[0]
        if name == "pg_dump":
            _dump_path(cmd).write_bytes(b"PGDMP")
            return 0, "", ""
        if name == "pg_restore":
            if "--list" in cmd:
                return 0, self.toc, ""
            if self.fail_restore:
                return 1, "", "restore boom"
            return 0, "", ""
        if name == "psql":
            self._psql_n += 1
            if self._psql_n in self.fail_psql:
                return 1, "", "psql boom"
            sql = cmd[cmd.index("-Atc") + 1]
            # "SELECT count(*) FROM pg_class" → table presence check
            if "pg_class" in sql and "pg_namespace" in sql:
                val = self.verify_count
            else:
                val = ""
            return 0, val, ""
        return 0, "", ""

    def psql_calls(self):
        return [(c[0][c[0].index("-Atc") + 1]) for c in self.calls
                if c[0][0] == "psql"]


@pytest.fixture()
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_NAME", DB)
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_USER", "riski")
    monkeypatch.setenv("DB_PWD", "secret")
    return tmp_path


# -- create_snapshot ------------------------------------------------------

def test_snapshot_path_plain_and_collision(tmp_path):
    from datetime import datetime
    ts = datetime(2026, 11, 26, 10, 30)
    p1 = snapshot_path(DB, tmp_path, ts)
    assert p1 == tmp_path / f"{DB}_2026-11-26.dump"
    p1.write_bytes(b"x")
    p2 = snapshot_path(DB, tmp_path, ts)
    assert p2 == tmp_path / f"{DB}_2026-11-26_1030.dump"


def test_create_snapshot_builds_and_verifies(tmp_env):
    runner = FakeRunner()
    out = create_snapshot(DB, tmp_env, runner=runner)
    assert out.exists()
    dump_cmd = next(c for c, _ in runner.calls if c[0] == "pg_dump")
    assert dump_cmd[0] == "pg_dump"
    assert "-Fc" in dump_cmd and "-d" in dump_cmd and DB in dump_cmd
    verify_cmd = [c for c, _ in runner.calls if c[0] == "pg_restore"][0]
    assert "--list" in verify_cmd


def test_create_snapshot_sets_pgpassword(tmp_env, monkeypatch):
    monkeypatch.setattr(db_snapshot, "DB_PWD", "secret")
    runner = FakeRunner()
    create_snapshot(DB, tmp_env, runner=runner)
    pg_calls = [e for c, e in runner.calls if c[0] in ("pg_dump", "pg_restore")]
    assert pg_calls and all(e.get("PGPASSWORD") == "secret" for e in pg_calls)


def test_create_snapshot_aborts_on_dump_failure(tmp_env):
    class Broken(FakeRunner):
        def __call__(self, cmd, env):
            if cmd[0] == "pg_dump":
                self.calls.append((list(cmd), dict(env)))
                return 1, "", "dump boom"
            return FakeRunner.__call__(self, cmd, env)
    with pytest.raises(SnapshotError):
        create_snapshot(DB, tmp_env, runner=Broken())


def test_create_snapshot_aborts_on_empty_or_dataless_toc(tmp_env):
    with pytest.raises(SnapshotError):
        create_snapshot(DB, tmp_env, runner=FakeRunner(toc=""))
    with pytest.raises(SnapshotError):
        create_snapshot(DB, tmp_env, runner=FakeRunner(toc=TOC_NO_DATA))


# -- TOC filtering ----------------------------------------------------------

def test_filtered_toc_drops_extension_and_comments(tmp_env):
    runner = FakeRunner()
    dump = tmp_env / "x.dump"
    dump.write_bytes(b"PGDMP")
    kept = _filtered_toc(dump, runner)
    assert "EXTENSION" not in kept
    assert "COMMENT - " not in kept
    assert "TABLE DATA public File" in kept


# -- restore_snapshot (in-place; rollback artifact = the dump file) ---------

def test_restore_terminates_sessions_then_restores_clean(tmp_env):
    runner = FakeRunner()
    dump = tmp_env / "dump-file"
    dump.write_bytes(b"PGDMP")
    out = restore_snapshot(dump, DB, runner=runner)
    sqls = runner.psql_calls()
    # sessions terminated, tables verified afterwards
    assert any("pg_terminate_backend" in s for s in sqls)
    assert any("pg_class" in s and "pg_namespace" in s for s in sqls)
    restore_cmd = next(c for c, _ in runner.calls
                       if c[0] == "pg_restore" and "--list" not in c)
    assert "--clean" in restore_cmd and "--if-exists" in restore_cmd
    assert "--no-owner" in restore_cmd and "--no-privileges" in restore_cmd
    assert "-L" in restore_cmd and DB in restore_cmd
    assert str(out).endswith(dump.name + ".toc.clean.list")


def test_restore_fails_loudly_when_tables_missing(tmp_env):
    runner = FakeRunner(verify_count="0")
    dump = tmp_env / "dump-file"
    dump.write_bytes(b"PGDMP")
    with pytest.raises(SnapshotError):
        restore_snapshot(dump, DB, runner=runner)


def test_restore_reports_failed_pg_restore(tmp_env):
    runner = FakeRunner(fail_restore=True)
    dump = tmp_env / "dump-file"
    dump.write_bytes(b"PGDMP")
    with pytest.raises(SnapshotError):
        restore_snapshot(dump, DB, runner=runner)


def test_restore_missing_dump(tmp_env):
    with pytest.raises(SnapshotError):
        restore_snapshot(tmp_env / "does-not-exist", DB,
                         runner=FakeRunner())


def test_snapshot_error_typed():
    assert issubclass(SnapshotError, RuntimeError)
    assert db_snapshot._admin_db() == os.getenv(
        "RISKI_PG_ADMIN_DB", db_snapshot.DB_NAME)
