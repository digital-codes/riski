# Spec Delta

## MODIFIED Requirements

### Requirement: Teaser-layer context

The summarizer SHALL use the teaser layer for the automatic summary pass and
SHALL use full document content when a user action requests refinement
(refine button or file-selection change). The full-content context per file
SHALL be capped by a configurable character budget. The prompt SHALL state
which context layer was used ("Teaser" vs "Volltext").

#### Scenario: Teaser preferred
- **WHEN** a file has both teaser and content and no user action requested
  refinement
- **THEN** only the teaser text enters the prompt

#### Scenario: Full content on refinement
- **WHEN** a summary run is flagged as a refinement
- **THEN** the LLM context uses each included file's full content (capped by
  the configured budget), falling back to teaser when content is absent

#### Scenario: Prompt names the context layer
- **WHEN** any summary run starts
- **THEN** the prompt's document header names the context layer in use

### Requirement: Provenance footer

The summary SHALL end with the provenance footer. When a per-file list is
present it SHALL be rendered between the summary body and the footer.

#### Scenario: Footer follows the file list
- **WHEN** a summary with a file list is produced
- **THEN** the file list appears above the footer and the footer content
  (model, endpoint, tokens, impact) is unchanged
