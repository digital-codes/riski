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
subset (e.g. the first 5). The set comprises the relevance-ordered search
hits (limited by `top_k`) plus the agenda-item sibling documents appended
by the pipeline (change: agenda-answer-expansion); appended documents
carry their agenda-item provenance and are numbered continuously with the
search hits.

#### Scenario: All fetched files are included
- **WHEN** a search result contains 10 top files
- **THEN** the assembled prompt contains context from all 10 files

#### Scenario: Sibling documents are included
- **WHEN** the pipeline has appended agenda-item sibling documents to
  `top_files` (beyond `top_k`)
- **THEN** the assembled prompt contains context from the appended
  documents as well, and the document list numbers them continuously with
  the search hits

#### Scenario: Files without text are marked
- **WHEN** a file has neither teaser nor content
- **THEN** the prompt notes its absence (e.g. "Not available") but the
  file still counts as included

### Requirement: Teaser-layer context
The teaser-layer context SHALL carry each document's date: the snippet
header is `Datei N (TT.MM.JJJJ): <name> (…)` when the file has a date
(missing dates just omit the bracket). The context SHALL be presented in
CHRONOLOGICAL order (oldest first), with the file numbers (Datei N)
preserved from the user's relevance-ordered list so references keep
matching the rendered document list. The teaser prompt SHALL state the
order and the temporal-weighing rule.

#### Scenario: Date in the snippet header
- **WHEN** the teaser context is built for a file with a date
- **THEN** the header carries the date in TT.MM.JJJJ form

#### Scenario: Chronological order with stable numbering
- **WHEN** the summarizer context is assembled for 5 files with mixed
  dates
- **THEN** the context is ordered oldest first while each document keeps
  its user-visible Datei number

### Requirement: Refinement context chronology
The full-content refinement context SHALL carry the same per-document
date headers and chronological order. The refine prompt SHALL replace the
"nach Relevanz sortiert" statement with the chronological order and the
temporal-weighing instruction (the summary reflects the CURRENT valid
state: a newer document supersedes an older one; a refinement contradicting
a 3-year-old file in favour of the old one is a summarization error).

#### Scenario: Refine prompt carries chronology

- **WHEN** the refinement pass builds its context
- **THEN** the prompt states the chronological order and instructs the
  model to weigh temporal recency (no "3-years-later refinement" of an
  outdated decision as the current state)

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

### Requirement: PII-free context and summaries (person names)

Generated summaries SHALL NOT contain person names (PII). Enforcement is
ARCHITECTURAL — prompt instructions alone are no valid control, because the
model copies names it can see. The guard operates in two layers: person
names in the document context entering the prompt are replaced by
per-request-consistent pseudonyms (`[PERSON_1]`, `[PERSON_2]`, …) BEFORE
generation (deterministic, vocabulary-based detector over OParl `Person`
names, cached; word boundaries), and the produced summary runs the same
detector AFTER generation, with surviving occurrences redacted
deterministically (`[PERSON_n]` / "(Name entfernt)", bare member-name lists
collapse to the marker) — no repair-LLM dependency. System prompts instruct
positively (reference persons only via pseudonyms and file/fraction
references). The displayed/stored summary is therefore never rendered with
an unredacted person name, regardless of model compliance.

#### Scenario: Names scrubbed before generation
- **WHEN** a document teaser/source chunk containing person names enters
  the summarization prompt
- **THEN** the names appear in the prompt as pseudonyms `[PERSON_n]`
  (consistent per request), never as real names

#### Scenario: Model enumerates despite scrubbing
- **WHEN** the model produces a name enumeration anyway (e.g. it
  hallucinates around membership questions)
- **THEN** the output verification finds surviving names and the stored
  summary is deterministically redacted before it renders

#### Scenario: Clean summaries pass through untouched
- **WHEN** the produced summary contains no person-name matches
- **THEN** the summary is stored as generated


### Requirement: PII guard exempts street and district names

Occurrences of a detected person name SHALL be exempt from context
scrubbing and output redaction when the occurrence is part of an actual
street or district name compound (per `Street`/`District` vocabulary,
normalized comparison: case, ß/ss, hyphens/spaces, typical street suffixes
such as -straße/-weg/-platz). The exemption SHALL apply per occurrence and
only to the compound: the same person token appearing as a bare person
mention elsewhere SHALL still be redacted. If the geo vocabulary is
unavailable, the guard SHALL keep full redaction (privacy over geo answers;
fail-closed). Person names without a street/district compound SHALL never
be unmasked by this exemption.

#### Scenario: Hyphenated street compound survives
- **WHEN** a summary or prompt context contains "Marie-Alexandra-Straße"
  and a person in the vocabulary matches a compound component
  (e.g. "Alexandra")
- **THEN** the compound stays fully visible (not "[xxx]straße") in scrubbed
  context and output

#### Scenario: Simple street compound survives
- **WHEN** a summary contains "Karolinenstraße"
- **THEN** the compound is not redacted, because it matches a `Street`
  entry (or is covered by the suffix rules)

#### Scenario: Bare person mention is still redacted
- **WHEN** the same text mentions the person directly outside any
  street/district compound (e.g. "Karoline sprach gegen den Beschluss")
- **THEN** that occurrence is pseudonymized/redacted as before

#### Scenario: Geo vocabulary unavailable keeps privacy
- **WHEN** the `Street`/`District` vocabulary cannot be loaded
- **THEN** no exemption is applied and the guard behaves exactly as before
  (fail-closed)
