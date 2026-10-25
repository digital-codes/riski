"""Unit tests for the category derivation helpers (src.update.pgCategorise)."""

from __future__ import annotations

import pytest

from src.update.pgCategorise import (
    SOURCE_CONFIDENCE,
    SOURCE_PRECEDENCE,
    canonicalize_document_type,
    default_confidence,
    precedence,
    resolve_precedence,
)


class TestPrecedence:
    def test_order_is_documented(self):
        assert SOURCE_PRECEDENCE == [
            "papertype",
            "oparl-keyword",
            "name-regex",
            "llm",
            "manual",
        ]

    def test_papertype_beats_everything(self):
        assert resolve_precedence(["llm", "name-regex", "papertype"]) == "papertype"

    def test_llm_is_weakest_deterministic_source(self):
        assert resolve_precedence(["llm", "name-regex"]) == "name-regex"

    def test_empty_returns_none(self):
        assert resolve_precedence([]) is None

    def test_unknown_sources_ignored(self):
        assert resolve_precedence(["horoscope", "llm"]) == "llm"
        assert resolve_precedence(["horoscope"]) is None

    def test_single_known_source(self):
        assert resolve_precedence(["name-regex"]) == "name-regex"

    def test_precedence_unknown_source_raises(self):
        with pytest.raises(ValueError, match="Unknown tag source"):
            precedence("horoscope")


class TestDefaultConfidence:
    def test_documented_defaults(self):
        assert SOURCE_CONFIDENCE["papertype"] == 1.0
        assert SOURCE_CONFIDENCE["oparl-keyword"] == 0.9
        assert SOURCE_CONFIDENCE["name-regex"] == 0.7
        assert SOURCE_CONFIDENCE["llm"] == 0.5

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError, match="Unknown tag source"):
            default_confidence("horoscope")


class TestCanonicalizeDocumentType:
    def test_passthrough_values(self):
        assert canonicalize_document_type("Beschlussvorlage") == ("Beschlussvorlage", None)
        assert canonicalize_document_type("Antrag") == ("Antrag", None)
        assert canonicalize_document_type("Änderungs-/Ergänzungsantrag") == (
            "Änderungs-/Ergänzungsantrag",
            None,
        )

    def test_haushalt_thh_code_folds(self):
        assert canonicalize_document_type("Haushalt THH 4100") == ("Haushalt", "4100")
        assert canonicalize_document_type("Haushalt 3100") == ("Haushalt", "3100")
        assert canonicalize_document_type("haushalt thh 8800") == ("Haushalt", "8800")

    def test_haushalt_without_code(self):
        assert canonicalize_document_type("Haushalt Gesamt") == ("Haushalt", None)

    def test_empty_input(self):
        assert canonicalize_document_type(None) == (None, None)
        assert canonicalize_document_type("") == (None, None)
        assert canonicalize_document_type("   ") == (None, None)

    def test_whitespace_is_stripped(self):
        assert canonicalize_document_type("  Antrag ") == ("Antrag", None)
