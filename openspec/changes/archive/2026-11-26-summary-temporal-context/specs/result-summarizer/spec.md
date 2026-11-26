# result-summarizer Delta

## MODIFIED Requirements

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

### Requirement: Full answer-set coverage
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