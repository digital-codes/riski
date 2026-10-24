"""Unit tests for the organization classification backfill (src.pgAddOrgClassification)."""

from __future__ import annotations

import pytest

from src.pgAddOrgClassification import derive_classification

pytestmark = pytest.mark.unit


class TestDeriveClassification:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Ortschaftsrat Neureut", "Ortschaftsrat"),
            ("Ortschaftsrat Grötzingen", "Ortschaftsrat"),
            ("Gemeinderat", "Gemeinderat"),
            ("Gemeinderat - Beratungen zum DHH", "Gemeinderat"),
            ("Bauausschuss", "Ausschuss"),
            ("Ausschuss für Umwelt und Gesundheit", "Ausschuss"),
            ("Betriebsausschuss Eigenbetrieb Stadtentwässerung", "Ausschuss"),
            ("Haupt- und Finanzausschuss", "Ausschuss"),
            ("Gestaltungsbeirat", "Beirat und Stiftung"),
            ("Ortsverwaltung Neureut", "Ortsverwaltung"),
            ("Dezernat 2", "Dezernat"),
            ("Tiefbauamt", "Amt"),
            ("Amt für Hochbau und Gebäudewirtschaft", "Amt"),
            ("Eigenbetrieb Gewerbeflächen", "Eigenbetrieb"),
            ("Fraktionsgeschäftsstelle", "Fraktion"),
            ("Karlsruhe Tourismus GmbH", "Beteiligungsgesellschaft"),
            ("Karlsruher Verkehrsverbund", "Beteiligungsgesellschaft"),
            ("Stadtwerke", "Beteiligungsgesellschaft"),
            ("Stabsstelle Projektcontrolling", "Stabsstelle"),
            ("AVG", "Sonstiges"),
            ("KASIG", "Sonstiges"),
            ("Offen", "Sonstiges"),
        ],
    )
    def test_rules(self, name, expected):
        assert derive_classification(name) == expected

    def test_case_insensitive(self):
        assert derive_classification("ortschaftsrat neureut") == "Ortschaftsrat"
        assert derive_classification("BAUAUSSCHUSS") == "Ausschuss"

    def test_empty_input(self):
        assert derive_classification(None) is None
        assert derive_classification("") is None
        assert derive_classification("   ") is None

    def test_specific_before_generic(self):
        # Betriebsausschuss *Eigenbetrieb* — the Ausschuss rule must win
        # over the Eigenbetrieb rule (listed earlier).
        assert derive_classification(
            'Betriebsausschuss "Eigenbetrieb Fußballstadion im Wildpark"'
        ) == "Ausschuss"
