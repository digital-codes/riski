# Spec Delta

## ADDED Requirements

### Requirement: Shared infrastructure for teaser generation
Teaser generation SHALL resolve its database connection through the shared
database access layer and SHALL call the LLM through the shared remote LLM
client using the configured summary endpoint and summary model by default. A
per-run model override SHALL be possible without changing the configured
default.

#### Scenario: Database connection without CLI credentials
- **WHEN** the teaser backfill runs with no username/password arguments
- **THEN** it connects using the shared database access layer's resolved
  credentials and does not require `localhost`/`riski_agentic` defaults

#### Scenario: Summary model is the default
- **WHEN** the teaser backfill runs without a model override
- **THEN** LLM calls target the configured summary endpoint and summary
  model, including legacy-named fallbacks in the configuration

#### Scenario: Per-run model override
- **WHEN** the teaser backfill runs with an explicit model override
- **THEN** that model is used for the teaser LLM calls while the configured
  summary endpoint/model remains untouched for other consumers
