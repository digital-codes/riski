"""Unit tests for src.pgTeasers – LLM layer mocked via src.remote, no
network, no DB (change: teasers-cli-parity)."""

import pytest

from src import pgTeasers as pt
from src import remote


def _chat_result(content):
    return {"content": content}


@pytest.fixture()
def no_llm(monkeypatch):
    """Patch remote.chat as seen from pgTeasers; records calls."""
    calls = []

    def fake_chat(messages, model=None, temperature=0.0, thinking=False):
        calls.append({"messages": messages, "model": model,
                      "temperature": temperature})
        return _chat_result("Ein Teaser.")

    monkeypatch.setattr(pt.remote, "chat", fake_chat)
    return calls


class TestMakeRequest:
    """make_request delegates to remote.chat and maps failures to None."""

    def test_success_returns_content(self, no_llm):
        assert pt.make_request("Text") == "Ein Teaser."

    def test_summary_model_is_default(self, no_llm):
        pt.make_request("Text")
        # model=None -> remote.chat uses the configured summary model
        assert no_llm[0]["model"] is None

    def test_model_override_passthrough(self, no_llm):
        pt.make_request("Text", model="mein-modell")
        assert no_llm[0]["model"] == "mein-modell"

    def test_empty_content_is_failure(self, monkeypatch):
        monkeypatch.setattr(pt.remote, "chat",
                            lambda *a, **k: _chat_result(""))
        assert pt.make_request("Text") is None

    def test_dummy_response_is_failure(self, monkeypatch):
        monkeypatch.setattr(pt.remote, "chat",
                            lambda *a, **k: _chat_result(pt._DUMMY_CONTENT))
        assert pt.make_request("Text") is None

    def test_lang_in_prompt(self, no_llm):
        pt.make_request("Text", lang="en", maxlen=50)
        system = no_llm[0]["messages"][0]["content"]
        assert "English" in system
        assert "50" in system

    def test_long_input_truncated_to_excerpt(self, no_llm):
        pt.make_request("x" * (pt.TEXT_EXCERPT_MAXLEN + 1000))
        user = no_llm[0]["messages"][1]["content"]
        assert len(user) <= pt.TEXT_EXCERPT_MAXLEN + len("Document text: ")

    def test_long_response_trimmed_to_maxlen(self, monkeypatch):
        monkeypatch.setattr(pt.remote, "chat",
                            lambda *a, **k: _chat_result("wort " * 500))
        result = pt.make_request("Text", maxlen=50)
        assert result is not None
        assert len(result.split()) == 50


class TestConfig:
    """Change: teasers-cli-parity — infrastructure moved to shared layers."""

    def test_no_script_local_retry_constants(self):
        # retry/backoff/429 handling lives in src.remote now
        assert not hasattr(pt, "MAX_RETRIES")
        assert not hasattr(pt, "RETRY_DELAY")
        assert not hasattr(pt, "API_TIMEOUT")

    def test_no_script_local_llm_envs(self):
        import inspect as _inspect
        src = _inspect.getsource(pt)
        assert "RISKI_LLM" not in src
        assert "LLM_URL" not in src.replace("LLM_URL``/``LLM_MDL", "")
        # no module-level endpoint/model constants of its own
        assert not hasattr(pt, "LLM_URL")
        assert not hasattr(pt, "LLM_MDL")

    def test_uses_shared_layers(self):
        src = __import__("inspect").getsource(pt)
        assert "from src.db import get_engine" in src
        assert "from src import remote" in src


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
        long_text = "x" * (pt.TEASER_CEILING + 5000)
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
        def fake_make_request(text, lang="de", maxlen=pt.DEFAULT_MAX_LEN, model=None):
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

    def test_model_flows_to_calls(self, monkeypatch):
        models = []

        def fake_make_request(text, lang="de", maxlen=pt.DEFAULT_MAX_LEN, model=None):
            models.append(model)
            if maxlen <= pt.CHUNK_PRE_SUMMARY_WORDS:
                return "Vorzz woerter."
            return "Ein Teaser."
        monkeypatch.setattr(pt, "make_request", fake_make_request)
        pt.generate_chunked_teaser(["A" * 100, "B" * 100], model="lauf-modell")
        assert models == ["lauf-modell"] * 3

    def test_failed_pre_summary_degrades_to_text_head(self, monkeypatch):
        calls = []

        def fake_make_request(text, lang="de", maxlen=pt.DEFAULT_MAX_LEN, model=None):
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

    def test_failed_reduce_falls_back_to_pre_summaries(self, monkeypatch):
        def fake_make_request(text, lang="de", maxlen=pt.DEFAULT_MAX_LEN, model=None):
            if maxlen <= pt.CHUNK_PRE_SUMMARY_WORDS:
                return "Vorzz woerter."
            return None  # the reduce call fails
        monkeypatch.setattr(pt, "make_request", fake_make_request)
        teaser = pt.generate_chunked_teaser(["A" * 50, "B" * 50])
        # concatenated pre-summaries serve as the teaser (ceiling-capped),
        # never an empty result
        assert teaser
        assert "Vorzz" in teaser
        assert len(teaser) <= pt.TEASER_CEILING

    def test_pre_summaries_carried_to_reduce(self, monkeypatch):
        seen_texts = []

        def fake_make_request(text, lang="de", maxlen=pt.DEFAULT_MAX_LEN, model=None):
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
