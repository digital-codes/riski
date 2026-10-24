# Tasks

## 1. Backend — summarizer

- [x] 1.1 `ResultSummarizer.summarize(result, force=False, use_full_content=False, exclude=None)`: context mode in `_file_text` (full content capped at `full_content_chars`, teaser first otherwise), prompt header names the layer, excluded oparlKeys removed from the working file copy (original `top_files` untouched); unit tests cover teaser default, full-content mode, cap, exclusion filtering (verify `pytest src/tests -m unit`).
- [x] 1.2 `_file_list_section`: markdown file list (number, name as download-URL link, berücksichtigt/nicht berücksichtigt) inserted between summary body and `_footer`; `_file_text` SELECT extended with `downloadurl`; unit tests assert list order and placement (verify `pytest src/tests -m unit`).
- [x] 1.3 Structured metadata: result gains `summary_files` (`[{oparlKey, name, fileName, downloadUrl, refused, excluded}]`); refused files auto-added to the exclusion set on refine; unit tests for refused-prefilter and metadata shape (verify `pytest src/tests -m unit`).

## 2. API — `/summarize`

- [x] 2.1 `SummarizeRequest` gains `refine: bool = False`, `exclude: list[str] = []`; handler passes `force=refine`, `use_full_content=refine`, merges exclusions into the session result (`summary_excluded`), returns `{"summary", "files"}`; concurrent second refine for the same session returns the in-flight state (`summarizing` guard); unit test for the request model + integration test (rollback-only) for the session-result update (verify `pytest src/tests -m integration`).

## 3. Frontend — summary pane

- [ ] 3.1 `SummaryCard.vue`: "Verfeinern" button (spinner while refining, disabled during load) emitting `refine`; collapsible file list from the new `files` prop with per-file include/exclude toggles emitting `toggle-file`; refused files pre-checked as excluded; summary text stays visible during refinement.
- [ ] 3.2 `app/src/api.js` + `App.vue`: pass `refine`/`exclude` to `/summarize`, wire button + toggle events, keep old summary visible and replace on response; manual verification against the dev server.

## 4. Docs

- [x] 4.1 README "Summaries" section: refine semantics (full content on user action), file list above the footer, include/exclude control; `openspec validate --changes` passes.
