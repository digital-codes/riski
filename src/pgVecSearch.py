"""Backward-compatibility shim — implementation moved to src.search.pgVecSearch (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.search.pgVecSearch import (  # noqa: F401
    Embeddings,
    File,
    call_embedding_model,
    filter_by_threshold,
    main,
    queryFiles,
    query_vector_similarity,
)

if __name__ == "__main__":
    raise SystemExit(main())
