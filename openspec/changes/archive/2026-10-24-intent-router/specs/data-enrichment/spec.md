# data-enrichment Delta

## ADDED Requirements

### Requirement: Organization classification backfill
An enrichment pass SHALL derive and store `Organization.classification` for
organizations where it is NULL, using name-regex rules (Ortschaftsrat,
Ausschuss, Beirat, Eigenbetrieb, Amt, Fraktion, ...) in the same additive,
idempotent, re-runnable style as the document-type categorisation pass. The
pass SHALL NOT overwrite non-NULL classifications and SHALL trim surrounding
whitespace from stored organization names.

#### Scenario: NULL classifications derived
- **WHEN** the pass runs on an organization named "Ortschaftsrat Neureut"
  with NULL classification
- **THEN** a gremium-type classification is written and the row is never
  rewritten on re-runs

#### Scenario: Existing classifications preserved
- **WHEN** the pass runs where classification is already set
- **THEN** the value is left untouched

#### Scenario: Whitespace normalised
- **WHEN** an organization name carries leading or trailing whitespace
- **THEN** the stored name is trimmed (e.g. " CDU-Fraktion" → "CDU-Fraktion")
