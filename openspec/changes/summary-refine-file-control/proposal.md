# Proposal

## Why

The automatic summary deliberately uses the compressed teaser layer for speed,
which costs depth on complex result sets, and the summary gives the user no
way to correct the document selection. A single "Verfeinern" (refine) action —
plus per-file include/exclude control — lets the user spend a slower LLM call
on full content and on exactly the files they care about, with the pane
updating when the result arrives.

## What Changes

- **Refine button** in the summary pane: re-runs the query-guided summarizer
  with **full document content** (not teasers) for the active session and
  replaces the summary when the call returns. Active user interaction always
  implies full content; the initial automatic pass stays teaser-based and fast.
- **File list in the summary**: all fetched files are appended at the end of
  the summary markdown — each with its name and download URL, marked as
  referenced or refused — placed **above** the existing model/usage footer.
  The same list is exposed to the frontend as structured data for rendering.
- **Per-file include/exclude**: the frontend renders the file list with
  include/exclude toggles; clicking changes the file list for the session and
  triggers a re-run of the summarizer over the changed selection (full
  content, since it follows an active user interaction).
- **API**: `/summarize` accepts a refine flag and an exclusion list, honours
  them in the session-stored result, and returns the structured file metadata
  (oparlKey, name, fileName, downloadUrl, refused) alongside the summary.
- **No breaking changes**: the teaser-based first pass, the refused-documents
  parsing and the provenance footer behave as before when no refine/exclusions
  are requested.

## Capabilities

### New Capabilities

- `summary-refine`: interactive refinement of the query-guided summary —
  full-content re-summarization, per-file inclusion control, and the
  structured per-file download/marking metadata.

### Modified Capabilities

- `result-summarizer`: the summary content gains the download-URL file list
  above the provenance footer, and the summarizer accepts a file-selection
  override and a full-content context mode.

## Impact

- **Code**: `src/pgResultSummarizer.py` (context mode, exclusions, file-list
  section, structured metadata), `src/apiServer.py` (`/summarize` request
  model + session result update), `app/src/components/SummaryCard.vue` +
  `app/src/App.vue` + `app/src/api.js` (refine button, file toggles, re-run
  wiring).
- **Database**: no schema changes (`File.downloadurl` already exists).
- **Performance**: full-content summaries are slower and cost more tokens —
  they run only on explicit user action; the API keeps the existing
  request/response pattern (frontend shows a loading state on the button).
- **Tests**: backend unit tests for context mode/exclusions/file list; API
  test for the refine request shape; frontend unaffected by automated tests
  (manual verification).
