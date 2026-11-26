"""Tests for the PII guard (change: summary-pii-guard)."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

from src.pgResultSummarizer import (  # noqa: E402
    _PII_VIOLATION_MARKER,
    _redact_text,
    find_pii_violations,
    pii_guard,
    person_names,
)


class TestDetection:
    def test_full_name_bare_surname_detected(self, monkeypatch):
        monkeypatch.setattr(
            "src.pgResultSummarizer.person_names",
            lambda: ["Martina Heynen", "Heynen", "Fahringer", "Bauer"])  # the real loader ALSO carries surnames (title-stripped)
        text = ("Die Mitglieder sind: Dr. Heynen\n"
                "  - Fahringer\n"
                "Die Fraktion (Datei 5) stimmt zu.")
        viol = find_pii_violations(text)
        assert any("Heynen" in v for v in viol)
        assert any("Fahringer" in v for v in viol)

    def test_clean_text_no_matches(self, monkeypatch):
        monkeypatch.setattr(
            "src.pgResultSummarizer.person_names",
            lambda: ["Martina Heynen", "Heynen", "Fahringer"])
        # no name substrings (word-boundary guard: 'Heinrich' ≠ Heynen)
        assert find_pii_violations(
            "Die Fraktion (Datei 5) und das Amt regeln den Antrag (Datei 7).") == []

    def test_common_word_still_flagged_over_redaction_side(self, monkeypatch):
        monkeypatch.setattr("src.pgResultSummarizer.person_names",
                            lambda: ["Bauer"])
        # PII-first: a surname that doubles as a noun IS a violation (design decision 2)
        assert find_pii_violations("Der Bauer stellt den Antrag (Datei 3).")

    def test_empty(self, monkeypatch):
        monkeypatch.setattr("src.pgResultSummarizer.person_names", lambda: [])
        assert find_pii_violations("x") == []


class TestFallbackRedaction:
    def test_inline_occurrences_replaced(self, monkeypatch):
        monkeypatch.setattr("src.pgResultSummarizer.person_names",
                            lambda: ["Fahringer"])
        out = _redact_text("Fahringer und die Fraktion (Datei 3).", ["Fahringer"])
        assert "Fahringer" not in out
        assert "(Datei 3)" in out

    def test_bare_name_list_collapses(self, monkeypatch):
        monkeypatch.setattr(
            "src.pgResultSummarizer.person_names",
            lambda: ["Fahringer", "Dujmovic", "Heynen"])
        text = "Die Mitglieder:\n    Fahringer\n    Dujmovic\n    Dr. Heynen"
        out = _redact_text(text, ["Fahringer", "Dujmovic", "Heynen"])
        assert "Fahringer" not in out and "Heynen" not in out
        assert "(Name entfernt)" in out


class TestGuardFlow:
    def _dup(self):
        import src.pgResultSummarizer as mod
        return mod

    def test_clean_summary_no_repair_call(self, monkeypatch):
        mod = self._dup()
        monkeypatch.setattr(mod, "find_pii_violations", lambda s: [])
        called = {"n": 0}
        monkeypatch.setattr(mod.remote, "chat",
                            lambda *a, **k: called.__setitem__("n", called["n"] + 1) or {})
        assert pii_guard("Eine PII-freie Zusammenfassung (Datei 2).") == \
            "Eine PII-freie Zusammenfassung (Datei 2)."
        assert called["n"] == 0

    def test_leak_redacted_deterministically_no_llm(self, monkeypatch):
        # change: summary-pii-guard (architectural decision) — the repair
        # LLM call is DROPPED: output violations are redacted
        # deterministically, the guarantee does not depend on an LLM
        mod = self._dup()
        monkeypatch.setattr(mod, "person_names", lambda: ["Fahringer"])
        called = {"n": 0}
        monkeypatch.setattr(mod.remote, "chat",
                            lambda *a, **k: called.__setitem__("n", called["n"] + 1) or {})
        out = pii_guard("Fahringer (Datei 5).")
        assert called["n"] == 0, "no LLM call for the guard"
        assert "Fahringer" not in out
        assert "(Datei 5)" in out

    def test_leaky_fallback(self, monkeypatch):
        mod = self._dup()
        monkeypatch.setattr(mod, "person_names", lambda: ["Fahringer"])
        out = pii_guard("Fahringer trotzdem da.")
        assert "Fahringer" not in out
        assert "(Name entfernt)" in out

    def test_scrubber_consistent_pseudonyms(self, monkeypatch):
        mod = self._dup()
        monkeypatch.setattr(mod, "person_names",
                            lambda: ["Fahringer", "Dujmovic"])
        seats = []

        class Seat:
            def __init__(self):
                self._pii_pseudonyms = {}
                self._pii_counter = 0
        seat = Seat()
        ctx = ("Deutsch: Fahringer erläutert; Zuwachs durch Dujmovic; "
               "Fahringer erneut.")
        out = mod.scrub_names(ctx, seat)
        assert "Fahringer" not in out and "Dujmovic" not in out
        assert out.count("[PERSON_1]") == 2        # same person ⇒ same map
        assert "[PERSON_2]" in out
        # the second request scrubs the same names → same pseudonyms
        out2 = mod.scrub_names("Fahringer meint Dujmovic.", seat)
        assert out2 == "[PERSON_1] meint [PERSON_2]."

    def test_prompt_never_carries_names_live(self, monkeypatch):
        # with the live vocabulary: a context containing member names is
        # scrubbed before the prompt build; "wer ist alles bei den Grünen"
        # would copy nothing
        mod = self._dup()
        seat = type("Seat", (), {"_pii_pseudonyms": {}, "_pii_counter": 0})()
        names = mod.person_names()
        probe = " ".join(names[:2])
        out = mod.scrub_names(probe, seat)
        assert "PERSON_1" in out
        assert all(n not in out for n in names[:2])

    def test_prompt_ids_registered(self):
        from src.remote import has_prompt
        assert has_prompt("pii-repair-summary")
        assert has_prompt("pii-repair-summary-user")

    def test_person_vocabulary_cached_and_titles_excluded(self):
        names = person_names()
        assert names, "live Person vocabulary loads"
                # change: fix-stale-test-fixtures — assert titled FORMS absent
        assert not any(n.startswith(("Dr.", "Prof.", "Dipl.-Ing.", "Oberbürgermeister",
                                     "Bürgermeister", "Stadtrat")) for n in names)
