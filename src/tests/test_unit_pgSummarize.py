"""Unit tests for src.pgSummarize – chat client is mocked."""

import pytest

from src import pgSummarize
from src.pgSummarize import request_summary, _strip_code_fence


@pytest.fixture()
def mock_chat(monkeypatch):
    calls = []

    def _chat(messages, model=None, temperature=0.0, thinking=False, **kwargs):
        calls.append({"messages": messages, "thinking": thinking, **kwargs})
        return {"content": "Zusammenfassung.", "total_tokens": 10}

    monkeypatch.setattr(pgSummarize, "chat", _chat)
    return calls


class TestRequestSummary:
    def test_returns_content(self, mock_chat):
        result = request_summary("Berichttext")
        assert result == "Zusammenfassung."

    def test_sends_system_prompt_and_report(self, mock_chat):
        request_summary("Berichttext")
        assert len(mock_chat) == 1
        messages = mock_chat[0]["messages"]
        assert messages[0]["role"] == "system"
        assert "Kommentator" in messages[0]["content"]
        assert messages[1] == {"role": "user", "content": "Berichttext"}
        # change: centralize-llm-instruction-prompts
        assert mock_chat[0]["prompt_id"] == "report-summarize"
        assert mock_chat[0]["call_id"] == "pgSummarize.request_summary.1"

    def test_prompt_is_module_level(self):
        # Regression: prompt used to be trapped inside _run_summarizer
        # change: centralize-llm-instruction-prompts — the instruction text
        # lives in the shared catalog (id: report-summarize)
        assert "Kommentator" in pgSummarize.get_prompt("report-summarize")
        assert "{report}" in pgSummarize.get_prompt("report-summarize")

    def test_thinking_flag_forwarded(self, mock_chat):
        request_summary("x", thinking=True)
        assert mock_chat[0]["thinking"] is True


class TestStripCodeFence:
    def test_removes_surrounding_fence(self):
        assert _strip_code_fence("```markdown\ntext\n```") == "text"

    def test_plain_text_unchanged(self):
        assert _strip_code_fence("plain") == "plain"

    def test_strips_whitespace(self):
        assert _strip_code_fence("  hi  ") == "hi"

pytestmark = pytest.mark.unit
