# KG-Pre — a metadata & ontology enrichment pipeline for Ratsinformationssystem data

*Proposal / consultation draft — 2026-11-18, derived from the
`kg-statement-extraction` prototype experience (change
`openspec/changes/kg-statement-extraction`).*

**The premise:** the paired-down OParl feed serving `riski` today is
"virtually free from reliable metadata and a precise content schema" —
the pipeline had to reconstruct request/response relations, outcomes,
parties, topics and vote results through traversal surgery
(`File__paper__Paper` attachment forensics), wording heuristics
(`Kenntnisnahme` vs `einstimmig zugestimmt`), name-regex vocabularies,
and text verification gates (`Punkt n der Tagesordnung`,
`Abstimmung` screenshots). All of that is *derivable* — and a
pre-ingest processor could derive it **once**, cleanly, so that
downstream retrieval/search/graph services consume a tidy, ontology-
grounded dataset instead of re-running workarounds.

The target shape: every document that enters the corpus leaves the
`KG-Pre` pipeline carrying **canonical metadata, typed relations and
grounded statements**, in a simplified OParl 1.1-compatible schema.

---

## 1. Architecture overview

```
        ┌────────────────────────────────────────────────────────┐
sources │ OParl 1.1 API / scraped HTML / PDF / local DB dumps    │
        └───────┬────────────────────────────────────────────────┘
                │ ingest (raw zone, unchanged originals)
        ┌───────▼────────────┐
        │ 1. NORMALIZE       │  one record per OParl entity, stable IDs,
        │    (id + schema)   │  provenance, source-hash, timestamps
        └───────┬────────────┘
        ┌───────▼────────────┐
        │ 2. CONTENT         │  PDF→markdown (OCR), chunking, per-chunk
        │    (text layer)    │  checksums — text is the unit of grounding
        └───────┬────────────┘
        ┌───────▼────────────┐
        │ 3. RELATE          │  resolve references: paper↔file↔agendaItem↔
        │    (graph)         │  meeting↔consultation↔organization; attach
        │                    │  protocols/screenshots by TOP+session match
        └───────┬────────────┘
        ┌───────▼────────────┐
        │ 4. CLASSIFY        │  controlled vocabularies (SKOS): doc type,
        │    (taxonomy)      │  outcome, status, topics, qualifiers —
        │                    │  decision-model verdicts w/ confidence
        └───────┬────────────┘
        ┌───────▼────────────┐
        │ 5. GROUND          │  statements: subject-predicate-object with
        │    (evidence)      │  span evidence (doc, chunk, char-range) +
        │                    │  extractor + verdict + confidence
        └───────┬────────────┘
        ┌───────▼────────────┐
        │ 6. PUBLISH         │  versioned dataset: SQLite/Post tables +
        │    (serve)         │  JSON-LD dumps; consumers = search/graph/RAG
        └────────────────────┘
```

Design principles, distilled from the prototype pain:

1. **One pass, idempotent, resumable** — each stage upserts on stable
   keys, so enrichment changes (new tag, new qualifier, new model) are
   re-runs of single stages, not pipeline rebuilds.
2. **Evidence or it didn't happen** — every produced fact carries
   `(subject, predicate, object, source_doc, span, method, confidence,
   verdict)`. No unvermed metadata column gets written without a
   pointer to where it came from.
3. **Vocabulary-first, model-second** — classification happens against
   versioned controlled vocabularies (SKOS schemes), not free-text
   LLM output; the model picks *from* the scheme (SystemOne
   question-per-term proved exactly right: one call, all 23 tags,
   noul = confidence).
4. **The OParl object is the spine** — even when scraped HTML lacks
   the structured links, the normalized record models the *OParl 1.1
   shape*, with `sourceProvenance: "derived"` on every reconstructed
   relation.

---

## 2. The schema: simplified OParl 1.1 core

OParl 1.1 defines exactly the entity system the prototype had to
reverse-engineer; the enriched schema is a **strictly typed subset**
(13 core classes) fixed into DDL rather than observed JSON columns
(the prototype's `pgGen` grown-up sibling):

```yaml
Body:            # the city
  id, name, website
Organization:    # gremium, faction, dezernat
  id, name, shortName, classification, organizationType
  membership*                       # → Person (role, startDate, endDate)
Person:
  id, name, familyName, givenName, affiliation*
Meeting:
  id, start, end, organization*, state(=geplant|durchgeführt),
  agendaItem*, protocol*, resultProtocol*
AgendaItem:
  id, number, name, meeting*, result, resolutionText_sb,
  consultation*
Consultation:
  id, meeting*, agendaItem*, paper*, role(decisive|consultative|),
  decisionBehavior(=consistent|deviating|pattern),
  authoritative(bool)
Paper:
  id, name, reference(address), date, paperType,
  originatorOrganization* / originatorPerson*,   ← the prototype's pain
  relatedPaper*  (superordinated/Änderungsantrag link),
  mainFile*, auxiliaryFile*
File:
  id, name, fileName, mimeType, date, sha256, size,
  text*: [chunks], fileClass (see §4)
Location / Street / District:
  id, name, geometry                     # geo layer, unchanged from riski
```

Two additions beyond OParl (documented as extensions, because Karlsruhe
 proved they carry the evidence):

* **`File.fileClass`** — controlled enumeration
  (`request | modification | response-protocol | ballot-result |
  attachment | protocol-fulltext`) — replaces the prototype's
  name-pattern guessing: assigned once at ingest, never re-derived.
* **`Consultation.decisionBehavior`** — OParl already defines
  `decisionBehavior` (`pattern`: repeats paper's decisionBehavior /
  `consistent` / `deviating`); the schema simply populates it, since
  the prototype had to infer it from `AgendaItem.result` availability.

## 3. Ontologies & vocabularies (concrete choices)

| layer | vocabulary | rationale |
|---|---|---|
| Document/paper type | **SKOS ConceptScheme** mirroring OParl `paperType` + RIS practice: `Antrag`, `Anfrage`, `Änderungsantrag`, `Ergänzungsantrag`, `Beschlussvorlage`, `Informationsvorlage`, `Einwohneranfrage`, `Petition`, `Wahlvorlage`, `Bekanntgabe`, … | the prototype's `papertypes` mapping becomes a scheme file (`kg_vocabulary.yaml` → migrating to `vocab/papertypes.ttl`) |
| Decision outcome | SKOS scheme: `zugestimmt`, `abgelehnt`, `beschlossen`, `zur Kenntnis genommen`, `vertagt`, `zurückgestellt`, `verwiesen`, `zurückgezogen`, `erledigt`, `stimmengleichheit`(+ per-body variants) | matches the prototype's `results` table incl. observed variants |
| Evidence role | `request`, `modification`, `response-protocol`, `ballot-result`, `attachment` | the `pair_documents.role` role column, made canonical |
| Topics (tags) | **ris-ki file-tags** (23 tags, existing seed) published as SKOS `ConceptScheme <https://ris-ki.de/ris/file-tags>` with per-qualifier `Concept`; | already ontology-designed in the prototype — the tag table *is* the scheme |
| Qualifiers | dedicated scheme: construction (Neubau/Sanierung/Erweiterung/Rückbau/Ausbau) + funding (Förderantrag/Drittmittel/Haushaltssperre) + procedure qualifiers | currently in YAML; the grounded `qualifiers` table directly maps |
| Actors/organizations | **local authority groupings + party scheme** (CDU/SPD/Grüne/FDP/LINKE/KAL/FRAKTIONSLOS/…) with *era validity intervals* (the prototype's `party_variants` era logic) | historical formations are the reason a naive party list fails |
| Administrative units | **AGS/Gemeindekennziffer** for districts/streets or OSM identifiers; riski's Streets/Districts Geo layer already provides geometry | keeps georeferences first-class |
| Domain predicate set for statements | small **W3C RDF-star friendly predicate vocabulary**: `kgps:requests`, `kgps:decides`, `kgps:modifies`, `kgps:costs`, `kgps:benefits`, `kgps:constrains`, `kgps:affects`, `kgps:executes`, `kgps:commences/ends` | the response/request statement field lists map 1:1 |

Rationale for SKOS: cheap (Turtle files + `rdflib`), versionable, and
every consumer can join on URIs rather than strings; the SystemOne
verdict per concept stays in the *evidence store*, not in the scheme.

## 4. Stage detail (where the prototype's workarounds become first-class)

### 4.1 Relate — attachment forensics becomes a per-relationship rule set
The prototype proved these attachment channels exist and can be
verified — KG-Pre turns them into declarative rules:

| rule | derived from | verification |
|---|---|---|
| paper↔protocol (per-TOP) | `File__paper__Paper`, name `Protokoll … TOP n` | TOP==agendaItem.number ∧ session date ∧ Beschluss-wording ↔ outcome |
| paper↔ballot ("Abstimmung%") | paper link, else name-TOP registry | TOP ∧ session (File.date) ∧ vote-majority ↔ outcome (OCR-warn preserved) |
| session-Niederschrift segmentation | `Meeting__auxiliaryFile`, multi-TOP docs | split on `Punkt <n> der Tagesordnung` (14 large GR files found) |
| Änderungsantrag↔original | `superordinatedPaper`, else title-similarity (difflib ≥0.75, ±1 yr) | consultation chain membership |

Each rule emits a typed relation **with its verification verdict**
(consistent / deviating / unverified stays in the graph but flagged).

### 4.2 Classify — one decision-model call per concept set
Exactly the SystemOne pattern that won in the prototype: for a document
state, one call carries *noul questions per concept* — outcomes, types,
topics WITH qualifiers — returning calibrated scores. Adjustment loop
(the D12 discipline): cross-check verdicts drive prompt/vocabulary
iteration, max 3 iterations per mismatch class, tuning report mandatory.

### 4.3 Ground — the statement layer becomes the product
The prototype's two LLM-stage statement sets (request/response fields)
forest into a **statement triple store** with homogeneous structure:

```
statement(id, subject, predicate, object,
          sourceOparlId, chunkIndex, charStart, charEnd,
          method(llm|ocr|db-column|regex|systemone),
          extractor, confidence, verdict, verifiedAt)
```

Round-trip fact check (render → compare → verdict) runs *inside* the
pipeline (not bolted on), on the rendered statement text vs source
span — per spec; pairs failing 3 tuning iterations are published
`verdict=failed` with reason, never silently dropped.

Vote numbers from ballot screenshots keep the OCR-clipping protocol:
*persist counts + plausibility verdict* (ok/warn/n.a.) — a warn never
produces a `kgps:decides` triple, only an annotation.

## 5. Output contract (what downstream gets)

Per body/time-slice publication:

* `papers.sqlite` / PostgreSQL: the typed schema of §2 (no guessing
  columns, `NOT NULL` where OParl guarantees a field);
* `statements.parquet`/`sqlite`: the triple+evidence store of §4.3;
* `vocab/` versioned SKOS TTLs (papertypes, outcomes, topics,
  qualifiers, parties) — consumers hard-pin a version;
* `kg_export.json` per pair — the prototype's export shape, minus the
  reconstruction;
* an API façade (`/papers`, `/statements`, `/votings`) so search &
  graph services (riski) consume via joins *only*.

Downstream simplicity example — the prototype's hardest query
("list all Gemeinderat decisions with outcome + vote weight + topic +
party") becomes:

```sql
SELECT p.name, s3.object AS outcome, v.ja, v.nein, t.tag, a.label
FROM papers p
JOIN statements s3 ON s3.subject=p.id AND s3.predicate='kgps:decides'
LEFT JOIN votings v ON v.paper=p.id
LEFT JOIN statement_topics st ON st.subject=p.id
LEFT JOIN tags t ON t.uri=st.object
LEFT JOIN parties a ON a.uri = (SELECT object FROM statements s2
                                 WHERE s2.subject=p.id AND s2.predicate='kgps:requests')
```

## 6. Runtime & models

* **Models**: the prototype's verdict — OLC cloud for extraction
  (gpt-oss:20b, ~3–6 s/PDF-set), decision model for classifications
  and verdicts (metis/greenpt: 0.3 s, cheap, deterministic), bge-m3
  only where similarity is genuinely needed (dedup, near-duplicate
  detection) — **not** for classification (SystemOne won).
* **Cost profile** (measured): ≈ 2 calls/pair/stage at ≤ 7 s — an
  8k-document corpus ≈ 15–25 h single-machine, embarrassingly
  parallelizable (`--shard` on paper hash).
* All stages in Python, typed (mypy), the repo layout mirrors
  `src/kg/*` renamed into `kgpre/{ingest,content,relate,classify,ground,publish}`.

## 7. Road-map sketch

| phase | scope | exit criterion |
|---|---|---|
| P1 | stages 1–3 (normalize/content/relate) + fixture-based tests vs today's forensic results (8,301 pairs, 267→792 response attachments, D10 chains) | relations ≥ the prototype's recall incl. the report's 350 ceiling… derived declaratively |
| P2 | stage 4 (classify) with the SKOS schemes ported from `kg_vocabulary.yaml` (23 topics, 9 qualifiers, outcomes, types, parties+eras) | tag/qualifier coverage on pair-docs ≥ current SystemOne sample (17/20, conf 0.91+) |
| P3 | stage 5 (ground): statements + inline round-trip cross-check; D12-style tuner | 94 %+ pass rate stable over 3 published versions |
| P4 | stage 6 (publish): typed schema + JSON-LD/SKOS + riski consumer migration | riski search/graph reads only KG-Pre output |

## 8. Honest gaps

* OCR of ballot screenshots stays lossy — keep counts as *annotated
  hints with warn verdicts* (the prototype's decision stands); a
  vision-OCR model (qwen3-vl, granite-vision) could later parse the
  seat maps into per-party votes.
* Era-valid party labels depend on intake data quality (membership
  history) — the SKOS party scheme should be curated from
  Ortschaftsrat/person years, not auto-derived.
* The DHH ('Antragsliste DHH 2026/2027', 'Beratungen zum DHH')
  meetings family needs a policy decision: they're budget debates, not
  simple request/decision pairs.

---

**Bottom line:** everything the kg prototype learned forensically is
mechanizable: typed schema (OParl subset + 2 documented extensions),
SKOS vocabularies ported 1:1 from the working YAML, SystemOne
classification with per-concept confidence, and a statement store
where every fact carries its evidence span and verification
verdict. The retrieval side then reduces to joins — which was the
point all along.
