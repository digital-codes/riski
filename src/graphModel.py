"""Backward-compatibility shim — implementation moved to src.search.graphModel (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.search.graphModel import (  # noqa: F401
    ADJACENCY,
    DEFAULT_MEETING_WEB_URL_FILE,
    _ATTR_FIELDS,
    _DATE_FIELDS,
    _UNSET,
    build_graph,
    expand_neighbors,
    load_meeting_web_base,
    node_id,
    parse_node_id,
)
