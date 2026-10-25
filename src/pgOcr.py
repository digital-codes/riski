"""Backward-compatibility shim — implementation moved to src.update.pgOcr (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.pgOcr import (  # noqa: F401
    DEFAULT_MAX_PAGES,
    _TRUNCATION_NOTE,
    _TRUNCATION_NOTE_NO_TOTAL,
    find_missing,
    main,
    ocr_pdf_to_markdown,
    pdf_page_count,
    run,
)

if __name__ == "__main__":
    raise SystemExit(main())
