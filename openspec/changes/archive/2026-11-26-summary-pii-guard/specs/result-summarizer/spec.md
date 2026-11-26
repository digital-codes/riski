# result-summarizer Delta

## ADDED Requirements

### Requirement: PII-free context and summaries (person names)

Generated summaries SHALL NOT contain person names (PII). Enforcement is
ARCHITECTURAL (prompt instructions alone are no valid control — the model
copies names it can see from the context):

1. **Context scrubbing BEFORE generation**: the document context
   (teasers / full-content chunks / extraction grounding blocks) entering
   the prompt is redacted — person names replaced by per-request-consistent
   pseudonyms (`[PERSON_1]`, `[PERSON_2]`, …) such that the model cannot
   copy real names. The detector is deterministic and vocabulary-based
   (OParl `Person` names, cached: full names, surnames ≥ 4 chars, titled
   variants, word boundaries).
2. **Output verification AFTER generation**: the produced summary runs
   the same detector; any surviving occurrence is redacted
   deterministically (`[PERSON_n]` / "(Name entfernt)"). Lists of bare
   names collapse to the redaction marker. NO repair LLM call.
3. **Positive prompt rules only**: the system prompts instruct
   positively — "beziehe dich auf Personen ausschließlich über die
   Pseudonyme [PERSON_n] sowie Fraktions-/Dokumentreferenzen (Datei N)"} —
   and stay short.

The displayed/stored summary is therefore never rendered with an
unredacted person name, regardless of model compliance. The学和
summarizer scrub covers the PROMPT context; a separate ingest-level
cleanup of the stored documents is a follow-up change.

#### Scenario: Names scrubbed before generation

- **WHEN** a document望 teaser/source chunk contains person names and it
  enters the summarization prompt
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