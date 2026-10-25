"""Backward-compatibility shim — implementation moved to src.update.pgAddStreetRefs (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.pgAddStreetRefs import (  # noqa: F401
    add_street_agendaitem_refs,
    create_streets_agendaitems_table,
    main,
    openDb,
)

if __name__ == "__main__":
    raise SystemExit(main())
