"""Unit tests for the GeoGate (change: geo-gating) — stubbed chat client,
scratch SQLite tables; no live LLM/database required."""

import pytest
from sqlalchemy import create_engine, text

from src.geoGate import GeoGate

pytestmark = pytest.mark.unit


@pytest.fixture()
def gate():
    g = GeoGate(engine=create_engine("sqlite://"))
    return g


def test_parse_verdicts_valid_json(gate):
    raw = ('{"verdicts": ['
           '{"name": "Hebelstraße", "verdict": "boilerplate", "reason": "Adresse"},'
           '{"name": "Kaiserstraße", "verdict": "content", "reason": "Thema"}]}')
    v = GeoGate.parse_verdicts(raw, ["Hebelstraße", "Kaiserstraße"])
    assert v["Hebelstraße"] == {"verdict": "boilerplate", "reason": "Adresse"}
    assert v["Kaiserstraße"] == {"verdict": "content", "reason": "Thema"}


def test_parse_verdicts_code_fenced(gate):
    raw = '```json\n{"verdicts": [{"name": "Mühlburg", "verdict": "unsure", "reason": "?"}]}\n```'
    v = GeoGate.parse_verdicts(raw, ["Mühlburg"])
    assert v["Mühlburg"]["verdict"] == "unsure"


def test_parse_verdicts_garbage_degrades_permissive(gate):
    # parse failures must never hide links: everything stays 'unsure'
    for raw in ("", "kein JSON", '{"verdicts": [', "{nonsense}"):
        v = GeoGate.parse_verdicts(raw, ["A", "B"])
        assert v["A"]["verdict"] == "unsure" and v["B"]["verdict"] == "unsure"


def test_parse_verdicts_unknown_verdict_becomes_unsure(gate):
    raw = '{"verdicts": [{"name": "A", "verdict": "maybe", "reason": "x"}]}'
    v = GeoGate.parse_verdicts(raw, ["A"])
    assert v["A"]["verdict"] == "unsure"


def test_build_prompt_contains_content_names_and_context(gate):
    prompt = gate.build_prompt(
        "Antrag SPD_022", "Antrag",
        "Sehr geehrte…\nSPD, Hebelstraße 21\n\nBetreff: Kaiserstraße Umbau",
        [{"entity": "Hebelstraße", "context": "SPD, Hebelstraße 21"},
         {"entity": "Kaiserstraße", "context": "Betreff: Kaiserstraße"}])
    assert "Hebelstraße" in prompt and "Kaiserstraße" in prompt
    assert "boilerplate" in prompt and "content" in prompt
    # Karlsruhe-specific rule present (Haus der Fraktionen trap)
    assert "Hebelstraße" in prompt and "Haus der Fraktionen" in prompt


def test_gate_mentions_llm_failure_degrades_to_unsure(gate, monkeypatch):
    monkeypatch.setattr(gate, "_chat", lambda prompt: None)
    v = gate.gate_mentions("doc", "Antrag", "content text",
                           [{"entity": "A", "context": ""}])
    assert v["A"] == {"verdict": "unsure", "reason": "llm error"}


def test_gate_mentions_success(gate, monkeypatch):
    def fake_chat(prompt):
        return '{"verdicts": [{"name": "A", "verdict": "boilerplate", "reason": "r"}]}'

    monkeypatch.setattr(gate, "_chat", fake_chat)
    v = gate.gate_mentions("doc", "Antrag", "x", [{"entity": "A", "context": ""}])
    assert v["A"]["verdict"] == "boilerplate"


def test_gate_mentions_regex_address_prefilter_no_llm(gate, monkeypatch):
    """change: geo-gating, task 3.3 — a mention whose every occurrence sits
    in an address block is verdict boilerplate WITHOUT an LLM call."""
    calls = []

    def boom(prompt):
        calls.append(prompt)
        raise AssertionError("LLM must not be called for regex-classified mentions")

    monkeypatch.setattr(gate, "_chat", boom)
    content = ("Antrag Nr. 170 DIE LINKE\n"
               "Die Linke, Hebelstraße 13, 76133 Karlsruhe\n"
               "Herrn Oberbürgermeister …")
    v = gate.gate_mentions("doc", "Antrag", content,
                           [{"entity": "Hebelstraße", "context": ""}])
    assert v["Hebelstraße"] == {
        "verdict": "boilerplate",
        "reason": "regex: Adressblock (Hausnummer + PLZ Karlsruhe)",
    }
    assert calls == []


def test_gate_mentions_mixed_document_reaches_llm(gate, monkeypatch):
    """One non-address occurrence disqualifies the regex — the mention goes
    to the LLM, and the verdicts merge into one result dict."""
    captured = {}

    def fake_chat(prompt):
        captured["prompt"] = prompt
        return '{"verdicts": [{"name": "Hebelstraße", "verdict": "content", "reason": "Haupttext"}]}'

    monkeypatch.setattr(gate, "_chat", fake_chat)
    content = ("Verkauf des Gebäudes in der Hebelstraße 13 an das "
               "Studierendenwerk.\nAbsender: Fraktion X, Hebelstraße 13, "
               "76133 Karlsruhe")
    v = gate.gate_mentions("doc", "Antrag", content,
                           [{"entity": "Hebelstraße", "context": ""}])
    assert v["Hebelstraße"]["verdict"] == "content"
    assert "Hebelstraße" in captured["prompt"]


def test_gate_mentions_regex_and_llm_survivors_merge(gate, monkeypatch):
    """Regex-classified and LLM-classified mentions land in one result."""
    def fake_chat(prompt):
        mentions_section = prompt[prompt.find("Gefundene Namen"):]
        assert "Kaiserstraße" not in mentions_section  # regex-classified: not a mention
        assert "Mühlburg" in mentions_section
        return '{"verdicts": [{"name": "Mühlburg", "verdict": "content", "reason": "r"}]}'

    monkeypatch.setattr(gate, "_chat", fake_chat)
    content = ("Ortschaftsrat Mühlburg, Kaiserstraße 10, 76133 Karlsruhe\n"
               "hier wird über Mühlburg beraten")
    v = gate.gate_mentions("doc", "Antrag", content,
                           [{"entity": "Kaiserstraße", "context": ""},
                            {"entity": "Mühlburg", "context": ""}])
    assert v["Kaiserstraße"]["verdict"] == "boilerplate"
    assert v["Mühlburg"]["verdict"] == "content"


def test_gate_mentions_all_regex_no_llm_call(gate, monkeypatch):
    """When the regex classifies every mention, no LLM call happens."""
    def boom(prompt):
        raise AssertionError("no survivors → no LLM call")

    monkeypatch.setattr(gate, "_chat", boom)
    content = "Fraktion X, Hebelstraße 21, 76133 Karlsruhe"
    v = gate.gate_mentions("doc", "Antrag", content,
                           [{"entity": "Hebelstraße", "context": ""}])
    assert v["Hebelstraße"]["verdict"] == "boilerplate"


def test_write_verdicts_file_rows(gate):
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(text('CREATE TABLE "Streets_items_Files" '
                          '(id INTEGER PRIMARY KEY, street_id INT, file_id INT, '
                          'gate_status VARCHAR(16), gate_reason VARCHAR(255), '
                          'gated_at TIMESTAMP, gate_model VARCHAR(64))'))
        conn.execute(text('INSERT INTO "Streets_items_Files" (street_id, file_id) '
                          'VALUES (5, 9)'))
    g = GeoGate(engine=eng)
    g.write_verdicts("Streets_items_Files",
                     [{"entity_id": 5, "entity_name": "Hebelstraße", "file_id": 9}],
                     {"Hebelstraße": {"verdict": "boilerplate", "reason": "Adresse"}},
                     "street_id")
    with eng.connect() as conn:
        row = conn.execute(text('SELECT gate_status, gate_reason, gate_model '
                                'FROM "Streets_items_Files"')).first()
    assert row.gate_status == "boilerplate"
    assert row.gate_reason == "Adresse"
    assert row.gate_model  # recorded


def test_write_verdicts_item_rows(gate):
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(text('CREATE TABLE "Streets_items_AgendaItems" '
                          '(id INTEGER PRIMARY KEY, street_id INT, agendaitem_id INT, '
                          'gate_status VARCHAR(16), gate_reason VARCHAR(255), '
                          'gated_at TIMESTAMP, gate_model VARCHAR(64))'))
        conn.execute(text('INSERT INTO "Streets_items_AgendaItems" '
                          '(street_id, agendaitem_id) VALUES (7, 42)'))
    g = GeoGate(engine=eng)
    g.write_verdicts("Streets_items_AgendaItems",
                     [{"entity_id": 7, "entity_name": "Kaiserstraße", "item_sid": 42}],
                     {"Kaiserstraße": {"verdict": "content", "reason": "Thema"}},
                     "street_id")
    with eng.connect() as conn:
        status = conn.execute(text('SELECT gate_status FROM '
                                   '"Streets_items_AgendaItems"')).scalar()
    assert status == "content"


def test_permissive_principle_gate_never_raises(gate, monkeypatch):
    """Matching must survive any gate failure: _chat raising is caught and
    degrades to unsure."""
    def boom(prompt):
        raise RuntimeError("endpoint down")

    monkeypatch.setattr(gate, "_chat", boom)
    v = gate.gate_mentions("doc", "Antrag", "x", [{"entity": "A", "context": ""}])
    assert v["A"]["verdict"] == "unsure"
