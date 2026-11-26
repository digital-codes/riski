# Tasks: summary-pii-guard

## 1. Prompts

- [x] 1.1 Harden `result-summary` + `result-summary-refine`: PII ban first, no name enumerations, reference convention, self-check
- [x] 1.2 New `pii-repair-summary(-user)` prompts in the registry (RETIRED after the architectural decision — the repair LLM call was dropped; prompts stay registered for potential offline tooling)

## 2. Guard implementation

- [x] 2.1 `pgResultSummarizer`: person-vocabulary loader (cached) + `find_pii_violations(summary)` (full names, surnames ≥ 4 chars incl. title prefixes, word boundaries)
- [x] 2.2 Guard wiring in both passes: violation detected → repair call → fallback deterministic redaction
- [x] 2.3 Fallback: primary-person-name lines → "(Name entfernt)", inline occurrences replaced in place

## 3. Tests

- [x] 3.1 Detection: full name / bare surname / false-negative guards; no matches → no repair call
- [x] 3.2 Output path rewritten per architectural decision: deterministic redaction, NO repair LLM call (tests assert zero chat calls for the guard, pseudonym consistency in the scrubber, live-vocabulary prompt scrub)
- [x] 3.3 Prompt ids registered; live sanity: the context-scrubber removes the exact member names from the finding ("Dr. Heynen, Fahringer, Dujmovic, Akbaba…" → [PERSON_n], names left in context: none); unit suite 458 pass incl. apiTrace

## Workflow follow-up

- `/opsx-archive` after apply.
