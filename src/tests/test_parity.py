"""Parity check: every migrated module exposes the same public API as its
``src/`` counterpart (per design.md D6).

Checked statically via AST (legacy modules execute top-level code on import
and are therefore not safe to import directly). For each migrated pair, the
set of public top-level names must be a superset of the original's, and
functions with the same name must keep a compatible required-arity.
"""

import ast
import pathlib

import pytest

PKG_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_ROOT = PKG_ROOT.parent / "src"
PKG_NAME = PKG_ROOT.name  # "src" until the directory swap, then "src"
# After the directory swap the legacy tree no longer exists; parity checks
# against the original src/ are skipped when it is absent.
_LEGACY_AVAILABLE = SRC_ROOT != PKG_ROOT and SRC_ROOT.exists()

# Intentional public-API changes / removals, documented in design.md:
# - pgNameVecs: private helpers _embed/_table_exists moved to src.remote/db
# - pgGen: public API preserved; jsonTest.py dropped (superseded)
# - pgOcr: folded into the remote layer (ocr())
# - pgAddNameVectors: original was broken (undefined names); refactored
#   version implements the intended API
ALLOWED_MISSING: dict[str, set[str]] = {
    "pgNameVecs": {"_embed", "_table_exists"},
    "pgOcr": "*",  # module folded into src.remote
    "pgAddNameVectors": {"EMBED_URL", "EMBED_MDL", "EMBED_API_KEY", "make_engine"},
    "pgAddSummaries": {"EMBED_URL", "EMBED_MDL", "EMBED_API_KEY", "make_engine"},
    "pgAddVecs": {"engine", "Session", "Base", "Embedding", "loaded_vectors",
                  "loaded_files", "embs", "inspector", "session"},
    "pgTimeline": {"EMBEDDING_API_URL", "EMBEDDING_MODEL", "EMBEDDING_API_KEY",
                   "SUMMARY_API_URL", "SUMMARY_MODEL", "SUMMARY_API_KEY"},
    "pgVecSearch": {"EMBEDDING_API_URL", "EMBEDDING_MODEL", "EMBEDDING_API_KEY"},
    "oparlUpdate": {"OUTPUT_FOLDER", "OUTPUT_PDF_FOLDER", "LOG_FILENAME",
                    "LAST_RUN_FILE", "SYSTEM_URL"},
    "pgAddStreets": set(),
    "pgSummarize": {"srcDir", "dstDir", "mdFiles", "mdContents", "mdLengths",
                    "mdLines", "df", "q98", "df_q98", "df_large", "df_small",
                    "prompt", "MISTRAL_API_KEY", "MISTRAL_CHAT_URL",
                    "MISTRAL_CHAT_MODEL", "smallNames", "validNames",
                    "requestSummary"},  # renamed to request_summary
}


def _public_defs(path: pathlib.Path) -> set[str]:
    """Public top-level function and class names (the API surface)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not node.name.startswith("_")
    }


def _required_arity(path: pathlib.Path) -> dict[str, int]:
    """Map public function name -> number of required positional params."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    arities = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            args = node.args.args
            defaults = node.args.defaults
            n_default = len(defaults)
            count = len(args) - n_default
            if node.args.vararg:
                count = 0  # *args accepts anything
            arities[node.name] = max(count, 0)
    return arities


def _migrated_pairs():
    if not _LEGACY_AVAILABLE:
        return
    for path in sorted(PKG_ROOT.glob("*.py")):
        if path.name == "__init__.py":
            continue
        legacy = SRC_ROOT / path.name
        if legacy.exists():
            yield path.stem, legacy, path


def test_all_src_files_have_a_counterpart():
    """Every migration-targeted src module must exist in the new package.

    jsonTest.py is intentionally dropped (superseded by pgGen.py) and
    pgOcr.py is folded into the remote layer.  pgTagTest2.py is a superseded
    prototype of the TagManager; private.py is the git-ignored credentials
    module consumed through the shared db/remote config resolution.
    """
    if not _LEGACY_AVAILABLE:
        pytest.skip("legacy src/ tree no longer present (post-swap)")
    expected = {p.stem for p in SRC_ROOT.glob("*.py")}
    expected -= {"jsonTest", "pgOcr", "pgTagTest2", "private"}
    actual = {stem for stem, _, _ in _migrated_pairs()}
    missing = expected - actual
    assert not missing, f"modules not migrated: {sorted(missing)}"


@pytest.mark.parametrize("stem,legacy_path,new_path", list(_migrated_pairs()))
def test_public_api_superset(stem, legacy_path, new_path):
    legacy_public = _public_defs(legacy_path)
    new_public = _public_defs(new_path)
    allowed = ALLOWED_MISSING.get(stem, set())
    if "*" in allowed:
        pytest.skip(f"{stem}: intentionally folded into another module")
    missing = legacy_public - new_public - allowed
    assert not missing, f"{stem}: public names missing in refactored module: {sorted(missing)}"


@pytest.mark.parametrize("stem,legacy_path,new_path", list(_migrated_pairs()))
def test_public_functions_kept_required_arity(stem, legacy_path, new_path):
    """Functions with the same name must not gain new required parameters."""
    allowed = ALLOWED_MISSING.get(stem, set())
    if "*" in allowed:
        pytest.skip(f"{stem}: intentionally folded into another module")
    old_arities = _required_arity(legacy_path)
    new_arities = _required_arity(new_path)
    for name, old_req in old_arities.items():
        if name in allowed or name not in new_arities:
            continue
        new_req = new_arities[name]
        assert new_req <= old_req, (
            f"{stem}.{name}: required positional parameters increased "
            f"({old_req} -> {new_req})"
        )
