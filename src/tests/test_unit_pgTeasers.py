"""Unit tests for src.update.pgTeasers – HTTP layer mocked, no network, no DB."""

import pytest
import requests

from src.update import pgTeasers as pt


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
