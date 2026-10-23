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
    monkeypatch.setattr(pc.remote, "chat", lambda *a, **k: {"content": "Zusammenfassung."})
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
        assert "gestellte Frage" in seen["system"]

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
        assert result["summary"] == "Zusammenfassung."

    def test_dummy_response_ignored(self, result, monkeypatch):
        monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", "http://llm")
        monkeypatch.setattr(pc.remote, "CHAT_MODEL", "m")
        monkeypatch.setattr(pc.remote, "chat", lambda *a, **k: {"content": "[dummy response]"})
        ResultSummarizer(FakeSession({})).summarize(result)
        assert "summary" not in result


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
