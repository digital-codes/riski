"""Unit tests for the result summarizer (src.pgResultSummarizer)."""

from __future__ import annotations

import pytest

import src.pgResultSummarizer as pc
from src.pgResultSummarizer import ResultSummarizer


class FakeSession:
    """Minimal stand-in: File (teaser, content) lookup by oparlKey."""

    def __init__(self, contents: dict):
        self._contents = contents  # oparlKey -> (teaser, content)

    def execute(self, stmt, params=None):
        key = params["k"]

        class R:
            def first(self):
                teaser, content = self._c
                return [teaser, content] if teaser or content else None

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

    def test_refusal_note_stored_verbatim(self, summarizer, result, monkeypatch):
        """The model's trailing note (refused documents) is part of the
        stored summary — not stripped or re-written."""

        def fake_chat(messages, **kwargs):
            return {"content": "Zusammenfassung.\n\n**Nicht berücksichtigte Dokumente:**\n- File 1"}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        summarizer.summarize(result)
        assert "**Nicht berücksichtigte Dokumente:**" in result["summary"]
        assert result["summary"].startswith("**Frage:** ")

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
