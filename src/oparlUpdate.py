"""Backward-compatibility shim — implementation moved to src.update.oparlUpdate (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.oparlUpdate import (  # noqa: F401
    COLLECTIONS,
    FILTER_PARAMS,
    LOG_FILENAME,
    MAX_RETRIES,
    MODE_FULL,
    OUTPUT_FOLDER,
    OUTPUT_PDF_FOLDER,
    PAGE_LIMIT,
    REQUEST_DELAY,
    SYSTEM_URL,
    crawl_oparl,
    extract_links,
    fetch_json,
    fetch_pdf,
    fix_karlsruhe_url,
    fix_urls_in_data,
    generate_descriptive_filename,
    get_resource_timestamp,
    hash_filename_from_url,
    iso_to_dt,
    main,
    parse_resource_date,
    parse_resource_id,
    parse_resource_type,
    process_resource,
    sanitize_filename,
    save_json,
    should_save,
)

if __name__ == "__main__":
    raise SystemExit(main())
