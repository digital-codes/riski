"""Integration tests for src.pgFileQuery against the live database.

Parity check: the refactored module must produce the same results as the
original ``src/pgFileQuery.py`` on the same data. Read-only queries only.
"""

import importlib.util
import os
import pathlib

import pytest
from sqlalchemy import MetaData, Table, select, text

from src import db
from src.pgFileQuery import (
    find_unreferenced_files,
    get_related_ids_for_agenda_item,
    get_related_ids_for_file,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine():
    return db.get_engine(readonly=True)


@pytest.fixture(scope="module")
def legacy_module():
    """Load the original src/pgFileQuery.py for output parity comparison."""
    path = pathlib.Path(__file__).resolve().parents[2] / "src" / "pgFileQuery.py"
    if not path.exists():
        pytest.skip("legacy src/pgFileQuery.py not present")
    # make src/private.py importable for the legacy module's openDb()
    src_dir = str(path.parent)
    import sys

    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    spec = importlib.util.spec_from_file_location("legacy_pgFileQuery", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFindUnreferencedFiles:
    def test_result_consistent_with_assoc_tables(self, engine):
        unreferenced = find_unreferenced_files()
        assert isinstance(unreferenced, list)
        sids = {row[0] for row in unreferenced}
        # cross-check: none of the returned files appears in an assoc table
        # on the side the query considers (File is 'src' in File__* tables,
        # 'tgt' in *__File tables)
        file_as_src = [
            "File__meeting__Meeting",
            "File__paper__Paper",
        ]
        file_as_tgt = [
            "AgendaItem__auxiliaryFile__File",
            "Meeting__auxiliaryFile__File",
            "Meeting__invitation__File",
            "Meeting__resultsProtocol__File",
            "Meeting__verbatimProtocol__File",
            "Paper__auxiliaryFile__File",
        ]
        metadata = MetaData()
        with engine.connect() as conn:
            for name in file_as_src:
                tbl = Table(name, metadata, autoload_with=engine)
                for sid in list(sids)[:50]:  # sample to keep the test fast
                    hit = conn.execute(
                        select(tbl.c.srcSid).where(tbl.c.srcSid == sid).limit(1)
                    ).first()
                    assert hit is None, f"file sid {sid} referenced in {name}.srcSid"
            for name in file_as_tgt:
                tbl = Table(name, metadata, autoload_with=engine)
                for sid in list(sids)[:50]:
                    hit = conn.execute(
                        select(tbl.c.tgtSid).where(tbl.c.tgtSid == sid).limit(1)
                    ).first()
                    assert hit is None, f"file sid {sid} referenced in {name}.tgtSid"

    def test_matches_legacy_output(self, engine, legacy_module):
        ours = sorted(find_unreferenced_files())
        theirs = sorted(legacy_module.find_unreferenced_files())
        assert ours == theirs


class TestRelatedIdsForFile:
    def test_matches_legacy_output(self, engine, legacy_module):
        # pick some files that actually have associations
        metadata = MetaData()
        af = Table("AgendaItem__auxiliaryFile__File", metadata, autoload_with=engine)
        file_tbl = Table("File", metadata, autoload_with=engine)
        with engine.connect() as conn:
            rows = conn.execute(
                select(file_tbl.c.oparlKey)
                .select_from(af.join(file_tbl, af.c.tgtSid == file_tbl.c.sid))
                .limit(5)
            ).fetchall()
        keys = [r[0] for r in rows]
        if not keys:
            pytest.skip("no file associations in database")
        for key in keys:
            ours = get_related_ids_for_file(key)
            theirs = legacy_module.get_related_ids_for_file(key)
            assert ours == theirs, f"mismatch for file oparlKey={key}"

    def test_unknown_key_returns_empty(self, engine):
        assert get_related_ids_for_file("definitely-not-a-real-key-xyz") == []


class TestRelatedIdsForAgendaItem:
    def test_matches_legacy_output(self, engine, legacy_module):
        metadata = MetaData()
        agenda_tbl = Table("AgendaItem", metadata, autoload_with=engine)
        af = Table("AgendaItem__auxiliaryFile__File", metadata, autoload_with=engine)
        with engine.connect() as conn:
            rows = conn.execute(
                select(agenda_tbl.c.oparlKey)
                .select_from(af.join(agenda_tbl, af.c.srcSid == agenda_tbl.c.sid))
                .limit(3)
            ).fetchall()
        keys = [r[0] for r in rows]
        if not keys:
            pytest.skip("no agenda item associations in database")
        for key in keys:
            ours = get_related_ids_for_agenda_item(key)
            theirs = legacy_module.get_related_ids_for_agenda_item(key)
            assert ours == theirs, f"mismatch for agenda oparlKey={key}"

    def test_unknown_key_returns_empty(self, engine):
        assert get_related_ids_for_agenda_item("definitely-not-a-real-key-xyz") == []
