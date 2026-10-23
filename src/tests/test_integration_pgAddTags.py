"""Tests for src.pgAddTags – grouping logic (unit) and live export (integration)."""

import importlib.util
import json
import pathlib
import sys

import pytest

from src import db
from src.pgAddTags import (
    AGENDA_GROUP_PATTERNS,
    FILE_GROUP_PATTERNS,
    categorize_name,
    group_rows,
)

# ---------------------------------------------------------------------------
# Unit tests: keyword grouping
# ---------------------------------------------------------------------------


class TestCategorizeName:
    @pytest.mark.parametrize("name,expected", [
        ("Protokoll der Sitzung", "Protokolle"),
        ("Anfrage der Fraktion X", "Anfragen"),
        ("Antrag auf XYZ", "Anträge"),
        ("Änderungsantrag 5", "Änderungsanträge"),
        ("Bekanntgabe 3", "Bekanntgaben"),
        ("Beschluss Nr. 12", "Beschlüsse"),
        ("Mitteilung des OB", "Mitteilungen"),
        ("Bürgerfragestunde", "Bürgerfragestunden"),
        ("Bauantrag der Firma", "Bauanträge"),
        ("Bebauungsplan Oststadt", "Bebauungspläne"),
        ("Haushalt der Stadt", "Haushalt"),
        ("Jahresabschluss 2024", "Jahresabschluss"),
        ("Prüfung des Kassenwesens", "Prüfung"),
    ])
    def test_german_keyword_groups(self, name, expected):
        assert categorize_name(name, AGENDA_GROUP_PATTERNS) == expected

    def test_other_when_no_match(self):
        assert categorize_name("ganz anderer Text", AGENDA_GROUP_PATTERNS) == "Other"

    def test_case_insensitive(self):
        assert categorize_name("PROTOKOLL", AGENDA_GROUP_PATTERNS) == "Protokolle"

    def test_file_patterns(self):
        assert categorize_name("Tagesordnung 03/2024", FILE_GROUP_PATTERNS) == "Tagesordnung"
        assert categorize_name("TOP 5", FILE_GROUP_PATTERNS) == "TOP"
        assert categorize_name("Anlage 2", FILE_GROUP_PATTERNS) == "Anlagen"


class TestGroupRows:
    def test_dash_prefixed_names_ignored(self):
        rows = [(1, "k1", "Protokoll A"), (2, "k2", "- abgesetzt")]
        groups = group_rows(rows, AGENDA_GROUP_PATTERNS, min_group_size=1)
        assert all(item["name"] != "- abgesetzt" for items in groups.values() for item in items)
        assert groups["Protokolle"][0]["key"] == "k1"

    def test_small_groups_merged_into_other(self):
        rows = [(1, "k1", "Protokoll A"), (2, "k2", "ganz anderes"), (3, "k3", "anderes 2")]
        groups = group_rows(rows, AGENDA_GROUP_PATTERNS, min_group_size=2)
        # "Protokolle" (1 item) and unmatched (2 items) -> only Protokolle merged
        assert "Protokolle" not in groups
        assert groups["Other"]

    def test_large_groups_kept(self):
        rows = [(i, f"k{i}", f"Protokoll {i}") for i in range(15)]
        groups = group_rows(rows, AGENDA_GROUP_PATTERNS, min_group_size=10)
        assert len(groups["Protokolle"]) == 15

    def test_row_structure(self):
        rows = [(7, "kk", "Haushalt")]
        groups = group_rows(rows, AGENDA_GROUP_PATTERNS, min_group_size=1)
        assert groups["Haushalt"] == [{"id": 7, "key": "kk", "name": "Haushalt"}]


# ---------------------------------------------------------------------------
# Integration: live export + parity with the legacy implementation
# ---------------------------------------------------------------------------

pytestmark_integration = pytest.mark.integration


@pytest.fixture(scope="module")
def engine():
    return db.get_engine(readonly=True)


@pytest.fixture(scope="module")
def legacy_module():
    path = pathlib.Path(__file__).resolve().parents[2] / "src" / "pgAddTags.py"
    if not path.exists():
        pytest.skip("legacy src/pgAddTags.py not present")
    src_dir = str(path.parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    spec = importlib.util.spec_from_file_location("legacy_pgAddTags", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestLiveExport:
    def test_main_wells_structured_json(self, engine, tmp_path):
        from src.pgAddTags import main

        out = tmp_path / "json"
        rc = main(["--json-dir", str(out)])
        assert rc == 0
        roles = json.loads((out / "roles.json").read_text())
        results = json.loads((out / "results.json").read_text())
        agenda_groups = json.loads((out / "agenda_groups.json").read_text())
        file_groups = json.loads((out / "file_groups.json").read_text())
        assert isinstance(roles, list)
        assert isinstance(results, list)
        for groups in (agenda_groups, file_groups):
            assert isinstance(groups, dict)
            for items in groups.values():
                assert isinstance(items, list)
                for item in items:
                    assert {"id", "key", "name"} <= set(item.keys())

    def test_matches_legacy_output(self, engine, tmp_path, legacy_module):
        ours_dir = tmp_path / "ours"
        theirs_dir = tmp_path / "theirs"
        from src.pgAddTags import main

        assert main(["--json-dir", str(ours_dir)]) == 0
        assert legacy_module.main(["--json-dir", str(theirs_dir)]) == 0
        for name in ("roles.json", "results.json", "agenda_groups.json", "file_groups.json"):
            ours = json.loads((ours_dir / name).read_text())
            theirs = json.loads((theirs_dir / name).read_text())
            assert ours == theirs, f"mismatch in {name}"
