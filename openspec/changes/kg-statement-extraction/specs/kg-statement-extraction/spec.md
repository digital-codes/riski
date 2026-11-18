# Spec Delta

## Purpose

Extract, per identified request/response pair, German ris-ki topic tags with confidence and qualifiers, the requesting party (author), and concise structured grounding statements for the request and the response — stored in a local SQLite prototype database and quality-checked by a round-trip fact cross-check.

## ADDED Requirements

### Requirement: Complete input document list
Each pair (or multi-pair/chain) SHALL carry the full list of its input documents, each with document id and file name — request documents, modification requests and response documents — independent of whether a statement refers to that document.

#### Scenario: Chain with amendments listed
- **WHEN** a chain consists of an original Antrag, one Änderungsantrag and one response file
- **THEN** the pair record lists all three documents with document id and file name

#### Scenario: Attached attachment files
- **WHEN** additional attachment files (Anlagen) belong to the request or response
- **THEN** they appear in the pair's document list with document id and file name as well, marked with their role in the pair

### Requirement: Tag schema classification
The system SHALL maintain a tag table with one description per tag from the ris-ki file-tag schema (https://ris-ki.de/ris/file-tags) and SHALL classify documents against those descriptions, allowing multiple tags per item, each with a numeric confidence and optional qualifier (e.g. Neubau / Sanierung / Erweiterung / Rückbau for construction), and SHALL be conservative (strictness over recall).

#### Scenario: Multi-tag with confidence
- **WHEN** a request document concerns installing a heat pump in a municipal building powered by renewable energy
- **THEN** the document receives tags such as "Energy" and "Building Construction" each with a confidence value, and the construction tag carries the qualifier for initial construction or reconstruction unless the text clearly indicates otherwise

#### Scenario: Uncertain document not tagged
- **WHEN** no tag description matches the document content above the strictness threshold
- **THEN** the document is stored untagged (no low-confidence forced assignment) and counted in the summary output

### Requirement: Author identification
The system SHALL identify the author of request documents, normalizing inconsistent party names and coalition/formations over time (e.g. CDU, SPD, Grüne, Frankfurter Liste variants), and SHALL record the normalization provenance.

#### Scenario: Party variant normalization
- **WHEN** one request's text references "CDU-Fraktion" and another a historical formation whose composition changed over the years
- **THEN** both resolve to their normalized party label with each request's meeting date used to apply the era-appropriate normalization

#### Scenario: Cannot determine author
- **WHEN** the source columns and document text do not indicate an authoring body
- **THEN** the statement stores the author field empty/unknown rather than guessing a party

### Requirement: Request statement set
For each request the system SHALL extract a statement record containing: topic or title, request type, meeting date (date of the meeting where discussed, not file date), document id and file names, author, intended impact or outcome, affected audience, actor responsible for action, precise requested action, start and end date, expected benefit and involved cost — each field stored with source document/chunk reference where available.

#### Scenario: Cost-free information request
- **WHEN** the request contains no cost or schedule information
- **THEN** the corresponding fields are stored empty and no placeholder or invented value is written

#### Scenario: Field traceable to source
- **WHEN** a non-empty statement field such as "involved cost" is extracted
- **THEN** the record stores the document id and chunk index from which the fact was taken

### Requirement: Response statement set
For each response the system SHALL extract: response type (zugestimmt, abgelehnt, vertagt, zur Kenntnis, delayed, …), result, action that will be taken, executing actor, expected cost, start and end date, modifications to the request, and dependencies or constraints (e.g. funding contingent on a third party, Haushaltssperre).

#### Scenario: Conditional approval
- **WHEN** the response approves a project only if a third party grants matching funds
- **THEN** the dependency/constraint field records that condition verbatim-summary with source reference

#### Scenario: Reference date question
- **WHEN** the meeting date of the request is queried
- **THEN** the statement reflects the meeting date at which it was discussed, not the file creation date

### Requirement: Modification chain handling
The system SHALL support pairs with more than two members — one or more modification requests (Änderungsantrag, Ergänzungsantrag) attached to an original request — and keep modification links between the statements.

#### Scenario: Amendment attached
- **WHEN** an Änderungsantrag references the same topic as an original Antrag in the same consultation chain
- **THEN** it is linked to the original request and its statements carry the modification relationship (requests and modifications form a chain; normally one response, but multiple responses are possible if external conditions change, e.g. Haushaltssperre)

#### Scenario: Changed conditions produce a second response
- **WHEN** an original topic receives two responses across meetings because a budget freeze intervened
- **THEN** both response statements remain linked to the same request statement with their respective meeting dates

### Requirement: Round-trip fact cross-check
The system SHALL render sample text from the extracted response statements and check against the source chunks whether the statement set and original text are compatible on facts (style irrelevant), storing a pass/fail verdict per checked pair. The cross-check SHALL run directly after extraction batches so verdicts can drive extraction-prompt adjustments — up to 3 adjustment iterations per mismatch class; residual mismatch classes after 3 iterations SHALL be documented instead of silently dropped.

#### Scenario: Statement contradicts document
- **WHEN** the generated sample text for a response contradicts a fact in the source chunks (e.g. wrong executing body)
- **THEN** the pair's cross-check verdict is stored as failed with a short reason so it can be revisited

#### Scenario: Compatible statement
- **WHEN** the rendered response text is fact-compatible with every source chunk referenced
- **THEN** the pair's cross-check verdict is recorded as passed

#### Scenario: Prompt adjustment loop
- **WHEN** a cross-check batch shows a recurring mismatch class (e.g. invented costs, English leakage)
- **THEN** the extraction prompt is adjusted and the sample re-extracted and re-checked, at most 3 iterations, with tried changes and residual rates recorded in the tuning report

### Requirement: SQLite prototype store
The output SHALL be written to a local SQLite database (tables for pairs, documents, tags, authors, request statements, response statements and cross-check verdicts); the system SHALL be resumable (already-extracted pairs are skipped) and all extraction scripts SHALL be typed, documented Python with a usage doc per script.

#### Scenario: Resume after interruption
- **WHEN** extraction is interrupted mid-run and restarted with the same environment
- **THEN** already completed pairs are skipped and previously written rows are not duplicated

### Requirement: Ollama-only models with configurable endpoint
Model endpoints SHALL default to the local ollama instance (http://localhost:11434/v1) regardless of `private.py` endpoint variables, with a command line parameter `--endpoint` (default "ollama") for the selection; the language model SHALL be one of granite4.2:8b, qwen3.5:4b, mistral:latest (all three tried, best selected and the choice documented), embeddings SHALL use bge-m3:latest and the classification/decision model SHALL use d3:2b.

#### Scenario: Default ollama endpoint
- **WHEN** the scripts are run without arguments while src/private.py contains other LLM endpoints
- **THEN** all model calls go to localhost:11434/v1 and no private.py endpoint URL is used

#### Scenario: Model comparison report
- **WHEN** the language model comparison run completes on a sample document set
- **THEN** results report per model on extraction quality so the best-performing model is recorded and used for the production run

## REMOVED Requirements

(none)
