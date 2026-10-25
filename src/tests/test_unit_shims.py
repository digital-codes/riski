"""Unit test that every re-export shim imports its full public surface
(unified-update-pipeline task 4.2) and that old CLI entry points keep
their main()/run() callables."""

import importlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# (shim module, package module) pairs moved by the restructure
SHIMS = {
    "src.update": [
        "oparlUpdate", "oparlRunLog", "syncIncremental", "pgOcr",
        "pgSummarize", "pgAddSummaries", "pgTeasers", "pgAddFileGeoRefs",
        "pgAddStreetRefs", "pgAddDistrictRefs", "pgCategorise", "pgTagMgr",
        "pgCoverage", "pgAddDistricts", "pgAddStreets", "pgAddNameVectors",
        "pgBackfillNameVecs", "pgAddVecs", "pgNameVecs",
    ],
    "src.search": [
        "pgVecSearch", "pgHybridSearch", "pgTimeline", "pgFileQuery",
        "graphModel", "pgResultSummarizer", "apiServer",
        "local_geo_matching",
    ],
}

CLI_ENTRY_POINTS = [
    "pgOcr", "oparlUpdate", "syncIncremental", "pgAddSummaries",
    "pgTeasers", "pgAddFileGeoRefs", "pgAddStreetRefs", "pgSummarize",
    "pgAddDistrictRefs", "pgCategorise", "pgCoverage",
]


def _public_names(module_file):
    """Top-level public defs/classes/UPPERCASE constants (AST-based —
    imported names like ``Path`` or ``argparse`` are not re-exported)."""
    import ast

    tree = ast.parse(module_file.read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id.isupper():
                names.add(node.target.id)
    return names


@pytest.mark.parametrize("pkg,mod", [
    (pkg, mod) for pkg, mods in SHIMS.items() for mod in mods
])
def test_shim_exports_match_implementation(pkg, mod):
    shim = importlib.import_module(f"src.{mod}")
    real = importlib.import_module(f"{pkg}.{mod}")
    public = _public_names(
        Path(importlib.import_module(pkg).__file__).parent / f"{mod}.py")
    missing = {n for n in public if getattr(shim, n, None) is not getattr(real, n, None)}
    assert not missing, f"shim src/{mod}.py misses: {sorted(missing)}"


@pytest.mark.parametrize("mod", CLI_ENTRY_POINTS)
def test_cli_entry_points_survive(mod):
    module = importlib.import_module(f"src.{mod}")
    assert callable(getattr(module, "main", None)) or \
        callable(getattr(module, "run", None)) or \
        callable(getattr(module, "_run_summarizer", None))


def test_no_internal_imports_of_old_paths():
    """Task 4.3: internal cross-imports use the new package paths (src/
    top-level shims are for external command lines only)."""
    from pathlib import Path

    moved = set(SHIMS["src.update"]) | set(SHIMS["src.search"])
    offenders = []
    for py in (Path(__file__).resolve().parents[1] / "src").rglob("*.py"):
        # shims themselves are exempt
        if py.parent.name in ("update", "search") or py.name.startswith(("pg", "oparl", "sync", "graph", "api", "local")) and py.parent.name == "src":
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            for mod in moved:
                if f"from src.{mod} import" in line or f"import src.{mod} " in line:
                    offenders.append(f"{py.name}: {line.strip()}")
    assert not offenders, "internal imports still use old paths:\n" + "\n".join(offenders)
