"""Tests for hybrid multi-signal recall (src.pgHybridSearch)."""

from __future__ import annotations

import pytest

from src.pgHybridSearch import (
    FilterError,
    parse_filters,
    rrf_fuse,
)


class TestRrfFuse:
    def test_single_list_scores_descend_by_rank(self):
        scores = rrf_fuse([["a", "b", "c"]])
        assert scores["a"] > scores["b"] > scores["c"]
        assert scores["a"] == pytest.approx(1 / 61)

    def test_item_in_both_lists_beats_single(self):
        scores = rrf_fuse([["a", "b"], ["b", "c"]])
        assert scores["b"] > scores["a"]
        assert scores["b"] == pytest.approx(1 / 61 + 1 / 62)

    def test_empty_lists(self):
        assert rrf_fuse([]) == {}
        assert rrf_fuse([[], []]) == {}

    def test_ordering_is_by_score(self):
        scores = rrf_fuse([["x", "y"], ["y", "z"]])
        keys = list(scores)
        assert keys[0] == "y"

    def test_custom_k(self):
        scores = rrf_fuse([["a"]], k=1)
        assert scores["a"] == pytest.approx(0.5)


class TestParseFilters:
    def test_none_passthrough(self):
        assert parse_filters(None) == []

    def test_valid_filters(self):
        out = parse_filters([
            {"facet": "paperType", "op": "in", "values": ["Antrag", "Anfrage"]},
            {"facet": "year", "op": "range", "from": "2021", "to": "2022", "basis": "meeting"},
            {"facet": "authoritative", "op": "eq", "value": True},
            {"facet": "tag", "scheme": "district", "op": "in", "values": ["Innenstadt-Ost"]},
        ])
        assert len(out) == 4
        assert out[0]["values"] == ["Antrag", "Anfrage"]
        assert out[1]["basis"] == "meeting"

    def test_unknown_facet_raises(self):
        with pytest.raises(FilterError, match="Unknown facet"):
            parse_filters([{"facet": "mood", "op": "in", "values": ["x"]}])

    def test_unknown_op_raises(self):
        with pytest.raises(FilterError, match="Unknown filter op"):
            parse_filters([{"facet": "paperType", "op": "contains", "values": ["x"]}])

    def test_in_requires_nonempty_values(self):
        with pytest.raises(FilterError, match="non-empty"):
            parse_filters([{"facet": "paperType", "op": "in", "values": []}])

    def test_range_only_for_year(self):
        with pytest.raises(FilterError, match="only supported for facet 'year'"):
            parse_filters([{"facet": "paperType", "op": "range", "from": "1", "to": "2"}])

    def test_year_range_requires_bounds(self):
        with pytest.raises(FilterError, match="requires 'from'"):
            parse_filters([{"facet": "year", "op": "range"}])

    def test_year_basis_validated(self):
        with pytest.raises(FilterError, match="basis"):
            parse_filters([{"facet": "year", "op": "range", "from": "2020", "basis": "decade"}])

    def test_tag_requires_scheme(self):
        with pytest.raises(FilterError, match="scheme"):
            parse_filters([{"facet": "tag", "op": "in", "values": ["x"]}])

    def test_non_dict_rejected(self):
        with pytest.raises(FilterError, match="must be an object"):
            parse_filters(["paperType"])


class TestHybridCandidatesIntegration:
    """Live read-only smoke tests (no embedding API required)."""

    @pytest.fixture(scope="class")
    def conn(self):
        from src.db import get_engine

        engine = get_engine()
        with engine.connect() as c:
            yield c

    def test_lexical_recall_finds_exact_name(self, conn):
        from src.pgHybridSearch import hybrid_candidates

        fake = [0.01] * 1024  # name_vecs tables absent; lexical does the work
        hyb = hybrid_candidates(conn, "Digitalstrategie", fake, top_k=10)
        ids = {m["id"] for m in hyb["matched_entities"]}
        assert "Paper_46236" in ids  # the Digitalstrategie paper
        assert hyb["file_candidates"]

    def test_papertype_filter_constrains_papers(self, conn):
        from src.pgHybridSearch import hybrid_candidates
        from sqlalchemy import text

        hyb = hybrid_candidates(
            conn, "Digitalstrategie", [0.01] * 1024, top_k=50,
            filters=[{"facet": "paperType", "op": "in", "values": ["Beschlussvorlage"]}],
        )
        paper_keys = [m["oparlKey"] for m in hyb["matched_entities"] if m["type"] == "Paper"]
        assert paper_keys, "expected lexical paper hits under the filter"
        rows = conn.execute(
            text('SELECT "oparlKey" FROM "Paper" WHERE "oparlKey" IN :keys AND papertype <> \'Beschlussvorlage\''),
            {"keys": tuple(paper_keys)},
        ).fetchall()
        assert not rows

    def test_signals_can_be_disabled(self, conn):
        from src.pgHybridSearch import hybrid_candidates

        hyb = hybrid_candidates(
            conn, "Digitalstrategie", [0.01] * 1024, top_k=10,
            signals={"lexical": False, "name_vectors": False, "content_vectors": False},
        )
        assert hyb["matched_entities"] == []
        assert hyb["file_candidates"] == []

    def test_facets_listing(self, conn):
        from src.pgHybridSearch import facets

        f = facets(conn)
        assert "Beschlussvorlage" in f["paperType"]
        assert isinstance(f["years"], list) and f["years"]
        assert f["result"]
        assert f["tags"].get("document-type", 0) > 0
