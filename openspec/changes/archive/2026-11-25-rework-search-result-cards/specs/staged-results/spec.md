# staged-results Delta

## MODIFIED Requirements

### Requirement: Search result card layout (search_topic)

The interactive client SHALL render the `search_topic` result view with the
following card order: (1) summary card (once the summary stage deliver­ed;
loading state before), (2) map card — only when geo data is available,
(3) timeline card, (4) network graph card (moved from the former first
position to last). The former top-10-files card SHALL be dropped from the
view. The former unstyled tags/related-documents paragraph block SHALL be
dropped from the view. The summary card SHALL no longer embed the related
section; instead a separate styled related-hints card SHALL follow the
summary card.

#### Scenario: Card order matches the contract

- **WHEN** a `search_topic` query returns files, meta, and geo data
- **THEN** the view shows summary card, then related-hints card (when
  allowed), then map, then timeline, then network graph — no top-10-files
  card and no unstyled tags/related-documents paragraph

### Requirement: Related-hints card visibility

The related-hints card SHALL show the refinement chips (kg topic hints the
user can pick to refine the query) and the related documents. It SHALL be
rendered ONLY when the result did NOT find a kg topic with a sufficiently
high score to enable a topical summary (topic focus below the topical
threshold). The chips SHALL be presented as interactive options — their
purpose is to give the user hints for refining the search query — not as
document list content.

#### Scenario: Hidden when topical summary enabled

- **WHEN** the query matched a kg topic above the topical threshold and the
  summary was generated with topic focus
- **THEN** no related-hints card is rendered (the summary stands alone)

#### Scenario: Shown for unfocused queries

- **WHEN** the query produced no topic focus above the threshold (plain
  search results) and related documents exist
- **THEN** the related-hints card follows the summary card with the
  refinement chips first, related documents second

#### Scenario: Chips refine the query

- **WHEN** the user picks a chip in the related-hints card
- **THEN** a new search is issued with the chip topic as a refinement hint
  (existing behaviour preserved)
