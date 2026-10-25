"""Backward-compatibility shim — implementation moved to src.search.apiServer (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.search.apiServer import (  # noqa: F401
    AskRequest,
    ExpandRequest,
    MAX_EXCLUDE_ITEMS,
    MAX_FILTER_ITEMS,
    MAX_QUERY_LENGTH,
    SearchRequest,
    SummarizeRequest,
    ask,
    expand,
    geo,
    get_facets,
    get_session,
    health,
    search,
    summarize,
)
