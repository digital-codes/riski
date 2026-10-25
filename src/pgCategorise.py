"""Backward-compatibility shim — implementation moved to src.update.pgCategorise (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.pgCategorise import (  # noqa: F401
    DOCUMENT_TYPE_SCHEME,
    LLM_SYSTEM_PROMPT,
    SOURCE_CONFIDENCE,
    SOURCE_PRECEDENCE,
    _HAUSHALT_CODE_RE,
    _HAUSHALT_RE,
    _NAME_PATTERNS,
    _PRECEDENCE_RANK,
    canonicalize_document_type,
    default_confidence,
    derive_llm_tags,
    derive_name_regex_tags,
    derive_papertype_tags,
    main,
    precedence,
    resolve_precedence,
)

if __name__ == "__main__":
    raise SystemExit(main())
