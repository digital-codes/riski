"""Tests for hybrid multi-signal recall (src.pgHybridSearch)."""

from __future__ import annotations

import pytest

from src.pgHybridSearch import (
    FilterError,
    _strip_terms_py,
    load_stop_terms,
    parse_filters,
    rrf_fuse,
)


class TestStopTerms:
    def test_shipped_list_loads(self):
        # the committed config file has active Karlsruhe terms
        terms = load_stop_terms()
        assert "Karlsruhe" in terms and "Stadt" in terms

    def test_strip_removes_terms_word_wise(self):
        terms = ["Karlsruhe", "Karlsruher", "Stadt"]
        assert _strip_terms_py("Digitalstrategie der Stadt Karlsruhe", terms) == "Digitalstrategie der"
        assert _strip_terms_py("Karlsruher Pass", terms) == "Pass"

    def test_strip_collapses_whitespace(self):
        assert _strip_terms_py("Stadt   der  Karlsruhe", ["Karlsruhe", "Stadt"]) == "der"

    def test_strip_case_insensitive(self):
        assert _strip_terms_py("KARLSRUHE stuff", ["Karlsruhe"]) == "stuff"

    def test_empty_terms_noop(self):
        assert _strip_terms_py("Digitalstrategie", []) == "Digitalstrategie"


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

    def test_weights_scale_contribution(self):
        # change: fix-hybrid-search-ranking — weighted RRF
        scores = rrf_fuse([["a"], ["b"]], weights=[1.5, 1.0])
        assert scores["a"] == pytest.approx(1.5 / 61)
        assert scores["b"] == pytest.approx(1.0 / 61)

    def test_lexical_weight_bears_vector_only_hits(self):
        # a top-1 lexical hit outranks a top-5 content-vector hit when
        # config defaults (1.5 / 1.0) apply
        v5 = 1.0 / (60 + 5)
        l1 = 1.5 / (60 + 1)
        assert l1 > v5

    def test_weighted_ordering_lexical_above_vector_only(self):
        # "b" is a vector-only content hit; "a" only lexically at rank 2.
        # Unweighted: b wins (better rank). Weighted (1.5 lexical): a wins.
        unweighted = rrf_fuse([["y", "a"], ["b", "y"]])
        assert unweighted["b"] > unweighted["a"]
        weighted = rrf_fuse([["y", "a"], ["b", "y"]], weights=[1.5, 1.0])
        assert weighted["a"] > weighted["b"]

    def test_weight_count_must_match_lists(self):
        # parallel-list contract: exact length required (no silent 1.0 fill)
        with pytest.raises(ValueError):
            rrf_fuse([["a"], ["a"]], weights=[2.0])

    def test_weight_count_mismatch_raises(self):
        with pytest.raises(ValueError, match="weights"):
            rrf_fuse([["a"], ["b"]], weights=[1.0])

    def test_worked_example_from_docstring(self):
        scores = rrf_fuse([["a", "b"], ["b"]], weights=[1.5, 1.0])
        assert scores["a"] == pytest.approx(1.5 / 61)
        assert scores["b"] == pytest.approx(1.5 / 62 + 1.0 / 61)
        assert scores["b"] > scores["a"]


class TestSearchWeightsConfig:
    """Config resolution for the `search` section (env > file > defaults)."""

    @pytest.fixture(autouse=True)
    def _reset_cache(self, monkeypatch):
        from src.instanceConfig import clear_cache
        yield
        clear_cache()

    def _clear(self):
        from src.instanceConfig import clear_cache
        clear_cache()

    def test_defaults_present(self, monkeypatch):
        monkeypatch.delenv("RISKI_SEARCH__WEIGHTED_FUSION", raising=False)
        monkeypatch.delenv("RISKI_SEARCH__FUSION_WEIGHTS__LEX", raising=False)
        monkeypatch.delenv("RISKI_INSTANCE_CONFIG", raising=False)
        self._clear()
        from src.pgHybridSearch import _search_weights
        w = _search_weights()
        assert w == [1.5, 0.8, 1.2]  # live-tuned defaults (design, extension B)

    def test_env_override_wins(self, monkeypatch):
        monkeypatch.setenv("RISKI_SEARCH__FUSION_WEIGHTS__LEX", "2.25")
        monkeypatch.delenv("RISKI_INSTANCE_CONFIG", raising=False)
        self._clear()
        from src.pgHybridSearch import _search_weights
        assert _search_weights()[0] == 2.25

    def test_kill_switch_plain_rrf(self, monkeypatch):
        monkeypatch.setenv("RISKI_SEARCH__WEIGHTED_FUSION", "false")
        monkeypatch.delenv("RISKI_INSTANCE_CONFIG", raising=False)
        self._clear()
        from src.pgHybridSearch import _search_weights
        assert _search_weights() is None
        # with the switch off, fusion degenerates to plain RRF
        scores = rrf_fuse([["a"]], weights=None)
        assert scores["a"] == pytest.approx(1 / 61)

    def test_per_signal_default_from_config(self, monkeypatch):
        monkeypatch.delenv("RISKI_SEARCH__PER_SIGNAL", raising=False)
        monkeypatch.delenv("RISKI_INSTANCE_CONFIG", raising=False)
        self._clear()
        from src.instanceConfig import section
        assert int(section("search").get("per_signal", 50)) == 100
        assert int(section("search").get("rerank_max_candidates", 0)) == 60

    def test_per_signal_env_override(self, monkeypatch):
        monkeypatch.setenv("RISKI_SEARCH__PER_SIGNAL", "37")
        monkeypatch.delenv("RISKI_INSTANCE_CONFIG", raising=False)
        self._clear()
        from src.instanceConfig import section
        assert int(section("search").get("per_signal")) == 37


class TestNormCalibration:
    """Score-blend normalization (change: fix-hybrid-search-ranking)."""

    CAL = {"lex_floor": 0.4, "vec_near": 0.30, "vec_far": 0.90}

    def test_norm_lex_bounds(self):
        from src.pgHybridSearch import _norm_lex
        assert _norm_lex(0.4, self.CAL) == 0.0
        assert _norm_lex(1.0, self.CAL) == pytest.approx(1.0)
        assert _norm_lex(0.7, self.CAL) == pytest.approx((0.7 - 0.4) / 0.6)

    def test_norm_lex_below_floor_clamped(self):
        from src.pgHybridSearch import _norm_lex
        assert _norm_lex(0.1, self.CAL) == 0.0

    def test_norm_vec_bounds(self):
        from src.pgHybridSearch import _norm_vec
        assert _norm_vec(0.30, self.CAL) == pytest.approx(1.0)
        assert _norm_vec(0.90, self.CAL) == pytest.approx(0.0)
        assert _norm_vec(0.60, self.CAL) == pytest.approx(0.5)

    def test_norm_vec_outlying_distances_clamped(self):
        from src.pgHybridSearch import _norm_vec
        assert _norm_vec(0.10, self.CAL) == pytest.approx(1.0)
        assert _norm_vec(1.20, self.CAL) == pytest.approx(0.0)


class TestScoreFusion:
    def test_mode_from_config(self, monkeypatch):
        monkeypatch.setenv("RISKI_SEARCH__FUSION_MODE", "rrf")
        monkeypatch.delenv("RISKI_INSTANCE_CONFIG", raising=False)
        from src.instanceConfig import clear_cache
        clear_cache()
        try:
            from src.pgHybridSearch import _fusion_mode
            assert _fusion_mode() == "rrf"
        finally:
            clear_cache()

    def test_default_is_scores(self, monkeypatch):
        monkeypatch.delenv("RISKI_SEARCH__FUSION_MODE", raising=False)
        monkeypatch.delenv("RISKI_INSTANCE_CONFIG", raising=False)
        from src.instanceConfig import clear_cache
        clear_cache()
        try:
            from src.pgHybridSearch import _fusion_mode
            assert _fusion_mode() == "scores"
        finally:
            clear_cache()

    def test_score_fusion_preserves_within_signal_strength(self):
        # score blending separates within-signal strength: a cosine-0.35
        # content hit beats a cosine-0.47 one (RRF gives both equal rank
        # points if adjacent)
        from src.pgHybridSearch import _norm_vec, _norm_lex
        strong, weak = _norm_vec(0.35, TestNormCalibration.CAL), \
            _norm_vec(0.47, TestNormCalibration.CAL)
        assert strong > weak
        # a strong direct name hit ("beteiligungsportal" simulated live
        # value 0.82) beats an excellent vector-only hit (0.35) under the
        # configured weights lex 1.5 / vc 1.0
        assert 1.5 * _norm_lex(0.82, TestNormCalibration.CAL) > 1.0 * strong


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

    def test_lexical_recall_excludes_stop_term_only_matches(self, conn):
        from src.pgHybridSearch import hybrid_candidates

        # fake vector: name_vecs absent/empty → lexical does the work
        hyb = hybrid_candidates(
            conn, "Digitalstrategie der Stadt Karlsruhe", [0.01] * 1024, top_k=10,
            signals={"lexical": True, "name_vectors": False, "content_vectors": False},
        )
        names = [str(m["name"]).lower() for m in hyb["matched_entities"]]
        assert any("digitalstrategie" in n for n in names)
        # generic city-name matches must not survive the stop-term stripping
        assert not any("inklusionspreis" in n or "linke-kitas" in n for n in names)

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
