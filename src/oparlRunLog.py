"""Backward-compatibility shim — implementation moved to src.update.oparlRunLog (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.oparlRunLog import (  # noqa: F401
    EPOCH_BASELINE,
    SEED_BASELINE,
    STATUS_NEW,
    STATUS_MODIFIED,
    Base,
    OparlUpdateRun,
    OparlUpdateRunItem,
    OparlUpdateRunTypeCount,
    TABLES,
    ensure_tables,
    resolve_baseline,
    RunRecorder,
)
