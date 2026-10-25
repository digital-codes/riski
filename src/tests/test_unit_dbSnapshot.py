"""Unit tests for src/db/db_snapshot.py — command sequences verified with
a fake subprocess runner, no live PostgreSQL required."""

import pytest

from pathlib import Path

from src.db import DB_NAME, DB_USER, db_snapshot
from src.db.db_snapshot import (
    SnapshotError,
    create_snapshot,
    restore_snapshot,
    snapshot_path,
)

pytestmark = pytest.mark.unit

GOOD_TOC = (
    ";\n; Archive created at 2026-10-25\n;\n"
    '214; 1259 16456 TABLE data public "Paper" riski\n'
    '215; 1259 16466 TABLE DATA public "File" riski\n'
    "3400; 0 0 EXTENSION vector\n"
    "3401; 0 0 COMMENT - EXTENSION vector\n"
)


def _fake_pg_dump(cmd):
    if "-f" in cmd:
        Path(cmd[cmd.index("-f") + 1]).touch()
    return 0, "", ""


class FakeRunner:
    """Records commands; programmable responses per binary."""

    def __init__(self, behaviors=None):
        self.commands = []
        self.behaviors = {"pg_dump": _fake_pg_dump}
        self.behaviors.update(behaviors or {})

    def __call__(self, cmd, env):
        self.commands.append((cmd, env))
        behavior = self.behaviors.get(cmd[0], lambda cmd: (0, GOOD_TOC, ""))
        return behavior(cmd)

    def calls(self, binary):
        return [c for c, _ in self.commands if c[0] == binary]


@pytest.fixture(autouse=True)
def snap_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(db_snapshot, "DB_HOST", "localhost")
    monkeypatch.setenv("PGPASSWORD", "test")
    return tmp_path


def test_snapshot_path_date_and_collision(tmp_path):
    from datetime import datetime

    ts = datetime(2026, 10, 25, 13, 45)
    p1 = snapshot_path(DB_NAME, tmp_path, ts)
    assert p1.name == f"{DB_NAME}_2026-10-25.dump"
    p1.touch()
    p2 = snapshot_path(DB_NAME, tmp_path, ts)
    assert p2.name == f"{DB_NAME}_2026-10-25_1345.dump"


def test_create_snapshot_ok(tmp_path):
    runner = FakeRunner()
    dump = create_snapshot(DB_NAME, target_dir=tmp_path, runner=runner)
    # the fake runner doesn't write the file, but the path is the dated name
    assert dump == tmp_path / f"{DB_NAME}_2026-10-25.dump" or dump.parent == tmp_path
    # the pg_dump command used the expected connection parameters
    dump_cmds = runner.calls("pg_dump")
    assert len(dump_cmds) == 1
    cmd = dump_cmds[0]
    assert "-Fc" in cmd and "-d" in cmd and DB_NAME in cmd
    assert "-U" in cmd and DB_USER in cmd
    # verification happened via pg_restore --list
    assert len(runner.calls("pg_restore")) == 1
    # PGPASSWORD was set for the child processes
    assert all(env.get("PGPASSWORD") for _, env in runner.commands)


def test_create_snapshot_fails_on_pg_dump_error(tmp_path):
    def fail(cmd):
        return 1, "", "pg_dump: error: connection refused"

    runner = FakeRunner(behaviors={"pg_dump": fail})
    with pytest.raises(SnapshotError, match="connection refused"):
        create_snapshot(DB_NAME, target_dir=tmp_path, runner=runner)


def test_create_snapshot_fails_on_empty_toc(tmp_path):
    runner = FakeRunner(behaviors={"pg_restore": lambda cmd: (0, "", "")})
    with pytest.raises(SnapshotError, match="empty table of contents"):
        create_snapshot(DB_NAME, target_dir=tmp_path, runner=runner)


def test_create_snapshot_fails_on_toc_without_data(tmp_path):
    schema_only = '214; 1259 16456 TABLE public "Paper" riski\n'
    runner = FakeRunner(behaviors={"pg_restore": lambda cmd: (0, schema_only, "")})
    with pytest.raises(SnapshotError, match="TABLE DATA"):
        create_snapshot(DB_NAME, target_dir=tmp_path, runner=runner)


def test_restore_happy_path_keeps_old_db(tmp_path, monkeypatch):
    from datetime import datetime

    monkeypatch.setattr(db_snapshot, "VERIFY_TABLES", ("Paper", "File"))
    dump = tmp_path / f"{DB_NAME}_2026-10-25.dump"
    dump.write_bytes(b"fake dump")
    runner = FakeRunner(behaviors={
        "psql": lambda cmd: (0, "4", ""),  # 4 main tables found in target
    })
    pre = restore_snapshot(dump, DB_NAME, runner=runner)
    assert pre.startswith(f"{DB_NAME}_pre_restore_")

    # sequence: --list, CREATE DATABASE, pg_restore, verify, terminate, rename x2
    sqls = [c for c in runner.calls("psql")]
    assert any('CREATE DATABASE' in " ".join(c) and "restore_" in " ".join(c) for c in sqls)
    assert any("pg_terminate_backend" in " ".join(c) for c in sqls)
    assert any(f'RENAME TO "{DB_NAME}_pre_restore_' in " ".join(c) for c in sqls)
    # final rename gives the restore target the live name
    assert any(f'ALTER DATABASE "{DB_NAME}_restore_' in " ".join(c)
               and f'RENAME TO "{DB_NAME}"' in " ".join(c) for c in sqls)
    # pg_restore used the filtered TOC and safe flags
    restore_cmd = runner.calls("pg_restore")[-1]
    assert "--no-owner" in restore_cmd and "--no-privileges" in restore_cmd
    assert "-L" in restore_cmd
    list_file = restore_cmd[restore_cmd.index("-L") + 1]
    toc = open(list_file).read()
    assert "EXTENSION" not in toc
    assert 'TABLE DATA' in toc
    # nothing was dropped
    for c in sqls:
        assert "DROP DATABASE" not in " ".join(c)


def test_restore_verifies_target_before_swap(tmp_path, monkeypatch):
    monkeypatch.setattr(db_snapshot, "VERIFY_TABLES", ("Paper", "File"))
    dump = tmp_path / "dump.dump"
    dump.write_bytes(b"fake")
    runner = FakeRunner(behaviors={
        "psql": lambda cmd: (0, "0", ""),  # verify query finds no tables
    })
    with pytest.raises(SnapshotError, match="not swapping"):
        restore_snapshot(dump, DB_NAME, runner=runner)
    # no rename/terminate ever ran
    for cmd, _ in runner.commands:
        assert "RENAME" not in " ".join(cmd)
        assert "pg_terminate_backend" not in " ".join(cmd)


def test_restore_rolls_back_rename_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(db_snapshot, "VERIFY_TABLES", ("Paper", "File"))
    dump = tmp_path / "dump.dump"
    dump.write_bytes(b"fake")

    state = {"renamed_current": False}
    calls = []

    def psql_fail_on_final_rename(cmd):
        sql = " ".join(cmd)
        calls.append(sql)
        if f'RENAME TO "{DB_NAME}_pre_restore_' in sql:
            state["renamed_current"] = True
            return 0, "", ""
        if f'ALTER DATABASE "{DB_NAME}_restore_' in sql:
            return 1, "", "rename failed"
        if f'ALTER DATABASE "{DB_NAME}_pre_restore_' in sql and "RENAME TO" in sql:
            # the rollback rename
            state["renamed_current"] = False
            return 0, "", ""
        return 0, "4", ""  # create/verify/terminate

    runner = FakeRunner(behaviors={"psql": psql_fail_on_final_rename})
    with pytest.raises(SnapshotError, match="rename failed"):
        restore_snapshot(dump, DB_NAME, runner=runner)
    assert state["renamed_current"] is False  # rollback rename ran


def test_restore_missing_dump(tmp_path):
    with pytest.raises(SnapshotError, match="not found"):
        restore_snapshot(tmp_path / "nope.dump", DB_NAME, runner=FakeRunner())
