"""Unit tests for the protocol verification gate (TOP/result checks)."""

import os
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from src.kg.kgProtocols import detect_outcome, outcome_word_scope, verify_protocol  # noqa: E402

_HEAD_2025 = (
    "Niederschrift\n10. Plenarsitzung des Gemeinderates\n"
    "27. Mai 2025, 15:30 Uhr\nöffentlich\n"
    "Punkt 35 der Tagesordnung: Bekanntgabe nichtöffentlich gefasster Beschlüsse\n"
    "Beschluss:\nKenntnisnahme\n"
)

_HEAD_AUSCHUSS = (
    "# Punkt 12 der Tagesordnung: Bauanträge\n"
    "Beschluss:\neinstimmig abgelehnt\n"
)


class TestVerifyProtocol:
    def test_top_and_result_match(self):
        top, result = verify_protocol(_HEAD_2025, "35", "kenntnisnahme")
        assert top is True
        assert result is True

    def test_top_number_mismatch(self):
        top, result = verify_protocol(_HEAD_2025, "38", "kenntnisnahme")
        assert top is False

    def test_result_mismatch(self):
        top, result = verify_protocol(
            "Punkt 41 der Tagesordnung: Antrag CDU\n"
            "Beschluss:\neinstimmig abgelehnt\n",
            "41",
            "zugestimmt",
        )
        assert top is True and result is False

    def test_no_top_reference(self):
        top, result = verify_protocol(
            "Anwesenheit (Protokoll)\nBeschluss:\nKenntnisnahme\n", None, None
        )
        assert top is False

    def test_empty_text(self):
        top, result = verify_protocol(None, "35", "kenntnisnahme")
        assert top is False and result is False


class TestDetectOutcome:
    def test_kenntnisnahme(self):
        assert detect_outcome("Beschluss:\nKenntnisnahme\n") == "kenntnisnahme"

    def test_zugestimmt(self):
        assert detect_outcome("Beschluss:\neinstimmig zugestimmt\n") == "zugestimmt"

    def test_verwiesen_in_fachausschuss(self):
        assert detect_outcome("verwiesen in Fachausschuss") == "verwiesen"

    def test_vertagt_zurueckgestellt(self):
        assert detect_outcome("Behandlung wurde zurückgestellt") == "vertagt"

    def test_nothing(self):
        assert detect_outcome("Der Vorsitzende ruft auf") is None

    def test_scope_finds_beschluss(self):
        scope = outcome_word_scope(_HEAD_2025)
        assert "kenntnisnahme" in scope.lower()
