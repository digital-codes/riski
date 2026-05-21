## ADDED Requirements

### Requirement: PDF Download Capability
The system SHALL download PDF files referenced by `File.accessUrl` entries, following redirects, streaming binary data, respecting a 10 MiB size limit, and logging failures without aborting the crawl. The script must send a generic `User‑Agent` header and `Accept: application/pdf`.

#### Acceptance Criteria
- Uses `requests` with `stream=True`, a retry strategy (3 attempts, back‑off 0.5), and a maximum of 5 redirects.
- Skips PDFs larger than 10 MiB, logging a warning.
- Logs any network or HTTP errors and continues processing.
- Writes a local copy to `OUTPUT_PDF_FOLDER` if not already present.
- Does **not** store raw PDF content in the database (the `File.content` column remains untouched).
