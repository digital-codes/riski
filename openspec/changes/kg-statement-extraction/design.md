# Design

## Context

See proposal.md — Why. The database is the existing `riski_agentic` PostgreSQL instance (OParl import + enrichment layers, `File_chunks` is the single text store per change `unify-file-content-in-chunks`; BGE-M3 chunk embeddings exist in `contentEmbeddings`). Read-only access pattern: `src/db` resolves `RO_USER`/`RO_PWD` from `src/private.py`. Traversal example: `src/pgTimeline.py` walks Paper → Consultation → AgendaItem → Meeting. Shared model access lives in `src/remote` (OpenAI-compatible `chat()`/`embed()`). The intent router (`src/pgIntentRouter.py`) already demonstrates the SystemOne-style decision-model pattern with `d3:2b`.

Constraints from docs/kg_building.md: prototype only, all documents German, no consistent column wording can be assumed, organization scope = "Gemeinderat", local ollama models only in v1 (`http://localhost:11434/v1`, add `--endpoint` CLI param default `ollama`), output to JSON or SQLite, console status at most every 10s, typed and documented scripts with a usage doc each.

## Goals / Non-Goals

**Goals:**
- Identify request/response pairs from DB structure with a flexible, deployment-tolerant mechanism (works on sparse web-scraping-derived schemas).
- Extraction quality targets: tags (ris-ki schema), authors (parties), request/response statements with source references and cross-check verdicts.
- Store everything in a resumable local SQLite prototype store under `results/`.

**Non-Goals:**
- No writes to PostgreSQL; no changes to the import/enrichment pipeline, API, or web app.
- No organization-level statements (ignored this prototype); no Person/Membership graph.
- No production knowledge-graph serving; output later feeds augmented retrieval, not this repo's runtime.
- Not trying to make all deployments perfectly extractable — graceful degradation with confidence + provenance instead.

## Decisions

### D1: Output target — SQLite, not JSON
**Decision:** per-pair relational records (pairs, documents, tags, statements, verdicts) map naturally to tables, and resume-by-pair-status is a JSON-writing anti-pattern. JSON remains available as a secondary export filter (`kgExport.py` emits JSON from the SQLite store).
**Alternative considered:** raw JSON files per pair — simpler, but no unique constraint for resumability and awkward aggregation queries (chunk-count distributions, tag coverage).

### D2: New `src/kg/` package, not `scripts/`
**Decision:** extraction is a multi-stage pipeline with shared helpers (log/status loop, SQLite store, prompt libs, vector search), mirroring the `src/` package conventions (`pg*` scripts each runnable as module or file). One script per stage:
- `kgIdentify.py` — DB traversal → pair candidates (per kg-pair-identification spec), including the full per-pair input-document list (document id + file name, with role: request / modification / response / attachment)
- `kgTagSchema.py` — ris-ki tag table + descriptions seed
- `kgTagSystemOne.py` — tag assignment confidence/qualifiers via one
  SystemOne call per document (replaces the earlier vector-tier
  `kgTags.py`, removed 2026-11-18: the decision model proved strictly
  better — one call, all tags, noul=confidence)
- `kgAuthors.py` — party normalization and author extraction
- `kgStatements.py` — request/response statement extraction
- `kgCrossCheck.py` — statement→text round-trip verification
- `kgModelSelect.py` — language model comparison harness (granite4.2:8b / qwen3.5:4b / mistral:latest)
- `kgExport.py` — JSON export view of the store
**Alternatives considered:** one monolithic script (harder to resume/iterate per stage); reusing pg scripts directly (they write to PostgreSQL — forbidden here).

### D3: Pair identification — layered signals, LLM last
**Decision:** four tiers, each item records the tier that decided it (spec requirement "Classification signal hierarchy"):
1. **Structural** (deterministic): `Paper.papertype` ∈ {Antrag, Anfrage, Änderungsantrag, Beschlussvorlage, …} + `Consultation.role = "Entscheidung"` / `authoritative` + `AgendaItem.result` + organization of `Meeting` = "Gemeinderat". Traversal based on `pgTimeline.py`'s joins.
2. **Name regex**: normalized (case/hyphen/whitespace-insensitive) regexes over `Paper.name`, `File.name`, `AgendaItem.name`, `File.teaser`, mapped through a YAML vocabulary file so wording variance is a config change, not a code change.
3. **Vector**: bge-m3 similarity of chunk embeddings against small hand-labeled anchor sets (confirmed Antrag texts, response confirmations) for ambiguous candidates.
4. **LLM (last resort)**: granite-family model classifies only candidates unresolved by 1–3; cost-controlled by candidate count.

### D4: Normalization/party vocabulary as config, not code
**Decision:** `config/kg_vocabulary.yaml` holds: papertype/result/role mapping tables (with regex variants), tag definitions + trigger descriptions, party name variants and their era validity (coalition changes over time resolved using the meeting date). Deliberately separate from `config/instance.yaml` which is for OParl endpoints, not semantics.

### D5: Statement extraction — one LLM call per request/response stage over the full document
**Decision:** documents in scope have ≤ 5 chunks (verified in the identification report; spec scenario), so each extraction call sees the *whole* document text (all chunks concatenated, head chunk prioritized if oversized) with a JSON-schema-constrained output. Two calls per request-stage and two per-response-stage is avoided — a single structured call per stage returning the full statement field set; fields not present stay empty (no hallucinated costs/dates). Source-reference (chunk index) capture for cost/date/action fields is mandated in the prompt and stored.
**Alternative considered:** chunk-by-chunk map-reduce (as the teaser layer does) — unnecessary for ≤5-chunk documents and would fragment cross-chunk facts; revisit only if the chunk-count report shows many >5-chunk documents.

### D6: Cross-check via generation, not similarity alone
**Decision:** render the response statements to a short German sample text, then ask the LLM a fact-compatibility verdict question against the source chunks (SystemOne-style decision call, `d3:2b` for cheap first pass, language model for ties). Pure embedding similarity is kept as a negative prefilter only (very low similarity ⇒ immediate review flag).

### D7: Model access — extend the `src/remote` client pattern, ollama-bounded
**Decision:** `src/kg/kgRemote.py` wraps `chat()`/`embed()` with base URL fixed to the `--endpoint` CLI value (default "ollama" → localhost:11434/v1) and *deliberately ignores* `private.py` endpoint vars in v1 (spec requirement). Retry/backoff inherited from the shared client design.

### D8: Resumability
All stages upsert on stable keys (pair key = `(paper_oparl_id, first_meeting_oparl_id)`; statement rows keyed by pair + stage; tag rows by file+tag) with a `status` column per pair (`identified → tagged → statements → crosschecked`). Re-runs skip done rows; interrupted stages reprocess only their own stage.

### D13: Ballot-screenshot evidence class (2026-11-18 amendment)
Operator observation: 2,299 `File.name LIKE 'Abstimmung%'` files are per-TOP ballot screenshots (KPanel/QUINTA format — TOP number, session timestamp, JA/NEIN/ENTHALTUNG counts, party seat maps; see report addendum 2). New stage `kgAbstimmung.py` adds them as response candidates to EXISTING pairs (no kgIdentify rerun — upserts): paper-linked files direct, others via name-TOP + session (text date **or** deterministic `File.date` — preferred). The screenshot IS the result, so no outcome-wording check; instead the OCR'd numeric majority is CROSS-CHECKED against the textual outcome (zugestimmt/beschlossen → JA dominant, abgelehnt → NEIN dominant). Clipped-digit risk (8 vs 0): contradictions are kept but flagged — a `verify_note` (additive column on `pair_documents`, `ensure_verify_note`) records verdict + parsed counts per attachment; 205 ok / 25 warn / 403 n.a. on the full run; 792 pairs now carry response docs.

### D12b: d3:2b via local SystemOne endpoint (2026-11-18 correction)
The decision model IS serveable: ollama exposes `POST /v1/systemone` (noul/choice/score questions, cf. https://ollama.com/library/d3) — chat/generate/completions are unsupported, which caused the earlier "not serveable" note. `KgRemote.systemone()` wraps it; kgCrossCheck uses d3:2b noul (threshold 0.5 = contradiction) as the primary verdict with the language model as fallback.

### D12: Extraction↔cross-check loop (2026-11-17 amendment)
Cross-checking is not a one-shot post-step: run `kgCrossCheck.py` right after each extraction batch on the SAME sample pairs and use its verdicts to tune the extraction prompts — up to **3 adjustment iterations** (prompt tweaks, e.g. stricter German-only wording, field splitting, "never invent" reinforcement). A mismatch class that keeps failing after 3 iterations is recorded in `results/kg_crosscheck_tuning.md` (mismatch type → tried prompts → residual rate) instead of being silently dropped. Only pairs extracted with the final prompt version are trusted for the full run.

### D11: Statement stages in the chain context (2026-11-17 amendment)
With `kgChains` in place the statement stages split by history role: **request statements** are extracted from the pair's own documents (author joined from the `author` statement row); **response statements** attach to the pair's meeting where the outcome/protocol evidence exists (outcomes derived from columns + role fallback + vector tier + verified protocols). A modification pair (papertype class `modification`) links to its original request pair via deterministic title similarity (difflib sequence ratio ≥ 0.75) against request pairs with the nearest meeting date — stored as `modifies` in the request statement JSON. Statement fields stay strictly empty where the source has nothing (no invented costs/dates), and each pair gets `status='statements'` after extraction so re-runs skip it.

### D10: Item history chains (2026-11-17 amendment)
220 request papers span multiple Gemeinderat meetings (199 with a resolvable outcome somewhere) — the corpus supports reconstructing an item's history. Decision: a post-processing stage `kgChains.py` operates purely on the SQLite store: papers with several pairs get consecutive links in a `pair_links` table (relation `next`), and all pairs of a paper except the last one (the one with the latest meeting date) are marked `pre_stage = true`. Outcome-from-role rule (verified): `Consultation.role = 'Kenntnisnahme'` implies outcome `kenntnisnahme` ONLY when `AgendaItem.result IS NULL` — a present result always wins (role-Kenntnisnahme items also carry 'einstimmig beschlossen' and 'Beratung im Fachgremium' results in the corpus).

### D9: Protocol attachment — verbatim verification gate (2026-11-17 amendment)
The corpus structurally carries response documents in two places: per-TOP protocol files attached to agenda items ("Protokoll GR TOP n", 244 on GR agenda items) and meeting-level results protocols (142 GR files, mostly attendance-only in recent years). Verification against the DB held: 219/244 per-TOP protocols reference their agenda item's TOP number; the "Beschluss:" section outcome wording matches `AgendaItem.result` for 54/81 (regex pass, formatting + non-outcome result values account for the misses).
**Decision:** a dedicated stage `kgProtocols.py` attaches protocols to pairs with role `response` only when (1) the protocol text references the pair's agenda item TOP number and (2) the Beschluss-section outcome wording is compatible with the pair's outcome (vocabulary match, d3 decision-model fallback later). Unverified protocols are reported in the run summary and never attributed.

## Risks / Trade-offs

- **Sparse-schema deployments cannot reach high precision** → the confidence/provenance columns make precision honest; the extraction layers check their tier before trusting a field; the round-trip cross-check catches contradictions.
- **Small local models are weaker at JSON extraction** → structured prompts (JSON schema in the prompt), one-stage-per-call granularity, and `kgModelSelect` picks the best of the three; granite4.2:8b is the expected winner on structured extraction.
- **Party/coalition normalization is error-prone over decades** → era-valid variant tables keyed by meeting date; unknown variants are reported (never guessed); the author statement stays empty rather than wrong.
- **Tag strictness vs. coverage tension** → ris-ki descriptions as the anchor; free "other" tagging disallowed; unknown content stays untagged and shows up as a coverage number rather than a false tag.
- **Round-trip self-agreement bias** (LLM validating its own output) → decision model d3:2b issues the verdict, reveal-late check semantics, and failed verdicts are stored for human review rather than auto-silently regenerated.

## Migration Plan

Purely additive: new package, new SQLite artifact, one config file. No PostgreSQL schema or existing module changes. Rollback = delete `results/kg_statements.sqlite` and the `src/kg/` directory.

## Open Questions

- Exact ris-ki tag descriptions will be authored from the schema site during implementation (kgTagSchema); the taxonomy may truncate qualifiers — acceptable, tag table is data not code.
