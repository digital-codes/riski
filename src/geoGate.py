"""Backward-compatibility shim — implementation moved to src.update.geoGate (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.geoGate import (  # noqa: F401
    logger,
    GATED_TABLES,
    GATE_COLUMNS_DDL,
    regex_boilerplate_reason,
    regex_all_addresses,
    PROMPT_TEMPLATE,
    GeoGate,
)
