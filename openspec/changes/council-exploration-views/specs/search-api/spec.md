# Spec Delta

## MODIFIED Requirements

### Requirement: Facets Endpoint

The API SHALL expose `GET /facets` returning the facet listing (paperType,
years, result, organization, tag counts per scheme, decision status, and
submitter counts).

#### Scenario: Facets drive filter UIs
- **WHEN** `/facets` is fetched
- **THEN** paperType values, result values, years, per-scheme tag counts,
  decision-status counts, and submitter counts are present
