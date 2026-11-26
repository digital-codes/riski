"""Backward-compatibility shim — implementation moved to src.update.pgOcr (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.pgOcr import (  # noqa: F401
    DEFAULT_MAX_PAGES,
    pdf_page_count,
    ocr_pdf_to_markdown,
    find_missing,
    pdf_status,
    run,
    main,
)

if __name__ == "__main__":
    raise SystemExit(main())
