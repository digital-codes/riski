"""Backward-compatibility shim — implementation moved to src.update.oparlUpdate (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.oparlUpdate import (  # noqa: F401
    DEFAULT_SYSTEM_URL,
    DEFAULT_OUTPUT_FOLDER,
    DEFAULT_OUTPUT_PDF_FOLDER,
    DEFAULT_LOG_FILENAME,
    SYSTEM_URL,
    OUTPUT_FOLDER,
    OUTPUT_PDF_FOLDER,
    LOG_FILENAME,
    rewrite_url,
    fix_karlsruhe_url,
    fix_urls_in_data,
    sanitize_filename,
    hash_filename_from_url,
    generate_descriptive_filename,
    parse_resource_type,
    parse_resource_id,
    parse_resource_date,
    save_json,
    iso_to_dt,
    get_resource_timestamp,
    should_save,
    MAX_RETRIES,
    fetch_json,
    fetch_pdf,
    extract_links,
    process_resource,
    resolve_body_ids,
    COLLECTIONS,
    FILTER_PARAMS,
    MODE_FULL,
    crawl_oparl,
    main,
)

if __name__ == "__main__":
    raise SystemExit(main())
