"""Backward-compatibility shim — implementation moved to src.search.pgTimeline (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.search.pgTimeline import (  # noqa: F401
    EMBEDDING_API_KEY,
    EMBEDDING_API_URL,
    EMBEDDING_MODEL,
    Embeddings,
    File,
    SUMMARY_API_KEY,
    SUMMARY_API_URL,
    SUMMARY_MODEL,
    TIMELINE_WINDOW_DAYS,
    TOP_K,
    build_timeline,
    call_embedding_model,
    call_reranking_chat_model,
    call_reranking_model,
    clear_embedding_cache,
    filter_by_threshold,
    find_related_objects,
    get_db_session,
    group_timeline_events,
    main,
    query_vector_similarity,
    search_and_build_timeline,
    search_and_summarize,
)

if __name__ == "__main__":
    raise SystemExit(main())
