"""Backward-compatibility shim — implementation moved to src.search.pgResultSummarizer (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.search.pgResultSummarizer import (  # noqa: F401
    log,
    person_names,
    find_pii_violations,
    TITLED_NAME_RE,
    Sc,
    pii_guard,
    scrub_names,
    TITLED_REFERENCE,
    ResultSummarizer,
)
