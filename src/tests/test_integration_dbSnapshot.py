"""Integration test for snapshot/restore against a scratch database
(unified-update-pipeline task 1.3).

Creates a tiny throwaway database, snapshots it, mutates it, restores,
and verifies the original row is back. Uses the real pg_dump/pg_restore
binaries but on a database small enough to keep the test fast. Skips when
the database is unreachable or CREATEDB is not available."""

import uuid

import pytest
from sqlalchemy import create_engine, text

from src.db import DB_HOST, DB_NAME, DB_PWD, DB_USER, build_url, get_engine

pytestmark = pytest.mark.integration

SCRATCH_DB = f"riski_snapshot_test_{uuid.uuid4().hex[:8]}"


def _server_reachable() -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


def _admin_engine():
    """Admin operations (CREATE/DROP DATABASE) run through the app's own
    database connection: the hba on the deployment only admits the app role
    to the app database, and the role has CREATEDB. CREATE/DROP DATABASE
    are server-wide commands executable from any database."""
    return create_engine(build_url(DB_USER, DB_PWD, DB_HOST, DB_NAME))


def _drop_if_exists(admin, name):
    with admin.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))


@pytest.fixture()
def scratch_db(monkeypatch):
    if not _server_reachable():
        pytest.skip("live database unavailable")
    # db_snapshot's administrative psql sessions must target the app db too
    monkeypatch.setenv("RISKI_PG_ADMIN_DB", DB_NAME)
    admin = _admin_engine()
    _drop_if_exists(admin, SCRATCH_DB)
    with admin.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}" OWNER "{DB_USER}"'))
    yield SCRATCH_DB
    with admin.connect() as conn:
        names = conn.execute(text(
            "SELECT datname FROM pg_database WHERE datname LIKE :pat",
        ), {"pat": f"{SCRATCH_DB}%"}).scalars().all()
    for name in names:
        _drop_if_exists(admin, name)


def test_snapshot_mutate_restore_roundtrip(scratch_db):
    """create a table with a row -> snapshot -> mutate -> restore -> row is
    back (unified-update-pipeline task 1.3)."""
    from src.db.db_snapshot import create_snapshot, restore_snapshot

    url = build_url(DB_USER, DB_PWD, DB_HOST, scratch_db)
    engine = create_engine(url)
    # the deployment's pg_hba.conf admits the app role only to specific
    # databases (README "Setup") — a freshly created scratch database is
    # not covered, so nothing can connect to it. Skip when the environment
    # has this limitation; the roundtrip runs on hosts where it doesn't.
    try:
        with engine.connect():
            pass
    except Exception as exc:  # noqa: BLE001 - hba/ident restrictions
        pytest.skip(f"scratch database not connectable on this host: {exc}")

    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE "Paper" (sid serial primary key, name text)'))
        conn.execute(text('INSERT INTO "Paper" (name) VALUES (\'original\')'))

    dump = create_snapshot(scratch_db, target_dir="/tmp/riski_snapshot_test")
    assert dump.exists() and dump.stat().st_size > 0

    # mutate: drop the row
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM "Paper"'))
    with engine.connect() as conn:
        count = conn.execute(text('SELECT count(*) FROM "Paper"')).scalar()
    assert count == 0

    # restore the snapshot (swap via rename)
    pre_db = restore_snapshot(dump, scratch_db)

    # the live database has the row back
    engine2 = create_engine(url)
    with engine2.connect() as conn:
        count = conn.execute(text('SELECT count(*) FROM "Paper"')).scalar()
        names = conn.execute(text('SELECT name FROM "Paper"')).scalars().all()
    assert count == 1
    assert names == ["original"]
    # the mutated state is kept aside, not dropped
    with _admin_engine().connect() as conn:
        exists = conn.execute(text(
            f"SELECT 1 FROM pg_database WHERE datname = '{pre_db}'"
        )).scalar()
    assert exists == 1
