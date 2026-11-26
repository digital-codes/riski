# Proposal: summary-temporal-context

## Why

Summaries contradict themselves across refinement runs and read
chronology-blind: the summarizer context has no per-file dates, and the
first pass does not even state the file order (the refine pass states
"nach Relevanz sortiert"). Live finding: a decision "to do ABC" from a
file dated ~today refines to "something else" from a file dated 3 years
earlier — two decisions of different ages presented as the current state.

Each `File` carries a `date` field (the meeting/publication date, mostly
via the relation lookups in `pgTimeline`) — it is already in the search
result payload (`top_files[].date`) and the timeline uses it.

## What Changes

- Both summarizer passes (teaser + refine) carry the DATE per document:
  the snippet header becomes `Datei N (TT.MM.JJJJ): <name>` (when a date
  is present).
- The context presentation order becomes CHRONOLOGICAL (oldest first)
  in both passes, while the per-file numbers (Datei N) keep matching the
  user's relevance-ordered list (numbering = visible-list position; the
  header carries it).
- `result-summary` prompt: documents ordered oldest first (stated).
- `result-summary-refine` prompt: the "nach Relevanz sortiert" sentence is
  replaced with the chronological order + the instruction to weigh the
  temporal order (an older decision supersedes only when a newer file
  says so; the summary states the CURRENT valid state).

## Capabilities

- **Modified Capabilities**: `result-summarizer` — context carries
  per-document dates, chronological order, temporal weighing instruction.

## Impact

- Code: `src/pgResultSummarizer.py` (context ordering + header dates),
  `config/instruction_prompts.json` (`result-summary`, `result-summary-refine`).
- No API contract change (`top_files[].date` already exists for the UI).
