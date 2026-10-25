"""Backward-compatibility shim — implementation moved to src.search.pgResultSummarizer (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.search.pgResultSummarizer import (  # noqa: F401
    ResultSummarizer,
    _FULL_CONTENT_FACTOR,
    _MAX_CONTENT_CHARS,
    _REFINE_MAX_WORDS,
    _REFINE_SYSTEM_PROMPT,
    _SYSTEM_PROMPT,
    _TEASER_MAX_WORDS,
)
