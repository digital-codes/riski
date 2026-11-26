"""Backward-compatibility shim — implementation moved to src.search.apiTrace (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.search.apiTrace import (  # noqa: F401
    ENV_FLAG,
    MAX_STR,
    MAX_LIST,
    trace_enabled,
    log_file_path,
    new_request_id,
    set_request_id,
    get_request_id,
    trace,
)
