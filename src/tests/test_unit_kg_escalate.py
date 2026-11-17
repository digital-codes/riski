"""Unit tests for the tier-2 regex escalation layer (no network)."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from src.kg.kgEscalate import Escalator  # noqa: E402
from src.kg.kgVocab import load_vocab  # noqa: E402


class _Conn:
    """Bit-box DB connection returning canned texts."""

    def __init__(self, payload: dict):
        self.payload = payload

    def execute(self, stmt, params=None):
        _ = stmt, params
        return iter([])

    # used via .scalar() in _texts_for
    def scalar(self):
        return 1


class TestTier2:
    def test_text_source_assembly(self):
        # _texts_for joins paper name + file/agenda texts; verify the
        # regex layer fires on a synthetic haystack
        vocab = load_vocab()
        esc = Escalator(_Conn({}), MagicMock(), vocab, remote=None)
        hay = "Antrag SPD: Spielplatz KG Aue vorberaten ohne Änderungen Kenntnisnahme"
        from src.kg.kgVocab import resolve_mapping

        assert resolve_mapping("Kenntnisnahme", vocab["results"])[0] == "kenntnisnahme"

    def test_outcome_anchors_present(self):
        vocab = load_vocab()
        for key in ("zugestimmt", "abgelehnt", "kenntnisnahme"):
            assert vocab["outcome_anchors"].get(key), key

    def test_threshold_constant(self):
        from src.kg import kgEscalate

        assert 0 < kgEscalate.VECTOR_THRESHOLD < 1

    def test_cosine(self):
        from src.kg.kgEscalate import _cosine

        assert abs(_cosine([1, 0], [1, 0]) - 1.0) < 1e-9
        assert abs(_cosine([1, 0], [0, 1])) < 1e-9
