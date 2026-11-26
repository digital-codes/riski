# Proposal: summary-pii-guard

## Why

The result-summary prompts were edited to prohibit personal information (PII: person names/addresses), but the model still leaks — live finding (2026-11-25, query "wer ist alles bei den grünen"): despite the rule, mistral-small enumerated ~8 council member names. llm_debug confirms the PII rule WAS in the prompt; promptsoftening alone does not hold for member-list-style questions because the document teasers literally contain the names.

## What Changes

- **Architectural fix (per GDPR review, 2026-11-26)**: prompt-level PII suppression is NOT a reliable control — the three real layers are:
1. **Scrub before generation**: the document context (teasers / full chunks / grounding blocks) is redacted BEFORE it enters the prompt — person names replaced by pseudonyms `[PERSON_1]`, `[PERSON_2]` … (deterministic vocab-based detection against the OParl `Person` table; the model cannot copy names it never sees).
2. **Verify after generation**: the produced summary runs a second detection pass (same detector); violations are redacted deterministically (`[PERSON_n]` / `(Name entfernt)`) — no repair-LLM dependency for the guarantee. (The earlier "repair pass" LLM call is DROPPED as unreliable.)
3. **Positive prompt rules only**: system prompts instruct positively ("Beziehe dich auf Personen ausschließlich über die Pseudonyme [PERSON_n] und cheeky Fraktions/Dokumentreferenzen (Datei N)") and stay short — negative bans are prompts' weakest instrument.
- Person names are pseudonymized CONSISTENTLY per request (same name → same pseudonym) so the model's statements stay internally referable.
- Guard runs in BOTH passes; also scrubs the grounding facts blocks.

**Follow-up change (ingest level, separate proposal)**: redact or embargo person names at INGEST (separate accessible field / `File_chunks` cleanup) — the context-scrub handles the summarizer, not the stored documents內; noted here per the design review, NOT in this change's scope.

## Capabilities

- **Modified Capabilities**: `result-summarizer` — summaries MUST NOT contain person names (PII ban enforced by detection + repair + deterministic fallback, not prompt-only).

## Impact

- Code: `src/pgResultSummarizer.py` (guard function wired into both passes), `config/instruction_prompts.json` (2 hardened texts + new `pii-repair-summary` pair), tests.
- Live DB: read-only Person scan. No API contract change.
