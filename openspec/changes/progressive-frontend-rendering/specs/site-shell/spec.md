# Spec Delta

## MODIFIED Requirements

### Requirement: Work page hosts the search UI and scrolls

The app SHALL render the existing search/exploration UI (search bar, network
view, summary, topic list, geo map, timeline, detail panel) inside a work page
container that has the shared navbar and footer. Unlike a fixed-viewport app
frame, the work page SHALL scroll as a normal document page. Result panes
SHALL render progressively as their data stages arrive (file list first, then
timeline, then network view), each showing a loading state while its data is
pending.

#### Scenario: Search UI available on work page

- **WHEN** the user navigates to the work page
- **THEN** the existing search UI is rendered and a search can be started as before

#### Scenario: Page scrolls

- **WHEN** the search produces results extending beyond the viewport
- **THEN** the user can scroll the page normally to reach all sections (network view, summary, map, timeline)

#### Scenario: Panes appear progressively

- **WHEN** a search is running and stage responses arrive one after another
- **THEN** the file list, timeline, and network view become visible and
  populated as their respective data arrives, each preceded by a visible
  loading state
