"""Backward-compatibility shim — implementation moved to src.search.pgTimeline (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.search.pgTimeline import (  # noqa: F401
    log,
    EMBEDDING_API_URL,
    EMBEDDING_MODEL,
    EMBEDDING_API_KEY,
    TOP_K,
    TIMELINE_WINDOW_DAYS,
    SUMMARY_API_URL,
    SUMMARY_MODEL,
    SUMMARY_API_KEY,
    call_reranking_chat_model,
    call_reranking_model,
    Base,
    Embeddings,
    File,
    call_embedding_model,
    clear_embedding_cache,
    filter_by_threshold,
    listwise_rerank,
    rerank_gate_decision,
    query_vector_similarity,
    get_db_session,
    agenda_item_seeds,
    expand_top_files_by_agenda_block,
    block_expand_top_files,
    find_related_objects,
    build_timeline,
    group_timeline_events,
    search_stage,
    timeline_stage,
    graph_stage,
    search_and_build_timeline,
    search_and_summarize,
    main,
)

if __name__ == "__main__":
    raise SystemExit(main())
