# Spec Delta

## Purpose

Identify, from the OParl database structure alone, documents that constitute request/response pairs around "Gemeinderat" decisions — request papers (Antrag, Anfrage, Beschlussvorlage, Änderungsantrag), their consultations, agenda items, meetings and the response/decision files — and classify the request type and meeting outcome with a confidence value.

## ADDED Requirements

### Requirement: Database-driven pair discovery
The system SHALL discover request/response document pairs solely from database tables and columns (Paper, File, File_chunks, AgendaItem, Consultation, Meeting and concept tables) using read-only credentials, without any writes to PostgreSQL.

#### Scenario: Antrag with consultation and decision file
- **WHEN** a Paper of papertype "Anfrage" or "Antrag" is linked through a Consultation (role "Entscheidung", authoritative) to an AgendaItem of a Meeting whose organization is "Gemeinderat", and decision files are attached to that association set
- **THEN** one pair candidate is emitted containing paper, agenda item, consultation, meeting date, request files and response files

#### Scenario: Minimal sparse deployment
- **WHEN** the database contains only the minimal source tables (Location, Organisation, Meeting, AgendaItem, File, File_chunks) with sparse columns and no structured OParl relations
- **THEN** identification still runs using the remaining fields (names, results, dates) and marks candidates with lower confidence instead of aborting

#### Scenario: Wording variance tolerance
- **WHEN** papertype, result or role values deviate from canonical wording (e.g. "enstimmig zugestimmt", "Kenntnisnahme", mixed-case or hyphenation variants)
- **THEN** the system classifies them via a configurable mapping (regex/normalization layer) and reports unmatched values in its console output instead of silently dropping the item

### Requirement: Classification signal hierarchy
The system SHALL classify item and result types using database columns and name patterns first, vectors/teasers second, and LLM calls only as a last resort; every candidate SHALL carry a provenance field naming the decisive signal and a numeric confidence.

#### Scenario: Column signal sufficient
- **WHEN** a candidate's papertype and AgendaItem.result unambiguously determine type and outcome (e.g. "Beschlussvorlage", "einstimmig zugestimmt")
- **THEN** the classification is recorded with signal "db-column" and no LLM call is made for that item

#### Scenario: Vector disambiguation
- **WHEN** columns are ambiguous and the chunk embeddings (BGE-M3) for the candidate's request and response documents show similarity to reference texts of a known type
- **THEN** the embedding signal is recorded as provenance with its confidence and the item is resolved without LLM escalation

### Requirement: Gemeinderat scope
The system SHALL only include meetings whose organization is "Gemeinderat" and SHALL ignore organizational-only documents in this prototype scope.

#### Scenario: Non-Gemeinderat meeting excluded
- **WHEN** a consultation leads to a Meeting identified as "Planungsausschuss" (organization is not Gemeinderat)
- **THEN** the pair is excluded from the output set and counted in a console exclusion summary

### Requirement: Protocol verification and response attachment
Meeting protocols (results protocol per meeting or per-TOP "Protokoll GR" files) SHALL be attached to a pair with role ``response`` only after verification: the protocol text SHALL reference the pair's agenda item TOP number AND the outcome wording in its "Beschluss" section SHALL be compatible with the pair's outcome. Unverified protocols SHALL stay unattached (not attributed to pairs) while remaining in the store's document pool.

#### Scenario: Verified TOP protocol
- **WHEN** a "Protokoll GR TOP 35" file's first chunk references "Punkt 35 der Tagesordnung" and its Beschluss wording matches the pair's outcome (e.g. "Kenntnisnahme")
- **THEN** the file is attached to the pair with role "response" and the verification verdict (top-match + result-match) is recorded

#### Scenario: Unverified protocol stays out
- **WHEN** a protocol's Beschluss section shows outcome wording that contradicts the agenda item result, or no TOP reference can be found
- **THEN** the file is not attached to the pair and the verification miss is reported in the run summary

### Requirement: Item history chains (pre-stage linking)
The system SHALL reconstruct the history of an item across meetings: papers discussed in multiple Gemeinderat meetings produce multiple pairs, and the system SHALL mark pairs that precede a final decision pair as pre-stage (``pre_stage`` flag) and link consecutive pairs of a paper's history in a pair-links table so statements can distinguish "discussion here" from "decided here".

#### Scenario: Multi-meeting item
- **WHEN** one paper is consulted in three Gemeinderat meetings and only the third carries a resolvable result
- **THEN** the first two pairs carry ``pre_stage = true``, are linked (first → second → third) and each pair keeps its own meeting date and per-pair outcome

#### Scenario: Outcome from consultation role
- **WHEN** a pair has no AgendaItem.result but its consultation role is "Kenntnisnahme"
- **THEN** the outcome is set to ``kenntnisnahme`` with signal ``db-partial`` and reduced confidence, only because the result column is empty (a present result always wins)

### Requirement: Ballot-screenshot vote evidence
Per-TOP ballot screenshots (``File.name LIKE 'Abstimmung%'``) SHALL be attachable to pairs as response documents when the TOP and session are verified; the OCR'd JA/NEIN/ENTHALTUNG counts SHALL be cross-checked against the pair's textual outcome and any contradiction SHALL be stored as a warning (clipped-digit risk) instead of being trusted or discarded. Attachment detail SHALL be persisted per document (verify_note).

#### Scenario: Consistent ballot counts
- **WHEN** an Abstimto screenshot shows JA=45, NEIN=0 for a pair whose outcome is "zugestimmt" and TOP + session date match
- **THEN** the file is attached with role "response" and verify_note records the consistent vote counts

#### Scenario: Contradicting OCR counts kept with warning
- **WHEN** the OCR'd majority (NEIN) contradicts the pair's textual outcome (zugestimmt) — plausible clipped-digit misreading
- **THEN** the attachment is kept, verify_note flags the contradiction explicitly, and downstream consumers know the counts are a hint only

#### Scenario: Session signal without text date
- **WHEN** the screenshot text carries no parseable date but the File.date equals the pair's meeting date
- **THEN** session verification passes via the deterministic File metadata

### Requirement: Status reporting
The script SHALL print progress status (counts found, classified, excluded) to the console at intervals of at most 10 seconds, and SHALL be resumable without duplicating output rows.

#### Scenario: Long run progress
- **WHEN** identification runs over several thousand papers for more than 10 seconds
- **THEN** the console receives at least one status line per 10-second interval with updated counts

### Requirement: Pair statistics report
The script SHALL report the distribution of documents per pair (chunk counts per file, number of request files, number of response files, count of modification-request chains) so expected characteristics (e.g. documents up to 5 chunks) can be verified.

#### Scenario: Chunk-size verification
- **WHEN** identification completes over the selected document set
- **THEN** a summary states how many documents exceed 5 chunks so the extraction layer can be validated against plan assumptions

## REMOVED Requirements

(none)
