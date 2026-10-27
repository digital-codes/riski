"""Unit tests for instance-agnostic enrichment rules (change:
instance-agnostic-config): address regex, venue noise, document-type
canonicalization, org classification, district columns."""

from __future__ import annotations

import pytest

import src.geoGate as gg
import src.pgAddOrgClassification as oc
import src.pgCategorise as cat
from src.instanceConfig import clear_cache
from src.pgAddFileGeoRefs import strip_venue_noise

pytestmark = pytest.mark.unit


@pytest.fixture
def city_rules(monkeypatch):
    """Point the instance config's address city at München for the test."""
    monkeypatch.setenv("RISKI_RULES__ADDRESS_REGEX_CITY", "München")
    clear_cache()
    yield
    clear_cache()


class TestAddressRegex:
    def test_default_karlsruhe_matches_old_pattern(self):
        rx = gg._address_regex("Kaiserstraße")
        assert rx.search("Kaiserstraße 21, 76133 Karlsruhe")
        assert not rx.search("Kaiserstraße 21, 80331 München")

    def test_configured_city(self, city_rules):
        rx = gg._address_regex("Sendlinger Straße")
        assert rx.search("Sendlinger Straße 21, 80331 München")
        assert not rx.search("Sendlinger Straße 21, 76133 Karlsruhe")

    def test_reason_carries_configured_city(self, city_rules):
        assert "München" in gg.regex_boilerplate_reason()

    def test_prompt_names_configured_city(self, city_rules):
        prompt = gg.GeoGate(engine=None).build_prompt(
            "d", "t", "c", [{"entity": "X"}])
        assert "Stadt München" in prompt
        assert "Hebelstraße 21, 12345 München" in prompt


class TestVenueNoise:
    def test_karlsruhe_default_strips_townhall(self):
        text = "Tagesordnung\nBürgersaal, Rathaus am Marktplatz\nTOP 1"
        assert "Rathaus" not in strip_venue_noise(text)
        assert "Tagesordnung" in strip_venue_noise(text)

    def test_content_mentions_survive(self):
        text = "Sanierung des Marktplatzes"
        assert strip_venue_noise(text) == text

    def test_empty_config_disables_stripping(self, monkeypatch):
        import yaml as _y

        monkeypatch.setenv("RISKI_RULES__VENUE_NOISE", "[]")
        clear_cache()
        try:
            text = "Bürgersaal, Rathaus am Marktplatz"
            assert strip_venue_noise(text) == text
        finally:
            clear_cache()


class TestDocTypeCanonicalization:
    def test_default_folds_thh_codes(self):
        assert cat.canonicalize_document_type("Haushalt THH 1234") == \
            ("Haushalt", "1234")
        assert cat.canonicalize_document_type("Haushalt") == ("Haushalt", None)
        assert cat.canonicalize_document_type("Beschlussvorlage") == \
            ("Beschlussvorlage", None)

    def test_disabled_passes_through(self, monkeypatch):
        monkeypatch.setenv("RISKI_RULES__HAUSHALT_CODES", "false")
        clear_cache()
        try:
            assert cat.canonicalize_document_type("Haushalt THH 1234") == \
                ("Haushalt THH 1234", None)
        finally:
            clear_cache()


class TestOrgClassification:
    def test_default_parity(self):
        assert oc.derive_classification("Ortschaftsrat Neureut") == \
            "Ortschaftsrat"
        assert oc.derive_classification(" Irgendein Verein") == \
            oc.FALLBACK_CLASSIFICATION

    def test_custom_rules_from_config(self, monkeypatch):
        monkeypatch.setenv(
            "RISKI_RULES__ORG_CLASSIFICATION",
            '[{pattern: "ausschusss?", label: Kommittee}, '
            '{pattern: ".", label: Andere}]')
        monkeypatch.setenv("RISKI_RULES__ORG_CLASSIFICATION_FALLBACK", "Rest")
        clear_cache()
        try:
            assert oc.derive_classification("Bauausschuss") == "Kommittee"
            assert oc.derive_classification("Irgendwas") == "Andere"
            assert oc.derive_classification("x") == "Andere"  # fallback unused
        finally:
            clear_cache()

    def test_empty_rules_fall_back_to_constants(self, monkeypatch):
        monkeypatch.setenv("RISKI_RULES__ORG_CLASSIFICATION", "[]")
        clear_cache()
        try:
            assert oc.derive_classification("Ortschaftsrat X") == \
                "Ortschaftsrat"
        finally:
            clear_cache()
