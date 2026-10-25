"""Backward-compatibility shim — implementation moved to src.search.pgFileQuery (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.search.pgFileQuery import (  # noqa: F401
    find_unreferenced_files,
    get_related_ids_for_agenda_item,
    get_related_ids_for_file,
    openDb,
)
