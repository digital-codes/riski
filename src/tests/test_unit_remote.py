"""Unit tests for src.remote – all HTTP mocked, no network access."""

import types

import pytest
import requests

from src import remote


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    monkeypatch.setenv("REMOTE_MAX_RETRIES", "3")
    monkeypatch.setenv("REMOTE_BASE_DELAY", "0")


def test_post_retries_transient_failure(monkeypatch):
    calls = {"n": 0}

    def flaky_post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.ConnectionError("boom")
        return _FakeResponse(200, {"ok": True})

    monkeypatch.setattr(remote.requests, "post", flaky_post)
    data = remote._post("embeddings", {})
    assert data == {"ok": True}
    assert calls["n"] == 2


def test_post_raises_after_exhausted_retries(monkeypatch):
    calls = {"n": 0}

    def always_fail(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        raise requests.ConnectionError("down")

    monkeypatch.setattr(remote.requests, "post", always_fail)
    with pytest.raises(RuntimeError):
        remote._post("embeddings", {})
    assert calls["n"] == 3  # REMOTE_MAX_RETRIES


def test_post_honours_retry_after(monkeypatch):
    sleeps = []

    monkeypatch.setattr(remote.time, "sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def rate_limited(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResponse(429, {}, headers={"Retry-After": "7"})
        return _FakeResponse(200, {"ok": True})

    monkeypatch.setattr(remote.requests, "post", rate_limited)
    data = remote._post("embeddings", {})
    assert data == {"ok": True}
    assert sleeps == [7.0]


def test_embed_raises_no_dummy_vector(monkeypatch):
    def fail(url, headers=None, json=None, timeout=None):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(remote.requests, "post", fail)
    with pytest.raises(RuntimeError):
        remote.embed("some text")


def test_chat_dummy_fallback_last_resort(monkeypatch):
    def fail(url, headers=None, json=None, timeout=None):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(remote.requests, "post", fail)
    result = remote.chat([{"role": "user", "content": "hi"}])
    assert result["content"] == "[dummy response]"


def test_chat_success(monkeypatch):
    def ok(url, headers=None, json=None, timeout=None):
        assert url.endswith("/chat/completions")
        return _FakeResponse(200, {
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        })

    monkeypatch.setattr(remote.requests, "post", ok)
    result = remote.chat([{"role": "user", "content": "hi"}])
    assert result == {
        "content": "hello",
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "total_tokens": 3,
        "model": None,
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        "impact": None,
        "endpoint": remote.CHAT_BASE_URL,
    }


def test_chat_thinking_param(monkeypatch):
    captured = {}

    def ok(url, headers=None, json=None, timeout=None):
        captured.update(json or {})
        return _FakeResponse(200, {"choices": [{"message": {"content": "x"}}]})

    monkeypatch.setattr(remote.requests, "post", ok)
    remote.chat([{"role": "user", "content": "hi"}], thinking=True)
    assert captured.get("think") is True


def test_embed_success_normalised(monkeypatch):
    import math

    def ok(url, headers=None, json=None, timeout=None):
        assert url.endswith("/embeddings")
        return _FakeResponse(200, {"data": [{"embedding": [3.0, 4.0]}]})

    monkeypatch.setattr(remote.requests, "post", ok)
    vec = remote.embed("text")
    assert math.isclose(float(vec[0]), 0.6, rel_tol=1e-6)
    assert math.isclose(float(vec[1]), 0.8, rel_tol=1e-6)


def test_ocr_success(monkeypatch):
    def ok(url, headers=None, data=None, timeout=None):
        assert url == remote.OCR_URL
        return _FakeResponse(200, {"pages": [{"markdown": "# hi"}]})

    monkeypatch.setattr(remote.requests, "post", ok)
    result = remote.ocr(b"%PDF-fake")
    assert result["pages"][0]["markdown"] == "# hi"


def test_ocr_retries_on_429(monkeypatch):
    calls = {"n": 0}
    sleeps = []
    monkeypatch.setattr(remote.time, "sleep", lambda s: sleeps.append(s))

    def rate_limited(url, headers=None, data=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResponse(429, headers={"Retry-After": "0"})
        return _FakeResponse(200, {"pages": []})

    monkeypatch.setattr(remote.requests, "post", rate_limited)
    result = remote.ocr(b"%PDF-fake")
    assert result == {"pages": []}
    assert calls["n"] == 2


def test_ocr_gives_up_after_max_retries(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(remote.time, "sleep", lambda s: None)

    def always_429(url, headers=None, data=None, timeout=None):
        calls["n"] += 1
        return _FakeResponse(429, headers={"Retry-After": "0"})

    monkeypatch.setattr(remote.requests, "post", always_429)
    with pytest.raises(requests.HTTPError):
        remote.ocr(b"%PDF-fake")
    assert calls["n"] == 8


def test_private_config_resolution(monkeypatch):
    fake = types.SimpleNamespace(EMB_URL="http://priv-embed", EMB_KEY="privkey")
    monkeypatch.setattr(remote, "_pr", fake)
    assert remote._get("EMB_URL", "EMBED_BASE_URL", "d") == "http://priv-embed"
    assert remote._get("EMB_KEY", "EMBED_API_KEY", "") == "privkey"
    # missing attribute falls back to env
    monkeypatch.setenv("EMBED_API_KEY", "envkey")
    assert remote._get("EMB_MISSING", "EMBED_API_KEY", "") == "envkey"


def test_env_over_default_when_no_private(monkeypatch):
    monkeypatch.setattr(remote, "_pr", None)
    monkeypatch.setenv("EMBED_API_KEY", "envkey")
    assert remote._get("EMB_KEY", "EMBED_API_KEY", "default") == "envkey"
    monkeypatch.delenv("EMBED_API_KEY")
    assert remote._get("EMB_KEY", "EMBED_API_KEY", "default") == "default"

pytestmark = pytest.mark.unit


class TestUrlComposition:
    def test_base_url_gets_path_appended(self, monkeypatch):
        captured = {}

        def ok(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            return _FakeResponse(200, {"data": [{"embedding": [1.0]}]})

        monkeypatch.setattr(remote, "EMBED_BASE_URL", "http://localhost:8085/v1")
        monkeypatch.setattr(remote.requests, "post", ok)
        remote._post("embeddings", {})
        assert captured["url"] == "http://localhost:8085/v1/embeddings"

    def test_full_endpoint_url_not_duplicated(self, monkeypatch):
        """private.py stores full URLs (e.g. .../openai/embeddings) — the
        path must not be appended a second time."""
        captured = {}

        def ok(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            return _FakeResponse(200, {"data": [{"embedding": [1.0]}]})

        monkeypatch.setattr(remote, "EMBED_BASE_URL", "https://api.deepinfra.com/v1/openai/embeddings")
        monkeypatch.setattr(remote.requests, "post", ok)
        remote._post("embeddings", {})
        assert captured["url"] == "https://api.deepinfra.com/v1/openai/embeddings"

    def test_chat_full_url_not_duplicated(self, monkeypatch):
        captured = {}

        def ok(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            return _FakeResponse(200, {"choices": [{"message": {"content": "x"}}]})

        monkeypatch.setattr(remote, "CHAT_BASE_URL", "https://api.example.com/v1/chat/completions")
        monkeypatch.setattr(remote.requests, "post", ok)
        remote.chat([{"role": "user", "content": "hi"}])
        assert captured["url"] == "https://api.example.com/v1/chat/completions"


class TestCoerceTemperature:
    def test_string_coerced(self):
        from src.remote import _coerce_temperature

        assert _coerce_temperature("0.2") == 0.2

    def test_float_passthrough(self):
        from src.remote import _coerce_temperature

        assert _coerce_temperature(0.1) == 0.1

    def test_garbage_falls_back_to_zero(self, caplog):
        from src.remote import _coerce_temperature

        assert _coerce_temperature("nonsense") == 0.0
        assert _coerce_temperature(None) == 0.0

    def test_chat_payload_coerces_string_temperature(self, monkeypatch):
        import src.remote as remote

        captured = {}
        monkeypatch.setattr(remote, "_post", lambda path, payload: captured.update(payload=payload) or remote._DUMMY_CHAT_RESPONSE)
        remote.chat([{"role": "user", "content": "x"}], temperature="0.4")
        assert captured["payload"]["temperature"] == 0.4
        assert isinstance(captured["payload"]["temperature"], float)


class TestChatCompat:
    def test_error_includes_response_body(self, monkeypatch):
        import requests as _rq

        import src.remote as remote

        class FakeResponse:
            status_code = 400
            text = '{"error":"\\"temperature\\" must be a float"}'
            headers = {}

            def raise_for_status(self):
                raise _rq.HTTPError("400", response=self)

        monkeypatch.setattr(remote.requests, "post", lambda *a, **k: FakeResponse())
        try:
            remote._post("chat/completions", {"model": "m", "messages": []})
            raised = False
        except RuntimeError as e:
            raised = True
            assert "must be a float" in str(e)  # endpoint error text surfaced
        assert raised

    def test_think_rejected_retries_without_it(self, monkeypatch):
        import requests as _rq

        import src.remote as remote

        payloads = []

        def flaky(path, payload):
            payloads.append(dict(payload))  # copy: chat pops "think" in place
            if "think" in payload:
                class FakeResponse:
                    status_code = 400
                    text = 'invalid field "think"'
                    headers = {}

                    def raise_for_status(self):
                        raise _rq.HTTPError("400", response=self)

                raise RuntimeError("400")

            return remote._DUMMY_CHAT_RESPONSE

        monkeypatch.setattr(remote, "_post", flaky)
        out = remote.chat([{"role": "user", "content": "x"}], thinking=True)
        assert len(payloads) == 2
        assert "think" in payloads[0] and "think" not in payloads[1]
        assert out["content"] == "[dummy response]"

    def test_temperature_never_string_in_payload(self, monkeypatch):
        import src.remote as remote

        captured = {}
        monkeypatch.setattr(remote, "_post", lambda path, payload: captured.update(p=payload) or remote._DUMMY_CHAT_RESPONSE)
        remote.chat([{"role": "user", "content": "x"}], temperature="0.3")
        assert isinstance(captured["p"]["temperature"], float)
