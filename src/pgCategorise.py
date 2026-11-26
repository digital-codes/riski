"""Backward-compatibility shim — implementation moved to src.update.pgCategorise (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.pgCategorise import (  # noqa: F401
    SOURCE_CONFIDENCE,
    SOURCE_PRECEDENCE,
    precedence,
    resolve_precedence,
    default_confidence,
    canonicalize_document_type,
    DOCUMENT_TYPE_SCHEME,
    derive_papertype_tags,
    derive_name_regex_tags,
    derive_llm_tags,
    main,
)

if __name__ == "__main__":
    raise SystemExit(main())
