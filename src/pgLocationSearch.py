"""Backward-compatibility shim — implementation moved to src.search.pgLocationSearch (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.search.pgLocationSearch import (  # noqa: F401
    GEO_ASSOC,
    AGENDA_ITEM_CAP,
    RERANK_ACCEPT,
    candidate_files,
    candidate_agenda_items,
    location_search_stage,
)
