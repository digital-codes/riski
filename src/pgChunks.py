"""Backward-compatibility shim — implementation moved to src.update.pgChunks (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.pgChunks import (  # noqa: F401
    logger,
    SIZE_CUTOFF,
    CHUNK_TARGET,
    CHUNK_HARD,
    FILE_CHUNKS_DDL,
    chunk_markdown,
    ensure_tables,
    store_chunks,
    chunk_text,
    document_text,
    iter_oversized_md,
    file_id_by_stem,
    missing_chunk_indexes,
    run_backfill,
    fix_small_contents,
    main,
)

if __name__ == "__main__":
    raise SystemExit(main())
