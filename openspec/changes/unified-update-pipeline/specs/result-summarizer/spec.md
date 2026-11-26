# result-summarizer Delta

## Purpose

Carry the `summary-pii-guard` requirement into the main specs (the archived
change's delta was never synced) so it can be amended here: the PII guard
must not destroy street and district names that are derived from person
names — geo answers depend on them.

## ADDED Requirements

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
