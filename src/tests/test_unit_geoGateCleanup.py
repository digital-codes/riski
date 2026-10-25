"""Unit tests for the pgGeoGateCleanup orchestration — regex pre-filter
vs LLM fallback, per-document batching (change: geo-gating)."""

import pytest

from src.pgGeoGateCleanup import (
    _address_regex,
    regex_all_addresses,
)

pytestmark = pytest.mark.unit

CONTENT_ADDRESS_ONLY = (
    "Antrag Nr. 170 DIE LINKE\nDie Linke, Hebelstraße 13, 76133 Karlsruhe\n"
    "Herrn Oberbürgermeister …"
)
CONTENT_MIXED = (
    "Verkauf des Gebäudes in der Hebelstraße 13 an das Studierendenwerk.\n"
    "Absender: Fraktion X, Hebelstraße 13, 76133 Karlsruhe"
)
CONTENT_ADDRESS_KAISER = (
    "Institut der Universität Karlsruhe (TH) Kaiserstraße 12 76131 Karlsruhe "
    "als sachverständigen Einwohner zu berufen."
)
CONTENT_ADDRESS_MUEHLBURG = (
    "Ortschaftsrat Mühlburg, Bahnhofstraße 5, 76137 Karlsruhe"
)


def test_regex_fires_on_pure_address_document():
    assert regex_all_addresses(CONTENT_ADDRESS_ONLY, "Hebelstraße")


def test_regex_spares_mixed_document():
    # body mention without PLZ next to an address line → LLM decides
    assert not regex_all_addresses(CONTENT_MIXED, "Hebelstraße")


def test_regex_fires_with_newline_separated_plz():
    content = "Die Linke\nHebelstraße 13\n76133 Karlsruhe\n\nAntrag auf …"
    assert regex_all_addresses(content, "Hebelstraße")


def test_regex_spares_district_without_house_number():
    assert not regex_all_addresses(CONTENT_ADDRESS_MUEHLBURG, "Mühlburg")


def test_regex_variants():
    assert regex_all_addresses("Kaiserstraße 12-14, 76133 Karlsruhe", "Kaiserstraße")
    assert regex_all_addresses("Hebelstraße 13a\n76133 Karlsruhe", "Hebelstraße")
    assert not regex_all_addresses("Hebelstraße liegt im Westen", "Hebelstraße")


def test_address_regex_anchored_to_name():
    # the pattern must start at the name — a PLZ elsewhere must not match
    assert _address_regex("Hebelstraße").match(
        "Hebelstraße 21, 76133 Karlsruhe", 0)
    assert _address_regex("Hebelstraße").match(
        "xx Hebelstraße 21, 76133 Karlsruhe", 3)


def test_doc_level_llm_skip_logic():
    """Docs whose every mention the regex classified as address-shaped get
    no entry in the LLM batch — mirrors the by_doc construction in run()."""
    rows = [
        {"file_sid": 1, "entity_name": "Hebelstraße", "content": CONTENT_ADDRESS_ONLY},
        {"file_sid": 1, "entity_name": "Mühlburg", "content": CONTENT_MIXED},
        {"file_sid": 2, "entity_name": "Kaiserstraße", "content": CONTENT_ADDRESS_KAISER},
        {"file_sid": 3, "entity_name": "Hebelstraße", "content": CONTENT_ADDRESS_ONLY},
    ]
    by_doc = {}
    for r in rows:
        if regex_all_addresses(r["content"] or "", r["entity_name"]):
            continue
        by_doc.setdefault(r["file_sid"], []).append(r)
    # doc 1 survives (Mühlburg is mixed), doc 2 fully regex-filtered (no LLM),
    # doc 3 fully regex-filtered (no LLM)
    assert set(by_doc) == {1}
    assert [m["entity_name"] for m in by_doc[1]] == ["Mühlburg"]


def test_mixed_doc_single_llm_call_for_all_survivors():
    """Multiple survivors of one document land in ONE LLM batch."""
    rows = [
        {"file_sid": 1, "entity_name": "Mühlburg", "content": CONTENT_MIXED},
        {"file_sid": 1, "entity_name": "Kaiserstraße", "content": CONTENT_MIXED},
        {"file_sid": 1, "entity_name": "Hebelstraße", "content": CONTENT_ADDRESS_ONLY},
    ]
    by_doc = {}
    for r in rows:
        if regex_all_addresses(r["content"] or "", r["entity_name"]):
            continue
        by_doc.setdefault(r["file_sid"], []).append(r)
    assert len(by_doc[1]) == 2  # Hebelstraße filtered, the rest batched once
