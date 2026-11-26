"""Unit test: every re-export shim imports cleanly and exposes exactly
the names it declares (unified-update-pipeline, task 4.2)."""

import ast
import importlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SHIMS = [
    "oparlUpdate", "oparlRunLog", "syncIncremental", "pgOcr", "pgSummarize",
    "pgAddSummaries", "pgChunks", "pgTeasers", "pgAddFileGeoRefs",
    "pgAddStreetRefs", "pgAddDistrictRefs", "geoGate", "pgGeoGateCleanup",
    "pgCategorise", "pgCoverage", "pgTagMgr", "pgAddDistricts",
    "pgAddStreets", "pgAddNameVectors", "pgBackfillNameVecs", "pgAddVecs",
    "pgNameVecs", "pgVecSearch", "pgHybridSearch", "pgTimeline",
    "pgFileQuery", "pgLocationSearch", "graphModel", "pgResultSummarizer",
    "apiServer", "apiTrace", "local_geo_matching",
]


def _shim_names(mod: str) -> list[str]:
    src = Path(__file__).resolve().parents[1] / f"{mod}.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and \
                node.module.startswith(("src.update.", "src.search.")):
            return [a.name for a in node.names]
    raise AssertionError(f"no re-export import in shim src/{mod}.py")


def test_every_shim_imports_cleanly_and_exposes_names():
    for mod in SHIMS:
        module = importlib.import_module(f"src.{mod}")
        declared = _shim_names(mod) if (
            Path(__file__).resolve().parents[1] / f"{mod}.py").exists() else []
        # shims live at src/<name>.py — direct sibling of tests dir
        for name in declared:
            assert hasattr(module, name), f"src/{mod}.py missing {name}"


def test_shims_are_thin_reexports():
    src_dir = Path(__file__).resolve().parents[1]
    for mod in SHIMS:
        src = (src_dir / f"{mod}.py").read_text(encoding="utf-8")
        assert "implementation moved to" in src, mod
        # the shim contains no logic: only the import statement + guard
        tree = ast.parse(src)
        top = [type(n).__name__ for n in tree.body
               if not isinstance(n, (ast.Import, ast.ImportFrom))]
        assert set(top) <= {"FunctionDef", "If", "Expr", "Try"}, mod
        for n in tree.body:
            if isinstance(n, ast.FunctionDef):
                assert n.name == "main", mod  # only the __main__ stub


def test_implementation_modules_resolve():
    for mod in SHIMS:
        importlib.import_module(f"src.update.{mod}") if mod in (
            "oparlUpdate", "oparlRunLog", "syncIncremental", "pgOcr",
            "pgSummarize", "pgAddSummaries", "pgChunks", "pgTeasers",
            "pgAddFileGeoRefs", "pgAddStreetRefs", "pgAddDistrictRefs",
            "geoGate", "pgGeoGateCleanup", "pgCategorise", "pgCoverage",
            "pgTagMgr", "pgAddDistricts", "pgAddStreets",
            "pgAddNameVectors", "pgBackfillNameVecs", "pgAddVecs",
            "pgNameVecs") else importlib.import_module(
                f"src.search.{mod}")
