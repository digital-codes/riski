"""Unit tests for cross-check rendering and mismatch classes (no network)."""

import os
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.kg.kgCrossCheck import classify_mismatch, render_response_text  # noqa: E402


class TestRender:
    def test_render_skips_empty(self):
        txt = render_response_text(
            {"response_type": "kenntnisnahme", "result": "", "expected_cost": ""}
        )
        assert txt == "Art der Antwort: kenntnisnahme"

    def test_render_orders_fields(self):
        txt = render_response_text(
            {"planned_action": "Sanierung prüfen", "response_type": "zugestimmt"}
        )
        assert txt.index("Art der Antwort") < txt.index("Geplante Maßnahme")


class TestClassify:
    def test_english_leakage(self):
        assert classify_mismatch("Antwort contains English the and of") == "english-leakage"

    def test_invented_cost(self):
        assert classify_mismatch("Kosten 5000 € nicht im Originaltext") == "invented-cost"

    def test_wrong_executor(self):
        assert classify_mismatch("falsche ausführende Stelle genannt") == "wrong-executor"

    def test_other(self):
        assert classify_mismatch("inhaltlich abweichend") == "other"


class TestSystemOneVerdict:
    def test_noul_threshold_mapping(self):
        from src.kg import kgCrossCheck as cc

        assert cc.NOUL_CONTRADICTION_THRESHOLD == 0.5
        assert "contradicts" in cc._CONTRADICTION_QUESTIONS
        assert cc._CONTRADICTION_QUESTIONS["contradicts"]["type"] == "noul"

    def test_remote_has_systemone(self):
        from src.kg.kgRemote import KgRemote

        assert hasattr(KgRemote, "systemone")
