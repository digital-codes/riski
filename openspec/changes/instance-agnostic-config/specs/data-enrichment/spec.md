# Spec Delta

## ADDED Requirements

### Requirement: City-specific enrichment rules from instance configuration

The deterministic address-block boilerplate heuristic (house number +
postal code + city name), the venue-noise patterns, the document-type
canonicalization rules and the organization classification name-regex
rules SHALL be sourced from the instance configuration with the current
Karlsruhe rules as defaults (see the `instance-config` capability), so
geo gating, file georeferencing and categorisation run unmodified against
another city's corpus.

#### Scenario: Gating regex follows the configured city
- **WHEN** the geo gate runs against a corpus whose address blocks end in
  the configured city name
- **THEN** pure address mentions are classified boilerplate by the
  deterministic heuristic exactly as they are today for Karlsruhe

#### Scenario: Categorisation without Karlsruhe conventions
- **WHEN** the categorisation pass runs with empty configured
  document-type canonicalization rules
- **THEN** document types pass through verbatim and name-regex/LLM
  classification uses the configured vocabulary
