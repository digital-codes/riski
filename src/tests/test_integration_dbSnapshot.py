"""Integration test for the snapshot helpers (update-orchestration,
task 1.3): create + verify a real pg_dump. The mutate/restore round-trip
of the original task cannot run on this deployment — pg_hba.conf admits
the app role ONLY to the app database itself, so no scratch database is
connectable; restore safety is covered by unit tests + the restore
flow's TOC/verification asserts (restore_snapshot runs against the live
database and is operator-invoked only)."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_create_and_verify_dump(tmp_path):
    from src.db import DB_NAME
    from src.db.db_snapshot import create_snapshot

    dump = create_snapshot(DB_NAME, target_dir=tmp_path)
    assert Path(dump).exists() and Path(dump).stat().st_size > 10_000_000
    # run twice → collision-free name with time suffix
    dump2 = create_snapshot(DB_NAME, target_dir=tmp_path)
    assert dump2 != dump
