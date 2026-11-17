# Proposal

## Why

The riski corpus currently supports retrieval (search, summaries, graph), but no structured, groundable record of *what the council decided and why*. The `/wissen` page already promises a knowledge-extraction layer. This change implements the prototype: identify request/response document pairs (Antrag/Anfrage → Beschluss/Mitteilung) from the OParl database structure alone, extract German topic tags (ris-ki schema), authors (parties), and concise grounding statements per request/response pair, so subsequent augmented retrieval can rely on verified facts instead of re-reading full documents.

## What Changes

- New read-only traversal scripts over the existing PostgreSQL schema (`Paper`, `File`, `File_chunks`, `AgendaItem`, `Consultation`, `Meeting`) that identify documents belonging to request/response pairs for the organization "Gemeinderat" (Antrag/Anfrage/Beschlussvorlage papers, their consultations, agenda items, meetings and outcome files).
- Classification of request type and response outcome from database columns (papertype, AgendaItem.result, Consultation.role/authoritative, name regexes), escalating only to embeddings/vectors and last-resort LLM.
- Meeting protocol files (per-TOP "Protokoll GR", meeting results protocols) are attached to pairs as response documents only after verification against the pair's agenda item TOP number and outcome wording (verified: 219/244 top-number matches, 54/81 outcome matches on the live corpus); unverified protocols stay unattributed.
- Item history reconstruction: papers discussed across several meetings mark pre-final pairs (`pre_stage`) and link consecutive pairs so a statement can distinguish discussion from decision (220 multi-meeting papers in the corpus).
- Tag extraction against the ris-ki file-tag schema (`https://ris-ki.de/ris/file-tags`): tag table with descriptions, multi-tag assignment with confidence values and qualifiers (e.g. Neubau/Sanierung/Erweiterung for construction).
- Author/party identification for request documents (CDU, SPD, Grüne, …) with normalization over inconsistent party naming and coalition changes over time.
- Statement extraction per pair: request statements (topic/title, type, meeting date, file ids, author, intended impact, affected audience, actor, precise requested action, start/end date, expected benefit, cost) and response statements (response type, result, action, executor, expected cost, dates, modifications to request, dependencies/constraints like Haushaltssperre or third-party funding conditions).
- Cross-check step: statements are rendered back to sample text and validated against the source chunks (fact compatibility).
- Prototype output in a local SQLite database (statement store, resumable), console status output at max 10s intervals; all German documents, typed and documented Python scripts, local ollama models only (`--endpoint` with default `ollama`, granite4.2:8b / qwen3.5:4b / mistral:latest — all tried, best selected -, bge-m3:latest embeddings, d3:2b decision model).
- No changes to the existing pipeline, API or web app; organizations are ignored for now (audience/executor resolved from names in text only).

## Capabilities

### New Capabilities

- `kg-pair-identification`: identifying request/response document pairs (papers, files, agenda items, consultations, meetings) from the OParl database structure, with outcome classification and confidence.
- `kg-statement-extraction`: extracting ris-ki tags with confidence/qualifiers, party authors, and per-pair request/response grounding statements into the SQLite prototype store, including the round-trip fact cross-check.

### Modified Capabilities

(none — read-only over the existing database, no pipeline/API behavior changes)

## Impact

- New scripts under `src/kg/` (or `scripts/kg/`), docs per script, new SQLite output artifact (e.g. `results/kg_statements.sqlite`).
- Reads via the read-only role (`RO_USER`/`RO_PWD`, `src/db`) — no writes to PostgreSQL.
- New local model dependency: ollama endpoint `http://localhost:11434/v1` (granite4.2:8b, qwen3.5:4b, mistral:latest, bge-m3:latest, d3:2b); model selection report recorded in `results/`.
- No frontend, API, search or import changes.
