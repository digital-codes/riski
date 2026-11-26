"""Backward-compatibility shim — implementation moved to src.update.pgTeasers (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.pgTeasers import (  # noqa: F401
    DEFAULT_MAX_LEN,
    TEXT_EXCERPT_MAXLEN,
    SUMMARY_TEMP,
    MAX_CHUNK_CHARS,
    TEASER_CEILING,
    CHUNK_PRE_SUMMARY_WORDS,
    parse_args,
    make_request,
    get_chunk_texts,
    summarize_to_teaser,
    generate_chunked_teaser,
    main,
)

if __name__ == "__main__":
    raise SystemExit(main())
