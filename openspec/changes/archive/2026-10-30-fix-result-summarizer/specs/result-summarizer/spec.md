# Spec Delta

## MODIFIED Requirements

### Requirement: Teaser-layer context

The summarizer SHALL use the teaser layer for the automatic summary pass. On
a user-action refinement run (refine button or file-selection change) the
context per file SHALL be the file's content layer, selected as follows:

- When the search phase determined a best-matching chunk for the file
  (chunk index carried in the file's match metadata), the refinement context
  SHALL be the text of THAT chunk — the piece of the document that matched
  the query — not the head chunk stored in the legacy content column.
- Files without a matching chunk index SHALL keep the legacy content column,
  falling back to the teaser when content is absent.

The refinement context per file SHALL be capped by a configurable character
budget. The prompt SHALL state which context layer was used ("Teaser" vs
"Volltext").

#### Scenario: Teaser preferred

- **WHEN** a file has both teaser and content and no user action requested
  refinement
- **THEN** only the teaser text enters the prompt

#### Scenario: Full content on refinement

- **WHEN** a summary run is flagged as a refinement
- **THEN** the LLM context uses each included file's content layer, selected
  per the rules above: the matched chunk's text when the search phase
  carries a chunk index (capped by the configured budget), otherwise the
  legacy content column, falling back to teaser when content is absent

#### Scenario: Matched chunk on refinement

- **WHEN** a refinement run includes a file whose search-phase match carries
  a chunk index pointing at a stored chunk
- **THEN** the prompt contains THAT chunk's text (capped by the configured
  budget) instead of the head chunk from the legacy content column

#### Scenario: No matching chunk falls back

- **WHEN** a refinement run includes a file with no chunk index in its match
  metadata (lexical/name/location match, agenda sibling, legacy single-vector
  file)
- **THEN** the prompt contains the file's content column text, falling back
  to the teaser when content is absent

#### Scenario: Teaser pass unchanged

- **WHEN** the automatic summary pass runs
- **THEN** no chunk selection happens and the context is identical to the
  behaviour before this change

#### Scenario: Prompt names the context layer

- **WHEN** any summary run starts
- **THEN** the prompt's document header names the context layer in use
