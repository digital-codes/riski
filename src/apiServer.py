"""Backward-compatibility shim — implementation moved to src.search.apiServer (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.search.apiServer import (  # noqa: F401
    app,
    SearchRequest,
    KG_RECALL_FLOOR,
    resolve_gremium_for_slot,
    MAX_QUERY_CHARS,
    validate_user_query,
    ExpandRequest,
    health,
    instance_config,
    file_proxy,
    search,
    AskRequest,
    ask,
    SessionRequest,
    GraphRequest,
    FollowupRequest,
    followup,
    timeline,
    graph,
    geo,
    SummarizeRequest,
    summarize,
    expand,
    get_facets,
    get_session,
)
