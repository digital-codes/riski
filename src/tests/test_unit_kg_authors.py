"""Unit tests for party author identification (no network)."""

import os
import sys
from datetime import date

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from src.kg.kgAuthors import author_from_text, era_allows  # noqa: E402
from src.kg.kgVocab import load_vocab  # noqa: E402

VOCAB = load_vocab()


class TestEraAllows:
    def test_null_era_always_valid(self):
        assert era_allows(None, date(1990, 1, 1)) is True

    def test_era_bounds(self):
        era = [["2009-01-01", "2014-12-31"]]
        assert era_allows(era, date(2012, 5, 1)) is True
        assert era_allows(era, date(2016, 1, 1)) is False

    def test_era_none_dates(self):
        era = [["2018-01-01", None]]  # open-ended
        assert era_allows(era, date(2026, 1, 1)) is True


class TestAuthorFromText:
    def test_cdu_name(self):
        label, pat = author_from_text(
            "Antrag der CDU-Fraktion: Parkhaus B redesigned", date(2024, 3, 1), VOCAB["party_variants"]
        )
        assert label == "CDU"

    def test_green_case_insensitive(self):
        label, _ = author_from_text(
            "Antrag der Fraktion BÜNDNIS 90/DIE GRÜNEN", date(2020, 1, 1), VOCAB["party_variants"]
        )
        assert label == "GRÜNE"

    def test_kal(self):
        label, _ = author_from_text(
            "Antrag KAL: K知limaneutrale Stadt", date(2021, 1, 1), VOCAB["party_variants"]
        )
        assert label == "KAL"

    def test_unknown_stays_empty(self):
        label, pattern = author_from_text(
            "Bekanntgabe nichtöffentlich gefasster Beschlüsse", date(2024, 1, 1), VOCAB["party_variants"]
        )
        assert label is None and pattern == ""
