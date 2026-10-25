"""Backward-compatibility shim — implementation moved to src.update.pgBackfillNameVecs (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.pgBackfillNameVecs import (  # noqa: F401
    DEFAULT_TABLES,
    PAUSE_SECONDS,
    main,
    run_table,
)

if __name__ == "__main__":
    raise SystemExit(main())
