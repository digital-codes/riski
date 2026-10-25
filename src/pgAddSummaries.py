"""Backward-compatibility shim — implementation moved to src.update.pgAddSummaries (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.pgAddSummaries import (  # noqa: F401
    Embedding,
    backfill_content_kind,
    content_kind_for,
    embed,
    ensure_embedding_unique_constraint,
    iter_md_files,
    main,
    normalize_file_basename,
    run,
)

if __name__ == "__main__":
    raise SystemExit(main())
