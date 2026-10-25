"""Backward-compatibility shim — implementation moved to src.update.pgTagMgr (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.pgTagMgr import (  # noqa: F401
    TagManager,
    _ID_COL,
    _OPAL_KEY_COL,
    _TAG_NAME_COL,
    _VALID_SOURCES,
)
