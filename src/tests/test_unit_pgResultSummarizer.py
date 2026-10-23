"""Unit tests for the result summarizer (src.pgResultSummarizer)."""

from __future__ import annotations

import pytest

import src.pgResultSummarizer as pc
from src.pgResultSummarizer import ResultSummarizer


class FakeSession:
    """Minimal stand-in: File.content lookup by oparlKey."""

    def __init__(self, contents: dict):
        self._contents = contents

    def execute(self, stmt, params=None):
        key = params["k"]

        class R:
            def first(self):
                content = self._c
                return [content] if content else None

        r = R()
        r._c = self._contents.get(key)
        return r


@pytest.fixture()
def result():
    return {
        "query": "test",
        "top_files": [
            {"oparlKey": "111", "name": "File A", "fileName": "a.pdf"},
            {"oparlKey": "222", "name": "File B", "fileName": "b.pdf"},
        ],
    }


@pytest.fixture()
def summarizer(monkeypatch):
    monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", "http://llm")
    monkeypatch.setattr(pc.remote, "CHAT_MODEL", "test-model")
    monkeypatch.setattr(pc.remote, "chat", lambda *a, **k: {"content": "Zusammenfassung."})
    return ResultSummarizer(FakeSession({"111": "Inhalt A", "222": None}))


class TestSummarize:
    def test_sets_summary(self, summarizer, result):
        summarizer.summarize(result)
        assert result["summary"] == "Zusammenfassung."

    def test_skips_existing_summary_unless_forced(self, summarizer, result):
        result["summary"] = "vorhanden"
        summarizer.summarize(result)
        assert result["summary"] == "vorhanden"
        summarizer.summarize(result, force=True)
        assert result["summary"] == "Zusammenfassung."

    def test_no_top_files_noop(self, summarizer):
        res = {"query": "x", "top_files": []}
        summarizer.summarize(res)
        assert "summary" not in res

    def test_model_not_configured_skips(self, result, monkeypatch):
        monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", None)
        res = ResultSummarizer(FakeSession({})).summarize(result)
        assert "summary" not in res

    def test_dummy_response_ignored(self, result, monkeypatch):
        monkeypatch.setattr(pc.remote, "CHAT_BASE_URL", "http://llm")
        monkeypatch.setattr(pc.remote, "CHAT_MODEL", "m")
        monkeypatch.setattr(pc.remote, "chat", lambda *a, **k: {"content": "[dummy response]"})
        ResultSummarizer(FakeSession({})).summarize(result)
        assert "summary" not in result

    def test_content_truncated_and_missing_content_marked(self, summarizer, result, monkeypatch):
        seen = {}

        def fake_chat(messages, **kwargs):
            seen["prompt"] = messages[1]["content"]
            return {"content": "S."}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        summarizer.content_chars = 10
        summarizer.summarize(result)
        assert "Inhalt A" in seen["prompt"] and "..." in seen["prompt"]
        assert "Not available" in seen["prompt"]


class TestSearchAndSummarize:
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
