"""Unit tests for the instruction prompt registry (change:
centralize-llm-instruction-prompts) — catalog loading, env override, and
error behaviour. All offline, no network."""

import json

import pytest

from src import remote

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _restore_catalog():
    """Every test leaves the module catalog as it imported it."""
    yield
    remote.reload_prompts()


def test_catalog_loads_at_import():
    assert remote.has_prompt("teaser-summarize")
    assert remote.has_prompt("doc-classify-teaser")
    assert remote.has_prompt("kg-contradiction-question")
    assert len(remote._PROMPTS) >= 25


def test_get_prompt_returns_verbatim_text():
    text = remote.get_prompt("doc-classify-teaser")
    assert text == (
        "Du klassifizierst kurze Dokument-Zusammenfassungen (Teaser) aus einem "
        "Ratsinformationssystem. Antworte NUR mit einem JSON-Objekt der Form "
        '{"tag": "<Kategorie>"}. Wähle die Kategorie aus der vorgegebenen Liste, '
        "wenn eine passt; sonst wähle ein prägnantes deutsches Schlagwort (1-3 Wörter)."
    )


def test_env_override_is_honoured(tmp_path, monkeypatch):
    catalog = tmp_path / "prompts.json"
    catalog.write_text(
        json.dumps({"version": 1, "prompts": {"only-mine": {"text": "TEST"}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("RISKI_PROMPTS_CONFIG", str(catalog))
    remote.reload_prompts()
    assert not remote.has_prompt("teaser-summarize")
    assert remote.get_prompt("only-mine") == "TEST"


def test_missing_catalog_logs_error_and_is_empty(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("RISKI_PROMPTS_CONFIG", str(tmp_path / "absent.json"))
    with caplog.at_level("ERROR"):
        remote.reload_prompts()
    assert remote._PROMPTS == {}
    assert "not found" in caplog.text
    with pytest.raises(KeyError):
        remote.get_prompt("teaser-summarize")


def test_broken_catalog_logs_error_and_is_empty(tmp_path, monkeypatch, caplog):
    catalog = tmp_path / "broken.json"
    catalog.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("RISKI_PROMPTS_CONFIG", str(catalog))
    with caplog.at_level("ERROR"):
        remote.reload_prompts()
    assert remote._PROMPTS == {}
    assert "unreadable" in caplog.text


def test_unknown_prompt_id_logs_error_and_raises(caplog):
    with caplog.at_level("ERROR"), pytest.raises(KeyError):
        remote.get_prompt("definitely-not-a-prompt-id")
    assert "Unknown prompt id" in caplog.text


def test_entry_without_text_is_dropped(tmp_path, monkeypatch, caplog):
    catalog = tmp_path / "prompts.json"
    catalog.write_text(
        json.dumps({"version": 1, "prompts": {
            "good": {"text": "ok"},
            "empty": {"description": "no text"},
        }}),
        encoding="utf-8",
    )
    monkeypatch.setenv("RISKI_PROMPTS_CONFIG", str(catalog))
    with caplog.at_level("ERROR"):
        remote.reload_prompts()
    assert remote.has_prompt("good")
    assert not remote.has_prompt("empty")
    assert "no text" in caplog.text
    assert "dropped" in caplog.text
