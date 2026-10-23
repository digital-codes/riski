"""Unit tests for src.pgGen – pure logic, fixture JSON, no database."""

import pytest
from sqlalchemy import MetaData

from src.pgGen import (
    Entity,
    EntityKey,
    build_base_row,
    collect_entities_from_obj,
    detect_relationships,
    detect_scalar_columns,
    infer_scalar_type,
    is_scalar,
    make_assoc_tables,
    make_main_tables,
    parse_datetime_maybe,
    safe_col_name,
    table_name_from_type,
    trailing_id_from_oparl_id,
    to_int_if_possible,
    verify_preservation,
)

# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


def _meeting(id_url, body_url, name="Ausschuss"):
    return {
        "id": id_url,
        "type": "https://schema.oparl.org/1.1/Meeting",
        "name": name,
        "start": "2024-03-01T18:00:00+02:00",
        "organization": [body_url],
        "location": {"id": f"{id_url}/location", "type": "https://schema.oparl.org/1.1/Location"},
    }


def _body(id_url):
    return {"id": id_url, "type": "https://schema.oparl.org/1.1/Body", "name": "Karlsruhe"}


@pytest.fixture()
def entities_and_maps():
    entities = {}
    url_to_key = {}
    body_url = "https://ris.karlsruhe.de/oparl/body/1"
    m1 = _meeting("https://ris.karlsruhe.de/oparl/meeting/961", body_url)
    collect_entities_from_obj({"data": [m1, _body(body_url)]}, entities, url_to_key, "File1.json")
    return entities, url_to_key


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_parse_datetime_iso(self):
        assert parse_datetime_maybe("2016-10-12T09:08:40+02:00").strftime("%Y-%m-%d %H:%M:%S") == "2016-10-12 09:08:40"

    def test_parse_datetime_date_formats(self):
        assert parse_datetime_maybe("2024-03-01") is not None
        assert parse_datetime_maybe("01.03.2024") is not None

    def test_parse_datetime_invalid(self):
        assert parse_datetime_maybe("not a date") is None
        assert parse_datetime_maybe(None) is None
        assert parse_datetime_maybe("") is None

    def test_table_name_from_type(self):
        assert table_name_from_type("https://schema.oparl.org/1.1/Meeting") == "Meeting"
        assert table_name_from_type("https://schema.oparl.org/1.1/Meeting/") == "Meeting"

    def test_trailing_id(self):
        assert trailing_id_from_oparl_id(".../meetings/961") == "961"
        assert trailing_id_from_oparl_id("https://x/system") == "system"

    def test_to_int_if_possible(self):
        assert to_int_if_possible("961") == 961
        assert to_int_if_possible("system") is None

    def test_safe_col_name_reserved(self):
        name, quote = safe_col_name("order")
        assert name == "order_col"
        assert quote is True

    def test_safe_col_name_plain(self):
        name, quote = safe_col_name("name")
        assert name == "name"
        assert quote is False

    def test_safe_col_name_special_chars(self):
        name, quote = safe_col_name("a-b c")
        assert name == "a_b_c"

    def test_safe_col_name_digit_start(self):
        name, _ = safe_col_name("1st")
        assert name == "k_1st"

    def test_infer_scalar_types(self):
        from sqlalchemy import BigInteger, Boolean, DateTime, Float, String

        assert infer_scalar_type([1, 2, 3]) == BigInteger
        assert infer_scalar_type([1, 2.5]) == Float
        assert infer_scalar_type([True, False]) == Boolean
        assert infer_scalar_type(["2024-01-01", "2024-01-02"]) == DateTime
        assert infer_scalar_type(["a", "b"]).length == 256
        assert type(infer_scalar_type(["a", "b"])) is String
        assert infer_scalar_type([None, None]).length == 256

    def test_is_scalar(self):
        assert is_scalar("x") and is_scalar(1) and is_scalar(1.5) and is_scalar(True)
        assert is_scalar(None)
        assert not is_scalar([1]) and not is_scalar({"a": 1})


# ---------------------------------------------------------------------------
# Pass 1 / Pass 2 on fixture data
# ---------------------------------------------------------------------------


class TestCollectEntities:
    def test_finds_nested_entities(self, entities_and_maps):
        entities, url_to_key = entities_and_maps
        tables = {k.table for k in entities}
        assert tables == {"Meeting", "Body", "Location"}
        assert len(entities) == 3
        assert "https://ris.karlsruhe.de/oparl/body/1" in url_to_key

    def test_duplicate_urls_merge_sources(self, entities_and_maps):
        entities, url_to_key = entities_and_maps
        body_url = "https://ris.karlsruhe.de/oparl/body/1"
        collect_entities_from_obj(
            {"data": [_body(body_url)]}, entities, url_to_key, "File2.json"
        )
        key = url_to_key[body_url]
        assert entities[key].sources == {"File1.json", "File2.json"}


class TestDetectRelationships:
    def test_single_fk_from_url_string(self, entities_and_maps):
        entities, url_to_key = entities_and_maps
        # the body reference in Meeting is embedded in a list -> many field;
        # location is an embedded dict -> single FK
        single, many = detect_relationships(entities, url_to_key)
        assert single.get("Meeting", {}).get("location") == "Location"

    def test_many_fk_from_url_list(self):
        entities = {}
        url_to_key = {}
        body_url = "https://ris.karlsruhe.de/oparl/body/1"
        m = _meeting("https://ris.karlsruhe.de/oparl/meeting/1", body_url)
        m["organization"] = [body_url]  # list of URL strings
        collect_entities_from_obj({"data": [m, _body(body_url)]}, entities, url_to_key, "F.json")
        single, many = detect_relationships(entities, url_to_key)
        assert many.get("Meeting", {}).get("organization") == "Body"

    def test_id_and_type_not_detected(self, entities_and_maps):
        entities, url_to_key = entities_and_maps
        single, many = detect_relationships(entities, url_to_key)
        for field_map in (single.get("Meeting", {}), many.get("Meeting", {})):
            assert "id" not in field_map
            assert "type" not in field_map


class TestDetectScalarColumns:
    def test_scalars_detected_and_renamed(self, entities_and_maps):
        entities, url_to_key = entities_and_maps
        single, many = detect_relationships(entities, url_to_key)
        scalar_types, scalar_colnames, scalar_quote = detect_scalar_columns(
            entities, single, many
        )
        meeting_scalars = scalar_colnames.get("Meeting", {})
        assert meeting_scalars.get("name") == "name"
        assert "start" in meeting_scalars  # renamed reserved word
        assert scalar_colnames["Meeting"]["start"] == "start_date"

    def test_fk_and_relation_fields_excluded(self, entities_and_maps):
        entities, url_to_key = entities_and_maps
        single, many = detect_relationships(entities, url_to_key)
        scalar_types, scalar_colnames, _ = detect_scalar_columns(
            entities, single, many
        )
        assert "location" not in scalar_colnames.get("Meeting", {})
        assert "organization" not in scalar_colnames.get("Meeting", {})
        assert "created" not in scalar_colnames.get("Meeting", {})


# ---------------------------------------------------------------------------
# Schema build (in-memory only)
# ---------------------------------------------------------------------------


class TestSchemaBuild:
    def _build(self, entities_and_maps):
        entities, url_to_key = entities_and_maps
        single, many = detect_relationships(entities, url_to_key)
        scalar_types, scalar_colnames, scalar_quote = detect_scalar_columns(
            entities, single, many
        )
        all_tables = {k.table for k in entities}
        metadata = MetaData()
        main = make_main_tables(
            metadata, all_tables, single, scalar_types, scalar_colnames, scalar_quote
        )
        assoc = make_assoc_tables(metadata, many, single)
        return metadata, main, assoc

    def test_main_tables_have_core_columns(self, entities_and_maps):
        metadata, main, assoc = self._build(entities_and_maps)
        meeting = main["Meeting"]
        names = {c.name for c in meeting.columns}
        assert {"sid", "id", "oparlKey", "oparlId", "type", "created", "modified", "data"} <= names

    def test_file_gets_content_and_teaser(self, entities_and_maps):
        entities, url_to_key = entities_and_maps
        file_url = "https://ris.karlsruhe.de/oparl/file/1"
        collect_entities_from_obj(
            {"data": [{
                "id": file_url,
                "type": "https://schema.oparl.org/1.1/File",
                "name": "report.pdf",
            }]},
            entities, url_to_key, "F.json",
        )
        metadata, main, assoc = self._build((entities, url_to_key))
        names = {c.name for c in main["File"].columns}
        assert "content" in names and "teaser" in names

    def test_assoc_table_naming(self, entities_and_maps):
        metadata, main, assoc = self._build(entities_and_maps)
        assert "Meeting__location__Location" in assoc
        assert "Meeting__organization__Body" in assoc

    def test_fk_column_added(self, entities_and_maps):
        metadata, main, assoc = self._build(entities_and_maps)
        names = {c.name for c in main["Meeting"].columns}
        assert "locationSid" in names


class TestBuildBaseRow:
    def test_row_fields(self, entities_and_maps):
        entities, url_to_key = entities_and_maps
        single, many = detect_relationships(entities, url_to_key)
        scalar_types, scalar_colnames, _ = detect_scalar_columns(entities, single, many)
        ent = next(e for e in entities.values() if e.key.table == "Meeting")
        row = build_base_row(ent, scalar_types, scalar_colnames)
        assert row["oparlKey"] == "961"
        assert row["id"] == 961
        assert row["type"].endswith("Meeting")
        assert row["created"] is None  # fixture has no 'created' key
        assert row["start_date"] is not None
        assert row["data"]["name"] == ent.raw["name"]
        assert row["name"] == "Ausschuss"
        assert row["start_date"] is not None


# ---------------------------------------------------------------------------
# Preservation checks (pure)
# ---------------------------------------------------------------------------


class TestVerifyPreservation:
    def test_no_decrease_passes(self):
        before = {"generated": {"File.content": {"non_null": 5, "non_empty": 4}}}
        after = {"generated": {"File.content": {"non_null": 6, "non_empty": 4}}}
        verify_preservation(before, after)  # should not raise

    def test_decrease_raises(self):
        before = {"generated": {"File.content": {"non_null": 5, "non_empty": 4}}}
        after = {"generated": {"File.content": {"non_null": 4, "non_empty": 4}}}
        with pytest.raises(RuntimeError, match="lossless migration check failed"):
            verify_preservation(before, after)

    def test_missing_key_treated_as_zero(self):
        before = {"generated": {"File.content": {"non_null": 1, "non_empty": 1}}}
        with pytest.raises(RuntimeError):
            verify_preservation(before, {"generated": {}})

pytestmark = pytest.mark.unit
