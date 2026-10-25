"""Backward-compatibility shim — implementation moved to src.search.pgHybridSearch (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.search.pgHybridSearch import (  # noqa: F401
    CANDIDATE_TABLES,
    CapacityError,
    DEFAULT_CANDIDATES_PER_SIGNAL,
    DEFAULT_STOP_TERMS_FILE,
    FACET_TTL_DEFAULT,
    FilterError,
    LEXICAL_SIMILARITY_THRESHOLD,
    RRF_K,
    TABLE_DATE_COL,
    TABLE_NAME_COL,
    _FACETS,
    _FACET_CACHE,
    _FANOUT_SEMAPHORE,
    _HYBRID_EXECUTOR,
    _OPS,
    _YEAR_BASES,
    build_candidate_filters,
    content_vector_candidates,
    facet_ttl,
    facets,
    hybrid_candidates,
    invalidate_facet_cache,
    lexical_candidates,
    load_stop_terms,
    name_vector_candidates,
    parse_filters,
    rrf_fuse,
)
