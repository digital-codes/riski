# initial-query-snapshot Specification

## Purpose

Answers the work page's default query (config: `frontend.default_query`)
from a versioned JSON snapshot (`app/src/assets/sampleData.json`) captured
from the real staged pipeline, instead of executing a full backend
retrieval cycle (recall → timeline → graph → summary → geo) just to render
the landing state. This gives a faster initial paint and makes the landing
view independent of the backend. The same file remains the offline fallback
when the API is unreachable; interactive session actions that require a
live backend session (refinement, file toggles, neighbour expansion) are
disabled in snapshot mode instead of failing.

## Requirements

### Requirement: Initial query answered from a snapshot

The work page's default query (config: `frontend.default_query`) SHALL be
answered from a JSON snapshot file bundled with the frontend
(`app/src/assets/sampleData.json`) — captured from the real staged
pipeline — instead of executing a backend retrieval cycle. The snapshot
SHALL carry every staged payload the initial render consumes: stage-1
fields (top_files, matched_entities, facets, applied_filters), the
timeline, the `documents`-scope graph with `expandable_types`, the summary,
and the geo FeatureCollection with its availability flag. Any other query
SHALL hit the API as usual, and the snapshot SHALL remain the offline
fallback when the API is unreachable (error banner in that case only).

Snapshot mode SHALL be visible to the user (subtle hint, no error styling),
and interactive session actions that require a live backend session
(refinement, file toggles, neighbour expansion) SHALL be disabled with a
hint instead of failing.

#### Scenario: Landing view without backend

- **WHEN** the work page mounts with the default query
- **THEN** the panes render from the snapshot file without any API request

#### Scenario: User search uses the API

- **WHEN** the user submits any query other than the default query
- **THEN** the staged API pipeline runs as before

#### Scenario: Offline fallback preserved

- **WHEN** the API is unreachable for a non-default query
- **THEN** the snapshot is shown with the existing offline hint

#### Scenario: Snapshot actions disabled

- **WHEN** the user attempts refinement, file toggles, or neighbour
  expansion in snapshot mode
- **THEN** the action is disabled or shows an explanatory hint — no failed
  request

#### Scenario: Snapshot regeneration

- **WHEN** the pipeline contract or the default query changes
- **THEN** a capture script regenerates the snapshot from a live run so
  the file never goes stale
