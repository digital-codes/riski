# result-summarizer Specification

## Purpose

Produces the German summary rendered by the web app's SummaryCard: a
separate step (`src/pgResultSummarizer.py`) consuming a search result and
adding `result["summary"]`. The summary is QUERY-GUIDED — it condenses
ALL fetched document teasers with respect to the search question, states
the question, and degrades gracefully when no chat model is configured.

Invoked via `search_and_summarize` (wrapper) and the API's `POST
/summarize` (async step after `/search`).

## Requirements

### Requirement: Query-guided summarization
The result summarizer SHALL include the search query in the LLM prompt and
SHALL instruct the model to condense the document texts with respect to
that question (in German). A summary generated without using the query
SHALL be considered non-conforming.

#### Scenario: Prompt carries the query
- **WHEN** the summarizer runs on a search result with `query = "…"`
- **THEN** the assembled LLM prompt contains that query text and the
  instruction to summarize in view of the question

#### Scenario: Generic summary rejected
- **WHEN** the chat client is stubbed
- **THEN** the summarizer still passes the query-bearing prompt; the
  summary content returned by the model is stored verbatim under
  `result["summary"]`

### Requirement: Full answer-set coverage
The summarizer SHALL build its context from ALL files listed in
`result["top_files"]` — it SHALL NOT truncate the context to a fixed
subset (e.g. the first 5). The number of files is determined by the
search step (`top_k`), not the summarizer.

#### Scenario: All fetched files are included
- **WHEN** a search result contains 10 top files
- **THEN** the assembled prompt contains context from all 10 files

#### Scenario: Files without text are marked
- **WHEN** a file has neither teaser nor content
- **THEN** the prompt notes its absence (e.g. "Not available") but the
  file still counts as included

### Requirement: Teaser-layer context
The summarizer SHALL use the teaser layer for the automatic summary pass and
SHALL use full document content when a user action requests refinement
(refine button or file-selection change). The full-content context per file
SHALL be capped by a configurable character budget. The prompt SHALL state
which context layer was used ("Teaser" vs "Volltext").

#### Scenario: Teaser preferred
- **WHEN** a file has both teaser and content and no user action requested
  refinement
- **THEN** only the teaser text enters the prompt

#### Scenario: Full content on refinement
- **WHEN** a summary run is flagged as a refinement
- **THEN** the LLM context uses each included file's full content (capped by
  the configured budget), falling back to teaser when content is absent

#### Scenario: Prompt names the context layer
- **WHEN** any summary run starts
- **THEN** the prompt's document header names the context layer in use

### Requirement: Graceful degradation
The summarizer SHALL skip summarization (leaving `result["summary"]`
absent) when there are no top files, no chat model is configured, or the
chat client returns its offline dummy response.

#### Scenario: No model configured
- **WHEN** the chat base URL or model is missing
- **THEN** the result is returned unchanged and no error is raised

### Requirement: Provenance footer
The summary SHALL end with the provenance footer. When a per-file list is
present it SHALL be rendered between the summary body and the footer.

#### Scenario: Footer follows the file list
- **WHEN** a summary with a file list is produced
- **THEN** the file list appears above the footer and the footer content
  (model, endpoint, tokens, impact) is unchanged

### Requirement: Relevance filtering with refusal note
The summarizer prompt SHALL instruct the model to evaluate whether each
provided document actually relates to the question, to base the summary
only on the related documents, and to append a trailing note listing the
refused documents (or stating that all were used).

#### Scenario: Off-topic documents from a wide search
- **WHEN** the search returns documents unrelated to the question
- **THEN** the prompt instructs the model to exclude them from the
  summary and to list their titles under a "Nicht berücksichtigte
  Dokumente" note at the end

#### Scenario: All documents relevant
- **WHEN** every document contributes to the question
- **THEN** the note states that all documents were considered
