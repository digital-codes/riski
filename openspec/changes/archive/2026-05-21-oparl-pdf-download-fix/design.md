## Context

The RISKI project pulls OParl data via `src/oparl_fetch.py` and `src/oparl_update.py`. While most JSON fields are stored successfully, PDF files referenced by the `File.accessUrl` attribute are either not downloaded or result in corrupted/partial files. This is due to missing proper handling of binary streams, redirects, and required request headers on some municipal OParl servers.

## Goals / Non-Goals

**Goals:**
- Implement reliable PDF download logic that follows redirects, streams binary data, and stores the content in the existing `File.content` column.
- Add retry and exponential backoff for transient network errors.
- Log failures without aborting the whole OParl crawl.

**Non-Goals:**
- Changing the database schema (the `content` column already exists).
- Implementing a full‑blown file storage service; PDFs remain stored in the PostgreSQL table.

## Decisions

1. **Requests library** – Continue using `requests` (already a dependency). Use `stream=True` for binary downloads.
2. **Headers** – Add a generic `User-Agent` and `Accept: application/pdf` to satisfy stricter servers.
3. **Redirect handling** – Rely on `requests` default `allow_redirects=True` but enforce a maximum of 5 redirects to avoid loops.
4. **Retry logic** – Use `urllib3.util.retry.Retry` via `requests.adapters.HTTPAdapter` with 3 total attempts and backoff factor 0.5.
5. **Error handling** – Catch `requests.exceptions.RequestException`; on failure, log the URL and continue.
6. **Storage** – After a successful download, assign the `bytes` object to `entity['content']` before sending the row to the database (the `content` column is a `TEXT` field, suitable for storing base64‑encoded data). We'll store raw binary as base64 to keep it text‑compatible.

## Risks / Trade-offs

- **Risk:** Large PDFs could bloat the `content` column and impact database performance. *Mitigation:* Introduce a size limit (e.g., skip files > 10 MiB) and log a warning.
- **Risk:** Some OParl servers may require authentication or custom headers not covered here. *Mitigation:* Provide a configuration hook (`private.py`) where additional headers can be added.

## Migration Plan

1. Update `src/oparl_fetch.py` (or `src/oparl_update.py`) to include the new download helper function.
2. Run the existing migration script to ensure existing rows are untouched.
3. Execute a full OParl crawl on a test environment and verify that the `File.content` column is populated for PDFs.
4. Monitor database size and adjust the size‑limit policy if needed.

## Open Questions

- Should we also store a SHA‑256 checksum of the PDF for integrity verification?
- Is it worthwhile to move PDF storage to a separate file store (e.g., S3) and keep only a reference in the DB?
