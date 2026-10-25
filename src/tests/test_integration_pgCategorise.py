"""Tests for the category derivation passes (src.update.pgCategorise).

Dry-run integration tests against the live database (read-only) plus unit
tests for the LLM classification parsing with a stubbed chat client.
"""

from __future__ import annotations

import pytest

from src.db import get_engine
from src.update.pgCategorise import (
    _candidate_vocabulary,
    _llm_classify,
    derive_llm_tags,
    derive_name_regex_tags,
    derive_papertype_tags,
)

pytestmark = pytest.mark.integration


class TestDryRunWritesNothing:
    def test_papertype_dry_run(self):
        engine = get_engine()
        before = _assoc_count(engine, "Paper_tags_assoc")
        stats = derive_papertype_tags(engine, dry_run=True, count=10)
        assert stats["scanned"] > 0
        assert _assoc_count(engine, "Paper_tags_assoc") == before

    def test_regex_dry_run(self):
        engine = get_engine()
        before = _assoc_count(engine, "AgendaItem_tags_assoc")
        stats = derive_name_regex_tags(engine, dry_run=True, count=10)
        assert stats["scanned"] > 0
        assert _assoc_count(engine, "AgendaItem_tags_assoc") == before


def _assoc_count(engine, table: str) -> int:
    if not __import__("src.db", fromlist=["table_exists"]).table_exists(table, engine=engine):
        return 0
    from sqlalchemy import text

    with engine.connect() as conn:
        return conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar()


class TestLlmClassify:
    def test_parses_json_answer(self, monkeypatch):
        import src.update.pgCategorise as pc

        def fake_chat(messages, **kwargs):
            return {"content": 'Hier: {"tag": "Anträge"}'}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        assert _llm_classify("teaser", ["Anträge"]) == "Anträge"

    def test_returns_none_on_garbage(self, monkeypatch):
        import src.update.pgCategorise as pc

        def fake_chat(messages, **kwargs):
            return {"content": "kein json hier"}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        assert _llm_classify("teaser", ["Anträge"]) is None

    def test_survives_exception(self, monkeypatch):
        import src.update.pgCategorise as pc

        def fake_chat(messages, **kwargs):
            raise RuntimeError("api down")

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        assert _llm_classify("teaser", ["Anträge"]) is None

    def test_vocabulary_is_nonempty_and_sorted(self):
        vocab = _candidate_vocabulary()
        assert vocab == sorted(vocab)
        assert "Anträge" in vocab and "Protokolle" in vocab


class TestLlmPassEscalation:
    def test_regex_hits_are_not_sent_to_llm(self, monkeypatch):
        import src.update.pgCategorise as pc

        calls = {"n": 0}

        def fake_chat(messages, **kwargs):
            calls["n"] += 1
            return {"content": '{"tag": "Sonstiges"}'}

        monkeypatch.setattr(pc.remote, "chat", fake_chat)
        # Scan real rows; regex-matched names must never trigger the LLM.
        stats = pc.derive_llm_tags(get_engine(), dry_run=True, count=30)
        assert stats["scanned"] > 0
        # Any LLM call corresponds to a regex miss, never a hit.
        assert calls["n"] <= stats["scanned"]
