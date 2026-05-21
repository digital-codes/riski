## Why

The current OParl client (`src/oparl_fetch.py` / `src/oparl_update.py`) fails to download PDF files referenced by the `File.accessUrl` property. The failure manifests as HTTP 403/404 errors or truncated files, preventing downstream processing (e.g., PDF text extraction, embedding generation). Reliable PDF retrieval is essential for the RISKI pipeline because many downstream analyses (vector embeddings, full‑text search) depend on the original document content.

## What Changes

- Fix the HTTP request logic to correctly follow redirects and handle binary streams when downloading PDFs.
- Add proper `User‑Agent` and `Accept` headers required by some municipal OParl servers.
- Store the downloaded binary data in the `File.content` column (already present in the schema) and optionally write a local copy for debugging.
- Extend error handling: retry on transient network errors, log failures, and continue without aborting the whole crawl.

## Capabilities

### New Capabilities
- `oparl-pdf-download-fix`: The system SHALL download PDF files referenced by OParl `File` objects, store the raw binary in the `content` column, and handle common failure modes gracefully.

### Modified Capabilities
- *none* (no existing capability is altered).

## Impact

- Modifies the OParl fetch/update scripts in `src/`.
- No schema changes required (the `content` column already exists).
- Improves downstream processing reliability (vector generation, full‑text indexing).
