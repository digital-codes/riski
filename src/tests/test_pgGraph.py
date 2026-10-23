"""Tests for the OParl graph model (src.graphModel) and edge logging."""

from __future__ import annotations

import pytest

from src.graphModel import ADJACENCY, build_graph, node_id


class TestAdjacencyMap:
    def test_core_types_present(self):
        for t in ("Paper", "File", "Meeting", "AgendaItem", "Consultation", "Organization"):
            assert t in ADJACENCY

    def test_relations_have_required_fields(self):
        for src, rels in ADJACENCY.items():
            for rel in rels:
                assert rel["relation"] and rel["target"] and rel["via"]
                assert rel["target"] in ADJACENCY, f"{src}->{rel['target']} target missing from map"

    def test_expected_relations(self):
        paper_rels = {r["relation"] for r in ADJACENCY["Paper"]}
        assert {"auxiliaryFile", "mainFile", "consultation", "underDirectionOf"} <= paper_rels
        meeting_rels = {r["relation"] for r in ADJACENCY["Meeting"]}
        assert {"agendaItem", "auxiliaryFile", "organization"} <= meeting_rels


class TestNodeId:
    def test_format(self):
        assert node_id("Paper", "46236") == "Paper_46236"


class TestBuildGraph:
    @pytest.fixture()
    def fixture_data(self):
        related = {
            "Paper": [{
                "sid": 1, "id": 46236, "oparlKey": "46236",
                "oparlId": "https://example/papers/46236",
                "name": "Digitalstrategie", "date": "2021-12-27",
                "reference": "2021/1528", "paperType": "Beschlussvorlage",
            }],
            "Consultation": [{
                "sid": 2, "oparlKey": "9001", "oparlId": "https://example/c/9001",
                "role": "Entscheidung", "authoritative": True,
                "meetingSid": 3, "paperSid": 1,
            }],
            "Meeting": [{
                "sid": 3, "oparlKey": "700", "oparlId": "https://example/m/700",
                "name": "Gemeinderat", "start_date": "2022-01-17 10:00",
            }],
            "Organization": [],
            "AgendaItem": [],
            "AuxFile": [{
                "sid": 4, "oparlKey": "636459", "oparlId": "https://example/f/636459",
                "name": "Protokoll", "fileName": "00636459.pdf", "date": "2022-03-11",
            }],
        }
        edges = [
            {"source": "Paper_46236", "target": "File_635289", "relation": "auxiliaryFile", "via": "Paper__auxiliaryFile__File"},
            {"source": "Paper_46236", "target": "File_635289", "relation": "auxiliaryFile", "via": "Paper__auxiliaryFile__File"},  # dup
            {"source": "Paper_46236", "target": "Consultation_9001", "relation": "consultation", "via": "Paper__consultation__Consultation"},
            {"source": "Consultation_9001", "target": "Meeting_700", "relation": "meeting", "via": "FK:Consultation.meetingSid"},
            {"source": "Paper_46236", "target": "AuxFile_636459", "relation": "auxiliaryFile", "via": "Paper__auxiliaryFile__File"},
            {"source": "Paper_46236", "target": "File_MISSING", "relation": "auxiliaryFile", "via": "x"},  # dangling
        ]
        top_files = [{
            "sid": 9, "oparlKey": "635289", "oparlId": "https://example/f/635289",
            "name": "BV Digitalstrategie", "fileName": "00635289.pdf",
            "date": "2022-01-17", "distance": 0.324,
            "match": {"lexical": True, "content": 0.324},
        }]
        return related, edges, top_files

    def test_nodes_from_objects_and_files(self, fixture_data):
        related, edges, top_files = fixture_data
        g = build_graph(related, edges, top_files)
        ids = {n["id"] for n in g["nodes"]}
        assert {"Paper_46236", "Consultation_9001", "Meeting_700",
                "AuxFile_636459", "File_635289"} <= ids

    def test_seed_file_carries_match_provenance(self, fixture_data):
        related, edges, top_files = fixture_data
        g = build_graph(related, edges, top_files)
        node = next(n for n in g["nodes"] if n["id"] == "File_635289")
        assert node["attrs"]["distance"] == 0.324
        assert node["attrs"]["match"] == {"lexical": True, "content": 0.324}

    def test_node_attrs_are_type_specific(self, fixture_data):
        related, edges, top_files = fixture_data
        g = build_graph(related, edges, top_files)
        paper = next(n for n in g["nodes"] if n["id"] == "Paper_46236")
        assert paper["attrs"]["paperType"] == "Beschlussvorlage"
        assert paper["attrs"]["reference"] == "2021/1528"
        assert paper["date"] == "2021-12-27"
        consultation = next(n for n in g["nodes"] if n["id"] == "Consultation_9001")
        assert consultation["attrs"]["role"] == "Entscheidung"
        assert consultation["date"] is None  # consultations carry no date

    def test_duplicate_edges_deduped(self, fixture_data):
        related, edges, top_files = fixture_data
        g = build_graph(related, edges, top_files)
        keys = [(e["source"], e["target"], e["relation"]) for e in g["edges"]]
        assert len(keys) == len(set(keys))
        assert ("Paper_46236", "File_635289", "auxiliaryFile") in keys

    def test_dangling_edge_untouched_but_reportable(self, fixture_data):
        """build_graph serializes edges as-is; endpoint integrity is the
        traversal's job (verified by the integration test below)."""
        related, edges, top_files = fixture_data
        g = build_graph(related, edges, top_files)
        assert any(e["target"] == "File_MISSING" for e in g["edges"])


class TestFindRelatedObjectsEdgeLog:
    """Integration: edge log consistency on the live database (read-only)."""

    pytestmark = pytest.mark.integration

    def test_edges_reference_existing_nodes(self):
        from src.pgTimeline import find_related_objects, get_db_session

        session = get_db_session()
        try:
            # BV Digitalstrategie file (sid from earlier runs)
            file_sids = {"635289": 39201}
            related = find_related_objects(session, file_sids)
            edges = related.pop("edges")
            assert edges, "expected at least one logged edge"

            # every edge endpoint must exist as a node (via oparlKey per type)
            from src.graphModel import node_id
            node_keys = set()
            for t, objs in related.items():
                for o in objs:
                    if o.get("oparlKey") is not None:
                        node_keys.add(node_id(t, o["oparlKey"]))
            node_keys.add(node_id("File", "635289"))  # seed file

            dangling = [e for e in edges
                        if e["source"] not in node_keys or e["target"] not in node_keys]
            assert not dangling, f"dangling edges: {dangling[:3]}"

            # the known relation must be present
            triples = {(e["source"], e["relation"], e["target"]) for e in edges}
            assert ("File_635289", "auxiliaryFile", "Paper_46236") in triples or \
                   ("Paper_46236", "auxiliaryFile", "File_635289") in triples

            # edge relation values must appear in the adjacency map vocabulary
            valid_relations = {r["relation"] for rels in ADJACENCY.values() for r in rels}
            for e in edges:
                assert e["relation"] in valid_relations, e
        finally:
            session.close()
