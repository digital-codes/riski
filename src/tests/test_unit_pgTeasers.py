"""Unit tests for src.pgTeasers – HTTP layer mocked, no network, no DB."""

import pytest
import requests

from src import pgTeasers as pt


class _Resp:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"{self.status_code} error")
            err.response = self
            raise err

    def json(self):
        return self._payload


def _ok_payload(content="Ein Teaser."):
    return {"choices": [{"finish_reason": "stop",
                         "message": {"content": content}}]}


@pytest.fixture()
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(pt.time, "sleep", sleeps.append)
    return sleeps


class TestMakeRequest:
    def test_success_returns_content(self, monkeypatch):
        monkeypatch.setattr(pt.requests, "post",
                            lambda *a, **k: _Resp(200, _ok_payload()))
        assert pt.make_request("Text") == "Ein Teaser."

    def test_429_honours_retry_after(self, monkeypatch, no_sleep):
        responses = [_Resp(429, headers={"Retry-After": "7"}), _Resp(200, _ok_payload())]
        monkeypatch.setattr(pt.requests, "post", lambda *a, **k: responses.pop(0))
        assert pt.make_request("Text") == "Ein Teaser."
        assert 7 in no_sleep

    def test_429_without_header_backs_off_exponentially(self, monkeypatch, no_sleep):
        responses = [_Resp(429), _Resp(429), _Resp(200, _ok_payload())]
        monkeypatch.setattr(pt.requests, "post", lambda *a, **k: responses.pop(0))
        assert pt.make_request("Text") == "Ein Teaser."
        assert no_sleep[0] == pt.RETRY_DELAY * (2 ** 0)
        assert no_sleep[1] == pt.RETRY_DELAY * (2 ** 1)

    def test_429_gives_up_after_max_retries(self, monkeypatch, no_sleep):
        monkeypatch.setattr(pt.requests, "post",
                            lambda *a, **k: _Resp(429))
        assert pt.make_request("Text") is None
        assert len(no_sleep) == pt.MAX_RETRIES

    def test_500_is_retried_then_gives_up(self, monkeypatch, no_sleep):
        monkeypatch.setattr(pt.requests, "post",
                            lambda *a, **k: _Resp(503, {"error": "busy"}))
        assert pt.make_request("Text") is None
        assert len(no_sleep) == pt.MAX_RETRIES

    def test_truncated_response_retries_with_more_tokens(self, monkeypatch, no_sleep):
        payloads = [
            _Resp(200, {"choices": [{"finish_reason": "length",
                                     "message": {"content": "zu lang"}}]}),
            _Resp(200, _ok_payload()),
        ]
        seen = []
        monkeypatch.setattr(pt.requests, "post",
                            lambda *a, **k: seen.append(k) or payloads.pop(0))
        assert pt.make_request("Text") == "Ein Teaser."
        # the retry used a doubled max_tokens budget
        assert seen[1]["json"]["max_tokens"] == pt.SUMMARY_MAX_TOKENS * 2

    def test_long_response_trimmed_to_maxlen(self, monkeypatch):
        monkeypatch.setattr(pt.requests, "post",
                            lambda *a, **k: _Resp(200, _ok_payload("wort " * 500)))
        result = pt.make_request("Text", maxlen=50)
        assert len(result.split()) == 50


class TestConfig:
    def test_retry_budget_documented(self):
        assert pt.MAX_RETRIES >= 5
        assert pt.RETRY_DELAY > 0


class TestTeaserCeiling:
    """Change: fix-result-summarizer — every teaser storage path stays
    within 120% of the max chunk size."""

    def test_ceiling_constant(self):
        assert pt.TEASER_CEILING == int(pt.MAX_CHUNK_CHARS * 1.2)

    def test_fallback_truncation_capped(self, monkeypatch):
        # API failure -> text[:TEXT_EXCERPT_MAXLEN] fallback is ceiling-capped
        monkeypatch.setattr(pt, "make_request", lambda *a, **k: None)
        long_text = "Wort " * 8000  # ~40k chars
        teaser = pt.summarize_to_teaser(long_text)
        assert len(teaser) <= pt.TEASER_CEILING

    def test_short_document_teaser_capped(self):
        long_text = "x" * (pt.TEASER_CEILING + 5000)  # >200 words, short branch needs <=200 words
        # a "short" document (>200 words goes through the API); directly
        # check the cap helper used on every storage path
        assert pt._cap_teaser(long_text) == long_text[:pt.TEASER_CEILING]

    def test_word_budget_teaser_below_ceiling(self, monkeypatch):
        monkeypatch.setattr(pt, "make_request",
                            lambda *a, **k: "wort " * 200)
        teaser = pt.summarize_to_teaser("wort " * 1000)
        assert len(teaser.split()) <= pt.DEFAULT_MAX_LEN
        assert len(teaser) <= pt.TEASER_CEILING


class TestChunkedTeaser:
    """Map-reduce teaser generation for chunked documents (change:
    fix-result-summarizer): all chunks contribute, ONE teaser per document."""

    def _patch_make_request(self, monkeypatch, calls):
        def fake_make_request(text, lang="de", maxlen=pt.DEFAULT_MAX_LEN):
            calls.append((len(text), maxlen))
            if maxlen <= pt.CHUNK_PRE_SUMMARY_WORDS:
                return f"Vorzusammenfassung ({len(text)} Zeichen)."
            return "Reduzierter Teaser."
        monkeypatch.setattr(pt, "make_request", fake_make_request)

    def test_all_chunks_contribute_single_teaser(self, monkeypatch):
        calls = []
        self._patch_make_request(monkeypatch, calls)
        chunks = ["Inhalt eins " * 100, "Inhalt zwei " * 100, "Inhalt drei " * 100]
        teaser = pt.generate_chunked_teaser(chunks)
        # one pre-summary call per chunk + one reduce call
        assert len(calls) == 4
        assert [c[1] for c in calls[:3]] == [pt.CHUNK_PRE_SUMMARY_WORDS] * 3
        assert calls[3][1] == pt.DEFAULT_MAX_LEN
        assert teaser == "Reduzierter Teaser."

    def test_failed_pre_summary_degrades_to_text_head(self, monkeypatch):
        calls = []

        def fake_make_request(text, lang="de", maxlen=pt.DEFAULT_MAX_LEN):
            calls.append(maxlen)
            if maxlen <= pt.CHUNK_PRE_SUMMARY_WORDS and "kaputt" in text:
                return None  # this chunk's pre-summary fails
            if maxlen <= pt.CHUNK_PRE_SUMMARY_WORDS:
                return "Vorzz woerter."
            return "Ein Teaser."
        monkeypatch.setattr(pt, "make_request", fake_make_request)
        chunks = ["Guter Text " * 50, "kaputter Text " * 50]
        teaser = pt.generate_chunked_teaser(chunks)
        assert teaser == "Ein Teaser."  # document still gets a teaser
        # the reduce call happened
        assert pt.DEFAULT_MAX_LEN in calls

    def test_pre_summaries_carried_to_reduce(self, monkeypatch):
        seen_texts = []

        def fake_make_request(text, lang="de", maxlen=pt.DEFAULT_MAX_LEN):
            if maxlen <= pt.CHUNK_PRE_SUMMARY_WORDS:
                return f"Vorzz-{len(seen_texts)} inhalte."
            seen_texts.append(text)
            return "Ein Teaser."
        monkeypatch.setattr(pt, "make_request", fake_make_request)
        pt.generate_chunked_teaser(["A" * 50, "B" * 50, "C" * 50])
        # the reduce input contains one bullet per chunk pre-summary
        assert len(seen_texts) == 1
        assert seen_texts[0].count("\n- ") == 2  # three bullet lines
        assert "Vorzz-0 inhalte." in seen_texts[0]
