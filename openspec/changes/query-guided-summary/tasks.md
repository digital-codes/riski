# Tasks: query-guided-summary

## 1. Summarizer changes

- [x] 1.1 Remove the `top` parameter and the `[: self.top]` truncation — context assembly iterates ALL `result["top_files"]`
- [x] 1.2 Replace `_SYSTEM_PROMPT` with the query-guided German instruction (summarize in view of the question, name the key documents, <500 words, no emojis)
- [x] 1.3 Prepend `Frage: {result['query']}` to the user message; fall back to the generic shape defensively when the query is missing
- [x] 1.4 Keep teaser-first context (`_file_text`), per-file cap, and all skip conditions unchanged

## 2. Tests

- [x] 2.1 Unit: prompt contains the query text and the guided instruction; user message starts with `Frage:`
- [x] 2.2 Unit: 10-file result → all 10 documents present in the prompt (no 5-file truncation)
- [x] 2.3 Unit: teaser preferred over content; content fallback when teaser missing; "Not available" marker when both missing
- [x] 2.4 Unit: existing skip conditions still pass (no top files, no model, dummy response, existing summary without force)
- [x] 2.5 Run full suite; live `/summarize` sanity check that the summary visibly addresses the question

## 3. Verification

- [x] 3.1 Update `app/src/assets/sampleData.json` via `search_and_summarize` with the new summary
- [x] 3.2 Frontend shows the query-guided summary (no component changes expected)
