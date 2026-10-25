"""Integration test: the /geo map filter honours gate verdicts (change:
geo-gating, task 4.3).

Runs against the live database. ``collect_geo`` opens its own connections,
so uncommitted writes would be invisible to it — the test therefore
commits its gate-status changes and restores the original verdicts in a
``finally`` block (rollback-free, assoc tables only). The verdicts from
the cleanup run (docs/geo-gate-apply-2026-10-25.md) stay intact.

Most files carry no geo reference at all, so feature-level assertions are
only made when the street actually has geometry; link-level assertions
(which links survive the gate filter) run in every case.
"""

import pytest
from sqlalchemy import text

from src.db import get_engine
from src.pgGeo import collect_geo

pytestmark = pytest.mark.integration


def _pick_candidate(conn):
    """A street that has at least one file link, plus one linked file's
    oparlKey (collect_geo works on oparlKeys)."""
    row = conn.execute(text('''
        SELECT lif.street_id, s.name, f."oparlKey" AS file_key,
               (s.geo IS NOT NULL) AS has_geo
        FROM "Streets_items_Files" lif
        JOIN "Street" s ON s.id = lif.street_id
        JOIN "File" f ON f.sid = lif.file_id
        LIMIT 1''')).fetchone()
    assert row is not None, "no street file link in db"
    return row.street_id, row.file_key, row.has_geo


def _original_links(conn, street_id):
    rows = conn.execute(text(
        'SELECT file_id, gate_status FROM "Streets_items_Files" '
        'WHERE street_id = :s'), {"s": street_id}).fetchall()
    return [(r.file_id, r.gate_status) for r in rows]


def _set_verdict(engine, street_id, verdict):
    with engine.begin() as tx:
        tx.execute(text(
            'UPDATE "Streets_items_Files" SET gate_status = :v '
            'WHERE street_id = :s'), {"v": verdict, "s": street_id})


def _visible_street_ids(engine, file_key):
    """street ids whose file links survive the gate filter."""
    with engine.connect() as conn:
        rows = conn.execute(text('''
            SELECT DISTINCT lif.street_id FROM "Streets_items_Files" lif
            WHERE lif.file_id = (SELECT sid FROM "File" WHERE "oparlKey" = :k LIMIT 1)
              AND lif.gate_status IS DISTINCT FROM 'boilerplate' '''),
            {"k": file_key}).fetchall()
    return {r[0] for r in rows}


class TestMapFilterHonoursGate:
    def test_boilerplate_hidden_null_unsure_content_pass(self):
        engine = get_engine()
        probe = engine.connect()
        try:
            street_id, file_key, has_geo = _pick_candidate(probe)
            originals = _original_links(probe, street_id)
        finally:
            probe.close()
        try:
            assert street_id in _visible_street_ids(engine, file_key), (
                "pre-existing state: the link must pass before the test touches it")

            # every link → boilerplate: the link set for the file must no
            # longer contain the street
            _set_verdict(engine, street_id, "boilerplate")
            assert street_id not in _visible_street_ids(engine, file_key)

            # one NULL link: the permissive filter lets the street through
            with engine.begin() as tx:
                tx.execute(text(
                    'UPDATE "Streets_items_Files" SET gate_status = NULL '
                    'WHERE street_id = :s AND file_id = (SELECT sid FROM "File" '
                    'WHERE "oparlKey" = :k LIMIT 1)'),
                    {"s": street_id, "k": file_key})
            assert street_id in _visible_street_ids(engine, file_key)

            # unsure and content pass as well
            for verdict in ("unsure", "content"):
                _set_verdict(engine, street_id, verdict)
                assert street_id in _visible_street_ids(engine, file_key), verdict

            # end-to-end: collect_geo honours the filter — with all links
            # boilerplate the street contributes no features (only
            # observable when the street has geometry)
            if has_geo:
                _set_verdict(engine, street_id, "boilerplate")
                fc = collect_geo(engine, [], [file_key])
                names = {f["properties"]["name"] for f in fc["features"]}
                name = engine.connect().execute(
                    text('SELECT name FROM "Street" WHERE id = :i'),
                    {"i": street_id}).scalar()
                assert name not in names
        finally:
            # restore the cleanup run's verdicts, link by link
            with engine.begin() as tx:
                for file_id, status in originals:
                    tx.execute(text(
                        'UPDATE "Streets_items_Files" SET gate_status = :v '
                        'WHERE street_id = :s AND file_id = :f'),
                        {"v": status, "s": street_id, "f": file_id})
