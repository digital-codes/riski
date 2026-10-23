"""Integration tests for src.pgGen – live database, additive/idempotent only.

``ensure_project_schema`` is designed to be non-destructive (CREATE IF NOT
EXISTS semantics, preservation snapshots).  These tests run it against the
live ``riski_agentic`` database and verify idempotency and preservation.
They skip automatically when the RW credentials lack the required
privileges (e.g. CREATE EXTENSION).
"""

import os

import pytest
from sqlalchemy import inspect, text

from src import db
from src.pgGen import (
    ensure_project_schema,
    migration_preservation_snapshot,
    verify_preservation,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine():
    if os.getenv("RW_USER") and os.getenv("RW_PWD"):
        url = db.build_url(
            os.environ["RW_USER"], os.environ["RW_PWD"], db.DB_HOST, db.DB_NAME
        )
        eng = db.get_engine(url=url)
    else:
        eng = db.get_engine()
    yield eng
    eng.dispose()


def _can_write(engine):
    """Probe whether the RW role can execute DDL (transient table)."""
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS test_ddl_probe (id int)"))
            conn.execute(text("DROP TABLE test_ddl_probe"))
        return True
    except Exception:
        return False


@pytest.fixture()
def write_guard(engine):
    if not _can_write(engine):
        pytest.skip("RW credentials lack DDL privileges on riski_agentic")


class TestEnsureProjectSchema:
    def test_project_tables_exist_after_run(self, engine, write_guard):
        ensure_project_schema(engine)
        names = set(inspect(engine).get_table_names())
        for required in (
            "Street",
            "District",
            "Streets_items_AgendaItems",
            "Districts_items_AgendaItems",
        ):
            assert required in names

    def test_re_run_preserves_data(self, engine, write_guard):
        before = migration_preservation_snapshot(engine)
        ensure_project_schema(engine)
        after = migration_preservation_snapshot(engine)
        # Preservation must hold on a schema-only re-run
        verify_preservation(before, after)
        # And table counts must not decrease anywhere
        for table, count in before["tables"].items():
            assert after["tables"].get(table, 0) >= count, table

    def test_file_columns_ensured(self, engine, write_guard):
        if "File" not in inspect(engine).get_table_names():
            pytest.skip("File table not present")
        ensure_project_schema(engine)
        cols = {c["name"] for c in inspect(engine).get_columns("File")}
        assert "content" in cols
        assert "teaser" in cols
