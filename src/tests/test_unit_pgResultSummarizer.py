"""Unit tests for the result summarizer (src.pgResultSummarizer)."""

from __future__ import annotations

import pytest

import src.pgResultSummarizer as pc
from src.pgResultSummarizer import ResultSummarizer


class FakeSession:
    """Minimal stand-in: File (teaser, content, downloadurl) by oparlKey."""

    def __init__(self, contents: dict):
        self._contents = contents  # oparlKey -> (teaser, content[, downloadurl])

    def execute(self, stmt, params=None):
        key = params["k"]

        class R:
            def first(self):
                c = self._c
                if c is None or (c[0] is None and c[1] is None and len(c) < 3):
                    return None if c is None else [c[0], c[1], None]
                if len(c) < 3:
                    return [c[0], c[1], None]
                return list(c)

        r = R()
        r._c = self._contents.get(key, (None, None))
        return r


def make_result(n: int = 2, query: str = "Was macht die Digitalstrategie?") -> dict:
    return {
        "query": query,
        "top_files": [
            {"oparlKey": str(100 + i), "name": f"File {i}", "fileName": f"f{i}.pdf"}
            for i in range(n)
        ],
    }


@pytest.fixture()
def summarizer(monkeypatch):
    monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", "http://llm")
    monkeypatch.setattr(pc.remote, "CHAT_MODEL", "test-model")
    monkeypatch.setattr(pc.remote, "chat", lambda *a, **k: {"content": "Zusammenfassung.", "endpoint": "http://llm"})
    return ResultSummarizer(FakeSession({}))


@pytest.fixture()
def result():
    return make_result(2)


class TestQueryGuidedPrompt:
    def test_prompt_carries_query(self, summarizer, result, monkeypatch):
        seen = {}

        def fake_chat(messages, **kwargs):
            seen["system"], seen["user"] = messages[0]["content"], messages[1]["content"]
            return {"content": "S."}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        summarizer.summarize(result)
        assert "Was macht die Digitalstrategie?" in seen["user"]
        assert seen["user"].startswith("Frage: ")
        # guided instruction: summarize in view of the question
        assert "in Hinblick auf die" in seen["system"]
        assert "gestellte" in seen["system"]
        # relevance filtering: evaluate each document, refuse off-topic ones
        assert "Beurteile" in seen["system"] and "nicht relevant" in seen["system"]
        assert "Nicht berücksichtigte Dokumente" in seen["system"]

    def test_refusal_note_stripped_from_summary(self, summarizer, result, monkeypatch):
        """The model's trailing note is parsed (summary_refused) but then
        stripped — the verdicts live in our own document list, and a
        separate note would be redundant/contradictory (user finding)."""

        def fake_chat(messages, **kwargs):
            return {"content": "Zusammenfassung.\n\n**Nicht berücksichtigte Dokumente:**\n- Datei 1: File 0"}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        summarizer.summarize(result)
        assert "**Nicht berücksichtigte Dokumente:**" not in result["summary"]
        assert result["summary"].startswith("**Frage:** ")
        # still parsed before stripping: map gating + pre-exclusion work
        assert result["summary_refused"] == [{"oparlKey": "100", "name": "File 0"}]
        assert result["summary_excluded"] == ["100"]
        # the verdict lives in the structured metadata (frontend renders it)
        files = {f["oparlKey"]: f for f in result["summary_files"]}
        assert files["100"]["excluded"] is True

    def test_summary_states_the_query(self, summarizer, result):
        summarizer.summarize(result)
        assert result["summary"].startswith("**Frage:** Was macht die Digitalstrategie?")

    def test_summary_without_query_has_no_header(self, summarizer, monkeypatch):
        res = make_result(1, query="")
        summarizer.summarize(res)
        assert not res["summary"].startswith("**Frage:**")

    def test_generic_fallback_without_query(self, summarizer, monkeypatch):
        seen = {}

        def fake_chat(messages, **kwargs):
            seen["user"] = messages[1]["content"]
            return {"content": "S."}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        res = make_result(1)
        res["query"] = ""
        summarizer.summarize(res)
        assert not seen["user"].startswith("Frage:")


class TestFullCoverage:
    def test_all_files_included_no_truncation(self, summarizer, monkeypatch):
        seen = {}

        def fake_chat(messages, **kwargs):
            seen["user"] = messages[1]["content"]
            return {"content": "S."}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        res = make_result(10)
        summarizer.summarize(res)
        for i in range(10):
            assert f"Datei {i + 1}:" in seen["user"]
            assert f"File {i}" in seen["user"]
        assert "Datei 11:" not in seen["user"]

    def test_missing_text_marked(self, summarizer, result, monkeypatch):
        seen = {}

        def fake_chat(messages, **kwargs):
            seen["user"] = messages[1]["content"]
            return {"content": "S."}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        summarizer._session = FakeSession({"100": ("Teaser", "Inhalt")})  # 101 empty
        summarizer.summarize(result)
        assert "Not available" in seen["user"]


class TestTeaserLayer:
    def test_teaser_preferred_over_content(self, result, monkeypatch):
        monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", "http://llm")
        monkeypatch.setattr(pc.remote, "CHAT_MODEL", "m")
        seen = {}

        def fake_chat(messages, **kwargs):
            seen["user"] = messages[1]["content"]
            return {"content": "S."}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        session = FakeSession({"100": ("Teaser A", "Inhalt A")})
        ResultSummarizer(session).summarize(result)
        assert "Teaser A" in seen["user"]
        assert "Inhalt A" not in seen["user"]

    def test_content_fallback_when_no_teaser(self, result, monkeypatch):
        monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", "http://llm")
        monkeypatch.setattr(pc.remote, "CHAT_MODEL", "m")
        seen = {}

        def fake_chat(messages, **kwargs):
            seen["user"] = messages[1]["content"]
            return {"content": "S."}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        session = FakeSession({"100": (None, "Voller Inhalt")})
        ResultSummarizer(session).summarize(result)
        assert "Voller Inhalt" in seen["user"]

    def test_per_file_cap(self, result, monkeypatch):
        monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", "http://llm")
        monkeypatch.setattr(pc.remote, "CHAT_MODEL", "m")
        seen = {}

        def fake_chat(messages, **kwargs):
            seen["user"] = messages[1]["content"]
            return {"content": "S."}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        long_teaser = "X" * 500
        session = FakeSession({"100": (long_teaser, None)})
        s = ResultSummarizer(session, content_chars=10)
        s.summarize(result)
        assert long_teaser not in seen["user"]


class TestSkipConditions:
    def test_no_top_files_noop(self, summarizer):
        res = {"query": "x", "top_files": []}
        summarizer.summarize(res)
        assert "summary" not in res

    def test_model_not_configured_skips(self, result, monkeypatch):
        monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", None)
        res = ResultSummarizer(FakeSession({})).summarize(result)
        assert "summary" not in res

    def test_existing_summary_skipped_unless_forced(self, summarizer, result):
        result["summary"] = "vorhanden"
        summarizer.summarize(result)
        assert result["summary"] == "vorhanden"
        summarizer.summarize(result, force=True)
        assert result["summary"].startswith("**Frage:** ")
        assert "Zusammenfassung." in result["summary"]

    def test_dummy_response_ignored(self, result, monkeypatch):
        monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", "http://llm")
        monkeypatch.setattr(pc.remote, "CHAT_MODEL", "m")
        monkeypatch.setattr(pc.remote, "chat", lambda *a, **k: {"content": "[dummy response]"})
        ResultSummarizer(FakeSession({})).summarize(result)
        assert "summary" not in result


class TestProvenanceFooter:
    def test_footer_with_tokens_and_impact(self, result, monkeypatch):
        monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", "http://llm:8000/v1")
        monkeypatch.setattr(pc.remote, "CHAT_MODEL", "mistral")

        def fake_chat(messages, **kwargs):
            return {
                "content": "Zusammenfassung.",
                "model": "served-model-name",
                "usage": {"prompt_tokens": 1200, "completion_tokens": 300, "total_tokens": 1500},
                "impact": {
                    "inferenceTime": {"total": 9200, "unit": "ms"},
                    "energy": {"total": 4500.0, "unit": "Wms"},
                    "emissions": {"total": 87.5, "unit": "ugCO2e"},
                },
            }

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        summarizer = ResultSummarizer(FakeSession({"100": ("Teaser", "Inhalt")}))
        summarizer.summarize(result)
        s = result["summary"]
        # footer comes after the summary content and contains provenance
        assert s.find("Zusammenfassung.") < s.find("---")
        assert "`served-model-name`" in s           # model from response
        assert "`http://llm:8000/v1`" in s          # endpoint
        assert "Tokens: 1200 / 300 (Prompt / Antwort, 1500 gesamt)" in s
        assert "Inferenzzeit: 9200 ms" in s
        assert "Energie: 4500 Wms" in s
        assert "Emissionen: 87.5 µgCO₂e" in s

    def test_footer_model_and_endpoint_even_without_usage(self, summarizer, result, monkeypatch):
        """Model + endpoint are always stated; usage/impact only when present."""
        monkeypatch.setattr(pc.remote, "chat", lambda *a, **k: {"content": "Zusammenfassung.", "endpoint": "http://llm"})
        summarizer.summarize(result)
        s = result["summary"]
        assert "`test-model`" in s and "`http://llm`" in s
        assert "Tokens:" not in s and "Energie" not in s

    def test_footer_absent_when_nothing_available(self, result, monkeypatch):
        """With no model/url anywhere, no footer is emitted (direct _footer check)."""
        monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", None)
        monkeypatch.setattr(pc.remote, "CHAT_MODEL", None)
        summarizer = ResultSummarizer(FakeSession({}), model=None)
        assert summarizer._footer({"content": "Zusammenfassung."}) == ""

    def test_footer_present_in_stored_summary_for_pdf(self, result, monkeypatch):
        """The footer is part of result["summary"] — the SummaryCard (and
        thus the PDF export) renders it automatically."""
        monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", "http://llm")
        monkeypatch.setattr(pc.remote, "CHAT_MODEL", "m")

        def fake_chat(messages, **kwargs):
            return {"content": "Zusammenfassung.",
                    "usage": {"prompt_tokens": 50, "completion_tokens": 49, "total_tokens": 99}}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        s = ResultSummarizer(FakeSession({"100": ("Teaser", "Inhalt")}))
        s.summarize(result)
        assert "Tokens: 50 / 49 (Prompt / Antwort, 99 gesamt)" in result["summary"]


class TestSearchAndSummarizeWrapper:
    def test_wrapper_runs_both_steps(self, monkeypatch):
        import src.pgTimeline as tl

        called = {"search": 0, "summary": 0}

        def fake_search(session, query, **kwargs):
            called["search"] += 1
            assert kwargs.get("top_k") == 3
            return {"query": query, "top_files": [{"oparlKey": "1", "name": "n", "fileName": "f"}]}

        class FakeSum:
            def __init__(self, session):
                pass

            def summarize(self, result, force=False):
                called["summary"] += 1
                result["summary"] = "S"

        monkeypatch.setattr(tl, "search_and_build_timeline", fake_search)
        monkeypatch.setattr("src.pgResultSummarizer.ResultSummarizer", FakeSum)
        res = tl.search_and_summarize(None, "q", top_k=3)
        assert called == {"search": 1, "summary": 1}
        assert res["summary"] == "S"

    def test_wrapper_can_skip_summary(self, monkeypatch):
        import src.pgTimeline as tl

        monkeypatch.setattr(
            tl, "search_and_build_timeline",
            lambda s, q, **k: {"query": q, "top_files": [{"oparlKey": "1", "name": "n", "fileName": "f"}]},
        )
        res = tl.search_and_summarize(None, "q", summarize=False)
        assert "summary" not in res

class TestRefusalParsing:
    """The verdict is machine-parseable: refused Datei numbers resolve to
    the fetched files (map gating consumes this)."""

    def test_parse_refused_documents(self, result, monkeypatch):
        monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", "http://llm")
        monkeypatch.setattr(pc.remote, "CHAT_MODEL", "m")

        def fake_chat(messages, **kwargs):
            return {"content": (
                "Zusammenfassung der relevanten Dokumente.\n\n"
                "**Nicht berücksichtigte Dokumente:**\n"
                "- Datei 2: File B\n"
            )}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        summarizer = ResultSummarizer(FakeSession({}))
        summarizer.summarize(result)
        assert result["summary_refused"] == [{"oparlKey": "101", "name": "File 1"}]

    def test_all_considered_no_refusals(self, summarizer, result, monkeypatch):
        monkeypatch.setattr(pc.remote, "chat", lambda *a, **k: {"content": (
            "Zusammenfassung.\n\n**Nicht berücksichtigte Dokumente:**\n"
            "Alle Dokumente wurden berücksichtigt.")})
        summarizer.summarize(result)
        assert result["summary_refused"] == []

    def test_no_note_no_refusals(self, summarizer, result, monkeypatch):
        monkeypatch.setattr(pc.remote, "chat", lambda *a, **k: {"content": "Zusammenfassung."})
        summarizer.summarize(result)
        assert result["summary_refused"] == []

    def test_out_of_range_indices_ignored(self, result, monkeypatch):
        monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", "http://llm")
        monkeypatch.setattr(pc.remote, "CHAT_MODEL", "m")

        def fake_chat(messages, **kwargs):
            return {"content": (
                "Zusammenfassung.\n\n**Nicht berücksichtigte Dokumente:**\n"
                "- Datei 99: Phantom\n- Datei 1: File A\n")}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        ResultSummarizer(FakeSession({})).summarize(result)
        assert result["summary_refused"] == [{"oparlKey": "100", "name": "File 0"}]


class TestFullContentRefinement:
    """Change: summary-refine-file-control — context mode + exclusions."""

    @pytest.fixture()
    def rich_session(self):
        contents = {
            "100": ("Teaser 100", "Volltext 100", "https://dl/f0.pdf"),
            "101": ("Teaser 101", "Volltext 101", "https://dl/f1.pdf"),
        }
        return FakeSession(contents)

    def test_full_content_preferred_on_refine(self, rich_session, result, monkeypatch):
        captured = {}

        def fake_chat(messages, **kwargs):
            captured["prompt"] = messages[1]["content"]
            return {"content": "Zusammenfassung.", "endpoint": "http://llm"}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        ResultSummarizer(rich_session).summarize(result, use_full_content=True)
        assert "Volltext 100" in captured["prompt"]
        assert "Teaser 100" not in captured["prompt"]
        assert "Dokumente (Volltext):" in captured["prompt"]

    def test_teaser_default_names_layer(self, rich_session, result, monkeypatch):
        captured = {}

        def fake_chat(messages, **kwargs):
            captured["prompt"] = messages[1]["content"]
            return {"content": "Zusammenfassung."}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        ResultSummarizer(rich_session).summarize(result)
        assert "Teaser 100" in captured["prompt"]
        assert "Dokumente (Teaser):" in captured["prompt"]

    def test_full_content_capped(self, rich_session, result, monkeypatch):
        long_content = "X" * 50_000
        session = FakeSession({"100": ("Teaser", long_content, None),
                               "101": ("Teaser 101", None, None)})
        captured = {}

        def fake_chat(messages, **kwargs):
            captured["prompt"] = messages[1]["content"]
            return {"content": "Zusammenfassung."}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        s = ResultSummarizer(session)
        s.summarize(result, use_full_content=True)
        cap = pc._MAX_CONTENT_CHARS * pc._FULL_CONTENT_FACTOR
        assert ("X" * cap) in captured["prompt"]
        assert ("X" * (cap + 1)) not in captured["prompt"]

    def test_exclusion_filters_working_copy(self, rich_session, monkeypatch):
        result = make_result(2)
        captured = {}

        def fake_chat(messages, **kwargs):
            captured["prompt"] = messages[1]["content"]
            return {"content": "Zusammenfassung."}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        ResultSummarizer(rich_session).summarize(result, exclude={"101"})
        assert "File 1" not in captured["prompt"]
        assert "File 0" in captured["prompt"]
        # the original top_files stay untouched
        assert len(result["top_files"]) == 2
        assert result["summary_excluded"] == ["101"]

    def test_summary_stays_clean_of_document_list(self, rich_session, result, monkeypatch):
        """The stored summary contains body + provenance footer only — the
        document list is rendered by the frontend from summary_files
        (single list, no duplication — user finding)."""
        monkeypatch.setattr(pc.remote, "chat",
                            lambda *a, **k: {"content": "Zusammenfassung.", "endpoint": "http://llm"})
        ResultSummarizer(rich_session).summarize(result)
        summary = result["summary"]
        assert "**Dokumente:**" not in summary
        assert summary.find("Zusammenfassung.") < summary.find("Endpunkt:")
        # the structured metadata still carries name, URL and verdict
        assert result["summary_files"][0]["downloadUrl"] == "https://dl/f0.pdf"
        assert result["summary_files"][0]["excluded"] is False

    def test_summary_files_metadata_refused_auto_excluded(self, rich_session, result, monkeypatch):
        def fake_chat(messages, **kwargs):
            return {"content": (
                "Zusammenfassung.\n\n**Nicht berücksichtigte Dokumente:**\n"
                "- Datei 2: File 1\n")}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        ResultSummarizer(rich_session).summarize(result)
        files = {f["oparlKey"]: f for f in result["summary_files"]}
        assert files["101"]["refused"] is True and files["101"]["excluded"] is True
        assert files["100"]["refused"] is False and files["100"]["excluded"] is False
        assert files["100"]["downloadUrl"] == "https://dl/f0.pdf"

    def test_all_excluded_no_model_call(self, rich_session, result, monkeypatch):
        calls = []
        monkeypatch.setattr(pc.remote, "chat", lambda *a, **k: calls.append(1) or {})
        ResultSummarizer(rich_session).summarize(result, exclude={"100", "101"})
        assert calls == []
        assert result["summary_files"][0]["excluded"] is True

    def test_refine_uses_full_selection_no_selection_prompt(self, rich_session, result, monkeypatch):
        """Refinement = no document selection: the refine prompt reads ALL
        provided content (the document set comes from the initial selection
        or the user's toggles), and the effective 'not considered' set is
        exactly the user-excluded files — a stray legacy note in the model
        output never changes the set (user finding: refine shrank the
        considered set)."""
        captured = {}

        def fake_chat(messages, **kwargs):
            captured["system"] = messages[0]["content"]
            captured["user"] = messages[1]["content"]
            # stray legacy-style note in the output — must be ignored
            return {"content": (
                "Übersicht.\n\n**Nicht berücksichtigte Dokumente:**\n"
                "- Datei 2: File 1\n")}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        ResultSummarizer(rich_session).summarize(result, use_full_content=True)
        # the refine system prompt forbids selection and demands a complete
        # overview with document references
        assert "KEINE eigene Auswahl" in captured["system"]
        assert "VOLLSTÄNDIGE Übersicht" in captured["system"]
        assert "900" in captured["system"]  # refine word budget
        # both files' full content entered the prompt
        assert "Volltext 100" in captured["user"] and "Volltext 101" in captured["user"]
        # the stray note does not change the set; nothing is excluded
        assert result["summary_refused"] == []
        assert result["summary_excluded"] == []
        files = {f["oparlKey"]: f for f in result["summary_files"]}
        assert files["101"]["excluded"] is False and files["101"]["refused"] is False
        assert result["summary_refined"] is True

    def test_prompt_numbering_follows_full_list(self, rich_session, result, monkeypatch):
        """Files keep their FULL-list position in the prompt even when
        other files are excluded — the model's "(Datei N)" references must
        match the document list the user sees (user finding: after
        excluding file 1 the text still referenced 'Datei 1', meaning
        something else)."""
        captured = {}

        def fake_chat(messages, **kwargs):
            captured["prompt"] = messages[1]["content"]
            return {"content": "Zusammenfassung."}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        # exclude the FIRST file (full-list position 1): the remaining file
        # keeps its position number 2
        ResultSummarizer(rich_session).summarize(result, exclude={"100"})
        assert "Datei 2: File 1 (f1.pdf)" in captured["prompt"]
        assert "Datei 1:" not in captured["prompt"]

    def test_teaser_run_refusals_pre_exclude(self, rich_session, result, monkeypatch):
        """On the automatic pass, refused files start excluded (so the
        refine button uses the current considered set)."""
        def fake_chat(messages, **kwargs):
            return {"content": (
                "Zusammenfassung.\n\n**Nicht berücksichtigte Dokumente:**\n"
                "- Datei 2: File 1\n")}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        ResultSummarizer(rich_session).summarize(result)
        assert result["summary_excluded"] == ["101"]
        files = {f["oparlKey"]: f for f in result["summary_files"]}
        assert files["101"]["excluded"] is True

    def test_refined_mode_marker(self, rich_session, result, monkeypatch):
        monkeypatch.setattr(pc.remote, "chat", lambda *a, **k: {"content": "Z."})
        ResultSummarizer(rich_session).summarize(result)
        assert result["summary_refined"] is False
        ResultSummarizer(rich_session).summarize(result, force=True, use_full_content=True)
        assert result["summary_refined"] is True
