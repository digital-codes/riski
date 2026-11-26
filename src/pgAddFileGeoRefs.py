"""Backward-compatibility shim — implementation moved to src.update.pgAddFileGeoRefs (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.pgAddFileGeoRefs import (  # noqa: F401
    STREET_FILE_ASSOC,
    DISTRICT_FILE_ASSOC,
    strip_venue_noise,
    match_files,
    prune_stale_agenda_refs,
    main,
)

if __name__ == "__main__":
    raise SystemExit(main())
