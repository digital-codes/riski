"""Unit tests for agenda-block answer expansion (change:
agenda-sibling-documents) — pure logic, no DB."""

from src.pgTimeline import (
    _block_prefix,
    _block_reference,
    expand_top_files_by_agenda_block,
)


def _fixture():
    ro = {
        "AgendaItem": [
            # Block 13 (meeting 7): 13.1 carries the seed hit
            {"oparlKey": "A1", "meetingSid": 7, "number": "13.1"},
            {"oparlKey": "A2", "meetingSid": 7, "number": "13.2"},
            {"oparlKey": "A3", "meetingSid": 7, "number": "13.3"},
            # unrelated TOPs of the same meeting
            {"oparlKey": "A4", "meetingSid": 7, "number": "5"},
            {"oparlKey": "A5", "meetingSid": 7, "number": "11"},
            # a name-matched seed TOP in another meeting (block 2)
            {"oparlKey": "A6", "meetingSid": 8, "number": "2.1", "_name_seed": True},
            # agenda item without number: stays a single object
            {"oparlKey": "A7", "meetingSid": 7, "number": None},
        ],
        "AuxFile": [
            {"sid": 2, "oparlKey": "S1", "name": "13.1 Anlage", "fileName": "s1.pdf"},
            {"sid": 3, "oparlKey": "S2", "name": "13.2 Dokument", "fileName": "s2.pdf"},
            {"sid": 4, "oparlKey": "S3", "name": "13.3 Protokoll", "fileName": "s3.pdf"},
            {"sid": 5, "oparlKey": "S4", "name": "TOP 5 Dokument", "fileName": "s4.pdf"},
            {"sid": 6, "oparlKey": "S5", "name": "TOP 11 Dokument", "fileName": "s5.pdf"},
            {"sid": 7, "oparlKey": "S6", "name": "2.1 Dokument", "fileName": "s6.pdf"},
            {"sid": 8, "oparlKey": "S7", "name": "Doku ohne Nummer", "fileName": "s7.pdf"},
        ],
    }
    edges = [
        {"source": "AgendaItem_A1", "target": "File_Hit", "relation": "auxiliaryFile"},
        {"source": "AgendaItem_A1", "target": "AuxFile_S1", "relation": "auxiliaryFile"},
        {"source": "AgendaItem_A2", "target": "AuxFile_S2", "relation": "auxiliaryFile"},
        {"source": "AgendaItem_A3", "target": "AuxFile_S3", "relation": "auxiliaryFile"},
        {"source": "AgendaItem_A4", "target": "AuxFile_S4", "relation": "auxiliaryFile"},
        {"source": "AgendaItem_A5", "target": "AuxFile_S5", "relation": "auxiliaryFile"},
        {"source": "AgendaItem_A6", "target": "AuxFile_S6", "relation": "auxiliaryFile"},
        {"source": "AgendaItem_A7", "target": "AuxFile_S7", "relation": "auxiliaryFile"},
    ]
    top_files = [{"oparlKey": "Hit", "sid": 1, "name": "Seed 13.1", "fileName": "hit.pdf"}]
    return ro, edges, top_files


class TestBlockPrefix:
    def test_subitem(self):
        assert _block_prefix("13.2") == 13

    def test_plain_number(self):
        assert _block_prefix("13") == 13

    def test_letter_suffix(self):
        assert _block_prefix("13.2a") == 13

    def test_missing_number(self):
        assert _block_prefix(None) is None
        assert _block_prefix("") is None

    def test_reference_label(self):
        assert _block_reference("13.2") == "TOP 13"
        assert _block_reference(None) is None


class TestBlockExpansion:
    def test_block_siblings_join_unrelated_excluded(self):
        ro, edges, top_files = _fixture()
        expanded = expand_top_files_by_agenda_block(
            ro, edges, top_files, query_terms=["thema"], text_provider=lambda k: "thema")
        keys = [f["oparlKey"] for f in expanded]
        # Block 13: seed + its sibling; unrelated TOPs (5, 11) excluded;
        # name-seed block 2: its document joins (name seeds always expand)
        assert keys == ["Hit", "S1", "S2", "S3", "S6"], keys
        via = {f["oparlKey"]: f.get("via") for f in expanded[1:]}
        assert via["S1"] == "TOP 13" and via["S2"] == "TOP 13" and via["S3"] == "TOP 13"
        assert via["S6"] == "TOP 2"

    def test_content_reference_filters_siblings(self):
        ro, edges, top_files = _fixture()
        # query tokens {knittelberg, 107}: only docs mentioning both pass
        texts = {"S1": "Bauantrag Am Knittelberg 107 — Anlage", "S2": "Bauantrag Am Knittelberg 107 — Plan",
                 "S3": "Protokoll ohne Bezug"}
        expanded = expand_top_files_by_agenda_block(
            ro, edges, top_files, query_terms=["knittelberg", "107"],
            text_provider=lambda k: texts.get(k, ""))
        keys = [f["oparlKey"] for f in expanded]
        assert keys == ["Hit", "S1", "S2"], keys  # S3 (no reference) filtered

    def test_no_query_terms_no_expansion(self):
        ro, edges, top_files = _fixture()
        expanded = expand_top_files_by_agenda_block(ro, edges, top_files)
        assert [f["oparlKey"] for f in expanded] == ["Hit"]

    def test_dedup_on_rerun(self):
        ro, edges, top_files = _fixture()
        once = expand_top_files_by_agenda_block(
            ro, edges, top_files, query_terms=["thema"], text_provider=lambda k: "thema")
        twice = expand_top_files_by_agenda_block(
            ro, edges, once, query_terms=["thema"], text_provider=lambda k: "thema")
        assert [f["oparlKey"] for f in twice] == [f["oparlKey"] for f in once]

    def test_appended_entries_shape(self):
        ro, edges, top_files = _fixture()
        expanded = expand_top_files_by_agenda_block(
            ro, edges, top_files, query_terms=["thema"], text_provider=lambda k: "thema")
        for f in expanded[1:]:
            assert f["distance"] is None and f["match"] is None
            assert {"sid", "oparlKey", "name", "fileName", "downloadurl",
                    "oparlId", "date", "via"} <= set(f.keys())
