# Spec Delta

## Purpose

Define the interactive refinement of the query-guided summary: a full-content
re-summarization on user action, per-file include/exclude control, and a
structured per-file list (name, download URL, referenced/refused) appended to
the summary above the provenance footer.

## ADDED Requirements

### Requirement: Full-content refinement on user action

The system SHALL re-run the query-guided summarizer with full document
content when the user requests refinement (refine button or a file-selection
change). The initial automatic summary SHALL continue to use the teaser
layer. Full-content runs SHALL cap the per-file context with a configurable
character budget. While a refinement runs, the previous summary SHALL remain
visible and the pane SHALL indicate the pending update; the pane SHALL be
updated when the refined summary arrives.

#### Scenario: Refine button triggers full-content summary
- **WHEN** the user activates the refine action for a session with a summary
- **THEN** the summarizer re-runs with full content and the pane is updated
  with the refined summary when the call completes

#### Scenario: Automatic pass stays teaser-based
- **WHEN** a search completes and the summary is fetched without user action
- **THEN** the summarizer uses the teaser layer as before

### Requirement: Per-file inclusion control

The system SHALL let the user include or exclude each fetched file from the
summary's document set. Changing the selection SHALL trigger a re-run of the
summarizer over exactly the included files with full content, and the pane
SHALL update with the new summary when it arrives. Exclusions SHALL persist
for the session so subsequent refinements honour them.

#### Scenario: User excludes a file
- **WHEN** the user toggles a file from included to excluded
- **THEN** the next summary run uses the remaining files with full content
  and the pane updates when it arrives

#### Scenario: Re-included files return
- **WHEN** the user re-includes a previously excluded file
- **THEN** the file is part of the next summary run again

### Requirement: File list with download URLs and verdict marking

Every summary SHALL end with a list of all fetched files, placed above the
model/usage provenance footer. Each entry SHALL contain the file's number
(from the prompt's document list), its name, and its download URL, and SHALL
be marked as referenced or refused. The same information SHALL be available
to the client as structured data (per file: identifier, name, download URL,
refused flag) so the frontend can render interactive controls.

#### Scenario: File list appears above the footer
- **WHEN** a summary is produced
- **THEN** the summary text contains the per-file list (number, name,
  download URL, referenced/refused) followed by the provenance footer

#### Scenario: Structured metadata for the frontend
- **WHEN** the summarize endpoint returns
- **THEN** the response carries the per-file metadata including the download
  URL and the refused flag

### Requirement: Refused files excluded from refinement by default

Files the model refused in the last run SHALL be pre-marked as excluded in
the interactive file list, so a refinement (which always follows user action)
does not silently re-include them. The user MAY re-include them explicitly.

#### Scenario: Refused files start excluded
- **WHEN** the file list is rendered for the first time after a summary with
  refused documents
- **THEN** the refused files are marked excluded by default and the user can
  toggle them back in
