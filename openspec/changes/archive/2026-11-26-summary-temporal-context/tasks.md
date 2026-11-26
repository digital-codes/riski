# Tasks: summary-temporal-context

## 1. Implementation

- [x] 1.1 `pgResultSummarizer`: context rows sorted chronologically (oldest first, missing dates last, stable); header `Datei N (TT.MM.JJJJ): …` via file["date"]; numbering unchanged (full_index)
- [x] 1.2 Prompts: `result-summary` (order stated, temporal rule) + `result-summary-refine` ("nach Relevanz sortiert" → chronological + temporal weighing)

## 2. Verification

- [x] 2.1 Unit tests: date in header when present/absent; chronological order; numbering preserved; refine without the relevance sentence
- [x] 2.2 Live: the forum-recht sequence refine — the summary states the current valid state with dated references (no 3-year regression)
- [x] 2.3 Prompt registry diff clean; suite green

## Workflow follow-up

- `/opsx-archive` after apply.
