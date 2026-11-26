# Design: summary-pii-guard

## Context

Live finding: the model received the user-edited PII rule but enumerated
council member names. Root cause: the document teasers legitimately
contain the names and mistral-small prioritizes "answering the question"
over an embedded formatting rule. Prompt-only enforcement is leak-prone;
the product must guarantee PII-free output.

## Decisions

1. **Prompt lead + self-check, but non-authoritative** — the ban becomes
   rule 1 with the reference convention; the guarantee comes from the
   guard, not the model.
2. **Deterministic detection via the `Person` vocabulary** (748 rows,
   cached per process): match full names AND surnames (tokens ≥ 4 chars,
   word boundary, case-insensitive). Also match "Anrede + Nachname"
   patterns (Dr. X). Common-word collisions (e.g. "Bauer" as a noun)
   land on the over-redaction side — acceptable for a PII-first product;
   the redaction preserves the document references.
3. **Repair pass**: one chat call with
   `pii-repair-summary(-user)` prompts (registry), operating ONLY on the
   summary text; prompt_id `pii-repair-summary`,
   call_id `pgResultSummarizer.pii_repair.1`.
4. **Deterministic fallback**: per violated line — if the line is
   primarily person-name tokens (e.g. the sample's bare member list),
   drop the line for "(Name entfernt)"; inline occurrences replace
   matched tokens in place. No second model call.
5. Cache the name set with a TTL (aligned with the KG-enrichment cache;
   `invalidate` after imports is out of scope for this change since 748
   person rows change rarely).

## Risks / Trade-offs

- [False positives (surnames that are also words) → over-redaction] →
  prefer leaking-left over false-leak; protected inside the reference
  convention ("die Fraktion (Datei N)") the model produces.
- [Repair call adds latency only when a leak is detected] → bounded by
  the leak's presence; clean summaries pay nothing.

## Migration Plan

Code change, no data/DB writes; rollback = revert commit.

## Open Questions

None.
