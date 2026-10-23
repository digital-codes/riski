"""Tests for the geo enrichment modules (local_geo_matching + loaders/refs)."""

import os

import pytest
from sqlalchemy import Column, DateTime, Integer, LargeBinary, MetaData, String, Table, text, select

from src import db
from src.local_geo_matching import (
    NameMatch,
    literal_name_spans,
    name_matches,
    longest_non_overlapping_name_matches,
    prepare_street_matcher,
)

# ---------------------------------------------------------------------------
# Unit tests: boundary-safe literal matching
# ---------------------------------------------------------------------------


class TestLiteralNameSpans:
    def test_basic_match(self):
        assert literal_name_spans("Treffen in der Weststadt", "Weststadt") == [(15, 24)]

    def test_case_insensitive(self):
        assert literal_name_spans("WESTSTADT", "weststadt") == [(0, 9)]

    def test_no_partial_word_match(self):
        # 'Weststadt' must not match inside 'Nordweststadt'
        assert literal_name_spans("Nordweststadt", "Weststadt") == []

    def test_punctuation_is_a_boundary(self):
        assert literal_name_spans('"Weststadt", sagte er', "Weststadt") == [(1, 10)]

    def test_multiple_occurrences(self):
        spans = literal_name_spans("Weststadt und Weststadt", "Weststadt")
        assert len(spans) == 2

    def test_empty_inputs(self):
        assert literal_name_spans("", "x") == []
        assert literal_name_spans("text", "") == []

    def test_name_matches(self):
        assert name_matches("Plenum in Mühlburg", "Mühlburg") is True
        assert name_matches("Plenum", "Mühlburg") is False


class TestLongestNonOverlapping:
    def test_longest_match_wins(self):
        items = [(1, "Durlach"), (2, "Durlacher Allee")]
        matches = longest_non_overlapping_name_matches("Antrag: Durlacher Allee 5", items)
        assert len(matches) == 1
        assert matches[0].item_id == 2
        assert matches[0].name == "Durlacher Allee"

    def test_non_overlapping_both_kept(self):
        items = [(1, "West"), (2, "Ost")]
        matches = longest_non_overlapping_name_matches("West und Ost", items)
        assert {m.item_id for m in matches} == {1, 2}

    def test_sorted_by_position(self):
        items = [(1, "B"), (2, "A")]
        matches = longest_non_overlapping_name_matches("A dann B", items)
        assert [m.start for m in matches] == sorted(m.start for m in matches)

    def test_shorter_shadowed_by_longer(self):
        items = [(1, "Rat"), (2, "Rat der Stadt")]
        matches = longest_non_overlapping_name_matches("Sitzung des Rat der Stadt", items)
        assert [m.item_id for m in matches] == [2]


class TestPreparedStreetMatcher:
    def test_combined_regex_longest_first(self):
        matcher = prepare_street_matcher([(1, "Durlach"), (2, "Durlacher Allee")])
        matches = matcher.matches("Durlacher Allee in Durlach")
        ids = [m.item_id for m in matches]
        assert 2 in ids and 1 in ids
        # 'Durlach' inside 'Durlacher Allee' is not matched separately there
        assert all(m.name == "Durlach" or m.name == "Durlacher Allee" for m in matches)

    def test_duplicate_names_deduplicated(self):
        matcher = prepare_street_matcher([(1, "Ringstraße"), (2, "ringstraße")])
        matches = matcher.matches("Ringstraße 3")
        assert len(matches) == 1

    def test_empty_items(self):
        matcher = prepare_street_matcher([])
        assert matcher.matches("anything") == []

    def test_match_positions(self):
        matcher = prepare_street_matcher([(5, "Kaiserstraße")])
        matches = matcher.matches("An der Kaiserstraße 1")
        assert len(matches) == 1
        m = matches[0]
        assert isinstance(m, NameMatch)
        assert m.item_id == 5
        assert m.start == 7
        assert m.end == 19


# ---------------------------------------------------------------------------
# Integration: loaders + reference builders on test_* tables
# ---------------------------------------------------------------------------

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


@pytest.fixture()
def geo_tables(engine):
    metadata = MetaData()
    streets = Table(
        "test_streets", metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(255), unique=True),
        Column("text", String(255)),
        Column("year", Integer),
        Column("description", String(4096)),
        Column("timestamp", DateTime),
        Column("districtName", String(255)),
        Column("geo", LargeBinary),
    )
    districts = Table(
        "test_districts", metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(255), unique=True),
        Column("number", Integer),
        Column("timestamp", DateTime),
        Column("geo", LargeBinary),
    )
    agendaitems = Table(
        "test_agendaitems", metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(500)),
    )
    street_refs = Table(
        "test_street_refs", metadata,
        Column("id", Integer, primary_key=True),
        Column("street_id", Integer, nullable=False),
        Column("agendaitem_id", Integer, nullable=False),
        Column("name_match", String(255), nullable=False),
    )
    district_refs = Table(
        "test_district_refs", metadata,
        Column("id", Integer, primary_key=True),
        Column("district_id", Integer, nullable=False),
        Column("agendaitem_id", Integer, nullable=False),
        Column("name_match", String(255), nullable=False),
        Column("created_at", DateTime),
    )
    metadata.create_all(engine, checkfirst=True)
    with engine.begin() as conn:
        for tbl in (streets, districts, agendaitems, street_refs, district_refs):
            conn.execute(tbl.delete())
    yield {"streets": streets, "districts": districts, "agendaitems": agendaitems,
           "street_refs": street_refs, "district_refs": district_refs}
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS test_street_refs CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS test_district_refs CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS test_agendaitems CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS test_districts CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS test_streets CASCADE"))


class TestStreetAndDistrictLoading:
    def test_load_streets_no_duplicates(self, engine, geo_tables):
        from src import pgAddStreets

        data = [
            {"name": "Kaiserstraße", "text": "benannt nach Kaiser Wilhelm"},
            {"name": "Mühlburg", "text": "Stadtteil"},
        ]
        # run the insert loop logic via a small driver replicating main()'s body
        streets_tbl = geo_tables["streets"]
        from datetime import datetime, timezone
        from sqlalchemy import LargeBinary

        with engine.connect() as conn:
            for street in data:
                name = street.get("name")
                existing = conn.execute(
                    select(streets_tbl).where(streets_tbl.c.name == name)
                ).fetchone()
                if existing:
                    continue
                conn.execute(streets_tbl.insert().values(
                    name=name,
                    text=street.get("text"),
                    year=street.get("year"),
                    description=None,
                    geo=None,
                    timestamp=datetime.now(timezone.utc),
                ))
            conn.commit()

            # duplicate load is a no-op
            for street in data:
                name = street.get("name")
                existing = conn.execute(
                    select(streets_tbl).where(streets_tbl.c.name == name)
                ).fetchone()
                if existing:
                    continue
                conn.execute(streets_tbl.insert().values(
                    name=name, text=street.get("text"), geo=None,
                    timestamp=datetime.now(timezone.utc),
                ))
            conn.commit()

        with engine.connect() as conn:
            names = [r[0] for r in conn.execute(select(streets_tbl.c.name)).fetchall()]
        assert sorted(names) == ["Kaiserstraße", "Mühlburg"]

    def test_load_districts_no_duplicates(self, engine, geo_tables):
        districts_tbl = geo_tables["districts"]
        from datetime import datetime, timezone

        rows = [("Innstadtstadtteil", 10), ("Weststadt", 11)]
        with engine.connect() as conn:
            for name, number in rows:
                existing = conn.execute(
                    select(districts_tbl).where(districts_tbl.c.name == name)
                ).fetchone()
                if existing:
                    continue
                conn.execute(districts_tbl.insert().values(
                    name=name, number=number, geo=None,
                    timestamp=datetime.now(timezone.utc),
                ))
            conn.commit()
        with engine.connect() as conn:
            names = [r[0] for r in conn.execute(select(districts_tbl.c.name)).fetchall()]
        assert sorted(names) == ["Innstadtstadtteil", "Weststadt"]


class TestReferenceBuilders:
    def test_street_refs_match_and_deduplicate(self, engine, geo_tables):
        streets_tbl = geo_tables["streets"]
        agenda_tbl = geo_tables["agendaitems"]
        ref_tbl = geo_tables["street_refs"]

        with engine.begin() as conn:
            conn.execute(streets_tbl.insert().values(id=1, name="Kaiserstraße"))
            conn.execute(streets_tbl.insert().values(id=2, name="Durlacher Allee"))
            conn.execute(agenda_tbl.insert().values(id=100, name="Bauantrag Kaiserstraße 12"))
            conn.execute(agenda_tbl.insert().values(id=101, name="Unrelated topic"))

        # build refs using the shared matcher logic from the module
        from src.pgAddStreetRefs import prepare_street_matcher
        from datetime import datetime, timezone

        with engine.connect() as conn:
            streets = [(r.id, r.name) for r in conn.execute(select(streets_tbl.c.id, streets_tbl.c.name)).fetchall()]
            matcher = prepare_street_matcher(streets)
            agendaitems = conn.execute(select(agenda_tbl.c.id, agenda_tbl.c.name)).fetchall()
            existing_pairs = set()
            pending = []
            for row in agendaitems:
                if not row.name:
                    continue
                for match in matcher.matches(row.name):
                    pair = (match.item_id, row.id)
                    if pair not in existing_pairs:
                        existing_pairs.add(pair)
                        pending.append({
                            "street_id": match.item_id,
                            "agendaitem_id": row.id,
                            "name_match": row.name,
                            "created_at": datetime.now(timezone.utc),
                        })
            if pending:
                conn.execute(ref_tbl.insert(), pending)
            conn.commit()

        with engine.connect() as conn:
            pairs = conn.execute(select(ref_tbl.c.street_id, ref_tbl.c.agendaitem_id)).fetchall()
        assert set(pairs) == {(1, 100)}  # only Kaiserstraße matched; unrelated item untouched

        # re-run: no duplicates
        with engine.connect() as conn:
            streets = [(r.id, r.name) for r in conn.execute(select(streets_tbl.c.id, streets_tbl.c.name)).fetchall()]
            matcher = prepare_street_matcher(streets)
            existing_pairs = {
                (r.street_id, r.agendaitem_id)
                for r in conn.execute(select(ref_tbl.c.street_id, ref_tbl.c.agendaitem_id)).fetchall()
            }
            new_pending = []
            for row in conn.execute(select(agenda_tbl.c.id, agenda_tbl.c.name)).fetchall():
                if not row.name:
                    continue
                for match in matcher.matches(row.name):
                    if (match.item_id, row.id) not in existing_pairs:
                        new_pending.append({"street_id": match.item_id, "agendaitem_id": row.id})
            assert new_pending == []

    def test_district_refs_boundary_safe(self, engine, geo_tables):
        from src.local_geo_matching import name_matches as nm
        from datetime import datetime, timezone

        districts_tbl = geo_tables["districts"]
        agenda_tbl = geo_tables["agendaitems"]
        ref_tbl = geo_tables["district_refs"]

        with engine.begin() as conn:
            conn.execute(districts_tbl.insert().values(id=1, name="Weststadt", number=11))
            conn.execute(agenda_tbl.insert().values(id=200, name="Sanierung Weststadt"))
            conn.execute(agenda_tbl.insert().values(id=201, name="Nordweststadt Planung"))

        with engine.connect() as conn:
            districts = conn.execute(select(districts_tbl.c.id, districts_tbl.c.name)).fetchall()
            agendaitems = conn.execute(select(agenda_tbl.c.id, agenda_tbl.c.name)).fetchall()
            inserted = []
            for d in districts:
                for a in agendaitems:
                    if not a.name or not d.name:
                        continue
                    # boundary-safe: 'Weststadt' must NOT match inside 'Nordweststadt'
                    if nm(a.name, d.name):
                        inserted.append((d.id, a.id, a.name))
            for district_id, agendaitem_id, name_match in inserted:
                conn.execute(ref_tbl.insert().values(
                    district_id=district_id,
                    agendaitem_id=agendaitem_id,
                    name_match=name_match,
                    created_at=datetime.now(timezone.utc),
                ))
            conn.commit()

        with engine.connect() as conn:
            pairs = conn.execute(select(ref_tbl.c.district_id, ref_tbl.c.agendaitem_id)).fetchall()
        assert set(pairs) == {(1, 200)}
