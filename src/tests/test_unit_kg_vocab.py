"""Unit tests for the kg vocabulary loading and normalization layer."""

import os
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from src.kg.kgVocab import DEFAULT_PATH, load_vocab, resolve_mapping  # noqa: E402


class TestVocabLoad:
    def test_file_exists_and_loads(self):
        assert os.path.exists(DEFAULT_PATH)
        vocab = load_vocab()
        for section in (
            "papertypes",
            "results",
            "consultation_roles",
            "meeting_scope",
            "party_variants",
            "file_tags",
        ):
            assert section in vocab, section

    def test_party_variants_have_comilations(self):
        vocab = load_vocab()
        for party, spec in vocab["party_variants"].items():
            assert spec.get("variants"), party
            assert "era" in spec, party


class TestResolveMapping:
    def test_papertype_case_insensitive(self):
        vocab = load_vocab()
        key, entry = resolve_mapping("ÄNDERUNGSANTRAG zur A1", vocab["papertypes"])
        assert key == "aenderungsantrag"
        assert entry["class"] == "modification"

    def test_hyphen_variant(self):
        vocab = load_vocab()
        key, _ = resolve_mapping("Änderungs-/Ergänzungsantrag", vocab["papertypes"])
        assert key == "aenderungsantrag"

    def test_result_wording_variants(self):
        vocab = load_vocab()
        # docs example: "enstimmig zugestimmt" (typo in source must not match, but
        # canonical spellings must) and "Kenntnisnahme"
        assert resolve_mapping("einstimmig zugestimmt", vocab["results"])[0] == "zugestimmt"
        assert resolve_mapping("mehrheitlich abgelehnt", vocab["results"])[0] == "abgelehnt"
        assert resolve_mapping("Kenntnisnahme", vocab["results"])[0] == "kenntnisnahme"

    def test_no_match_returns_none(self):
        vocab = load_vocab()
        key, entry = resolve_mapping("ganz anderer Text", vocab["papertypes"])
        assert key is None and entry is None

    def test_none_and_empty(self):
        vocab = load_vocab()
        assert resolve_mapping(None, vocab["results"]) == (None, None)
        assert resolve_mapping("", vocab["results"]) == (None, None)

    def test_consultation_role_decisive_flag(self):
        vocab = load_vocab()
        key, entry = resolve_mapping("Entscheidung", vocab["consultation_roles"])
        assert key == "entscheidung" and entry["decisive"] is True
        key, entry = resolve_mapping("Vorberatung", vocab["consultation_roles"])
        assert entry["decisive"] is False
