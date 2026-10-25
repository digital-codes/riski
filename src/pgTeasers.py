"""Backward-compatibility shim — implementation moved to src.update.pgTeasers (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.pgTeasers import (  # noqa: F401
    API_TIMEOUT,
    DEFAULT_MAX_LEN,
    LLM_API_KEY,
    LLM_MDL,
    LLM_URL,
    MAX_RETRIES,
    RETRY_DELAY,
    SUMMARY_MAX_TOKENS,
    SUMMARY_TEMP,
    TEXT_EXCERPT_MAXLEN,
    getcreds,
    has_existing_teaser,
    main,
    make_request,
    parse_args,
)

if __name__ == "__main__":
    raise SystemExit(main())
