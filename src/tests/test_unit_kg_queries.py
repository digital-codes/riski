"""Unit tests for kgQueries helpers (mock engine, no live PG)."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.kg.kgQueries import json_loads, related_by_tags  # noqa: E402
from src.kg.kgQueries import statements_for_papers  # noqa: E402


class _Res:
    def __init__(self, rows): self.rows = [tuple(r) for r in rows]
    def fetchall(self): return self.rows
    def scalar(self): return self.rows[0][0] if self.rows else None


class _Ctx:
    def __init__(self, results): self._r = _Res(results)
    def execute(self, *a, **kw): return self._r
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _Eng:
    def __init__(self, results): self._r = results
    def connect(self): return _Ctx(self._r)

    def readonly(self): return self


class TestStatements:
    def test_flags_excluded_from_payload(self):
        f1 = {"topic": "T", "involved_cost": "", "_flags": {"involved_cost": "cost-m"},
              "_flagged": {"involved_cost": {"value": "9M", "reason": "x"}}}
        f2 = {"topic": "T2"}
        rows = [(10, 1, "request", f1), (10, 1, "response", f2)]
        eng = _Eng(rows)
        with patch("src.kg.kgQueries.get_engine", return_value=eng):
            out = statements_for_papers([10])
        assert out[10]["request"]["topic"] == "T"
        assert "involved_cost" not in out[10]["request"]  # excluded via flags
        assert out[10]["flags"]["request"] == {"involved_cost": "cost-m"}
        assert out[10]["response"]["topic"] == "T2"

    def test_empty_input(self):
        with patch("src.kg.kgQueries.get_engine", return_value=_Eng([])):
            assert statements_for_papers([]) == {}


class TestRelated:
    def test_related_excludes_top_files(self):
        rows = [(300, 2, 4.0, ["Culture", "Sports"])]
        eng = _Eng(rows)
        with patch("src.kg.kgQueries.get_engine", return_value=eng):
            got = related_by_tags([("10127", 1.0)], min_shared=2)
        assert got[0]["shared_tags"] == ["Culture", "Sports"]

    def test_name_resolution(self):
        # helper resolves display names in a second query (names query
        # hits the same mock rows)
        rows = [(300, 2, 4.0, ["Culture"])]
        got_res = _Res(rows)
        ctx = _Ctx(rows)
        # second context returns names rows; simulate by patching twice
        eng = MagicMock()
        eng.connect.side_effect = [_Ctx(rows), _Ctx([(300, "Nur Kultur", "300.pdf")])]
        with patch("src.kg.kgQueries.get_engine", return_value=eng):
            got = related_by_tags([("10127", 1.0)])
        assert got and got[0]["name"] == "Nur Kultur"


class TestJSON:
    def test_json_loads(self):
        assert json_loads({"a": 1}) == {"a": 1}
        assert json_loads('{"a": 1}') == {"a": 1}
