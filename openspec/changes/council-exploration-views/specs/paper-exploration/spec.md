# Spec Delta

## Purpose

Bietet eine Stöber-Sicht auf den Ratsinformationsbestand: Beschlussvorlagen
und Anträge browsen, nach Jahr, Typ, Einbringer, Beschluss-Status und
Stadtteil filtern, und jede Vorlage mit Beratungskette, Dateien und
Folgevorlagen-Kette im Detail sehen. Ergänzt die Frage-Antwort-Suche um
Exploration, ohne den offiziellen Sitzungskalender zu ersetzen.

## ADDED Requirements

### Requirement: Paper browsing with filters

The API SHALL expose `GET /papers` returning paginated papers with filters:
year, document type, submitter (Einbringer), decision status, and district;
results SHALL carry reference, title, date, type, submitter, and latest
decision status. Unknown filter values SHALL yield an empty result set, not
an error.

#### Scenario: Year filter separates eras

- **WHEN** the user filters papers by year 2013 versus 2020 for the topic
  "Klimaschutzkonzept"
- **THEN** each filter view returns only papers from that year

#### Scenario: Submitter filter

- **WHEN** the user filters papers by submitter "CDU"
- **THEN** only papers with a detected CDU submission are returned

#### Scenario: Unknown filter value

- **WHEN** a filter value matches no paper
- **THEN** the endpoint returns an empty page (200), not an error

### Requirement: Paper detail with consultation chain and related papers

The API SHALL expose `GET /papers/{reference}` returning the paper's
metadata (reference, title, type, date, submitter), its consultation chain
(meetings and agenda items with dates and decision status where available),
its associated files including auxiliary files, and related papers via
subordinated/superordinated links. An unknown reference SHALL respond 404.

#### Scenario: Consultation chain shows decision history

- **WHEN** a paper detail is requested for a paper consulted in two meetings
- **THEN** the response lists both consultations in order with dates and
  the decision status recorded per agenda item

#### Scenario: Related-paper chain

- **WHEN** a paper has a subordinated or superordinated paper link
- **THEN** the response lists the related paper(s) with reference and title

#### Scenario: Unknown reference

- **WHEN** `GET /papers/{reference}` is called with an unknown reference
- **THEN** the API responds 404

### Requirement: Browse pages in the frontend

The frontend SHALL provide a papers browse page (filter bar + result cards,
menu-reachable) and a paper detail page rendering the metadata, consultation
chain, files, and related-paper chain from the endpoints above.

#### Scenario: Browse page reachable and filterable

- **WHEN** the user opens the papers page from the menu and applies a filter
- **THEN** the list updates to the filtered papers
