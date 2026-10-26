# Design

## Context

Siehe proposal.md. Relevanter Ist-Zustand:

- Pipeline: `pgOcr` → `ko_extracted/*.md` (134.847 Dateien, 51.822 .md) →
  `pgSummarize` (LLM, >8.000 Bytes → ≤8.000-Zeichen-Zusammenfassung in
  `ko_sums/`) → `pgAddSummaries` (match per Filename-Stem, `File.content`,
  `contentKind`: 23.946 'fulltext' / 23.212 'summary') → Embeddings
  (`contentEmbeddings`: id, oparlKey, value — 47.158 Zeilen, ein Vektor je
  Datei).
- Recall: `pgHybridSearch.content_vector_candidates` — Cosinus-Distanz über
  `contentEmbeddings`, Join auf `File`, RRF-Fusion dateibasiert; Reranker
  liest `File.content` (pgTimeline `call_reranking_*`).
- Teaser: `pgTeasers`, LLM über Dokumentkopf (`TEXT_EXCERPT_MAXLEN`).
- Redo-Set bestätigt: 10.198 >8k-Markdowns (9.095 'summary', 1.095
  'fulltext', 8 ohne File-Match); Größenverteilung p50 2 KB, p90 15 KB,
  max 572 KB.

## Goals / Non-Goals

**Goals:**
- Volle Dokumenttiefe im Retrieval (Chunks statt Kappung/Kompression).
- LLM-freie Inhaltsebene (pgSummarize-Rolle endet für >8k-Dateien).
- Reranker über den passenden Abschnitt; Chunk-Provenienz als Belegebene.
- Minimal-invasiv: kleine Dateien und deren Vektoren bleiben unberührt.

**Non-Goals:**
- Keine Per-Chunk-Zusammenfassungen und kein Teaser-Verfahrenswechsel.
- Keine Vereinheitlichung aller 47k Dateien auf Chunk-Speicherung (kleine
  Dateien bleiben bei Einzel-Vektor `chunk_index = 0`).
- Keine Änderung an RRF-Fusion, Facetten, Intent-Routing.
- Kein Overlapping (heading-bewusste Grenzen statt Blind-Cut+Overlap).

## Decisions

### 1. Quelle ist `ko_extracted` (OCR-Markdown), nicht `ko_sums`

Der Chunker konsumiert den OCR-Output. `ko_sums`/pgSummarize wird für
>8k-Dateien eingestellt — dafür war er da. `ko_sums` bleibt auf Disk (keine
Löschaktion), wird aber nicht mehr gelesen. Alternative — Chunks aus den
Zusammenfassungen — verwirft den Qualitätsvorteil.

### 2. Tabelle `File_chunks`, keine Parallel-Tabelle für Vektoren

`File_chunks(file_sid, chunk_index, char_start, char_end, text, PRIMARY
KEY(file_sid, chunk_index))` — Chunks sind die Belegebene und späterer
Zitier-Granulat (Wissen-Ausblick). Embeddings bleiben in `contentEmbeddings`,
ergänzt um `chunk_index INT NULL` (NULL = legacy Einzel-Vektor kleiner
Dateien; Werte ≥0 = Chunk-Vektor). Der Recall aggregiert
`min(distance) GROUP BY oparlKey` — ein Index auf `(oparlKey, distance)`-bzw.
ivfflat-Neuaufbau wird in Task 1 geprüft.

### 3. Heading-bewusstes Chunking, Zielgröße ~7.000 Zeichen

Split an Markdown-Überschriften, wenn der laufende Chunk ~7.000 Zeichen
überschreitet; hässliche Überschrift-Läufe (>8.000) werden hart geteilt.
Kein Overlap: Ratstexte sind stark gegliedert, Overlap kostete 10–15 %
Embedding-Volumen. Zielgröße unter dem alten 8k-Cutoff, damit kein Chunk
über die bisherige Vektor-Nutzungsgrenze hinausgeht.

### 4. Recall-Änderung minimal: Aggregation statt Schema-Wechsel

`content_vector_candidates` wird um Chunk-Granularität erweitert (Subselect
`min(distance) GROUP BY oparlKey` mit `chunk_index` im Rückgabepaket);
RRF, Kandidatenlimits und Signaltoggles bleiben unverändert. Die
Best-Chunk-Provenienz (chunk_index/char_range) wandert mit dem Kandidaten
in die Reranking-Stufe.

### 5. Reranker-Eingabe: bester Chunk

`pgTimeline` liest für rerankte Dateien den Text des besten Chunks
(statt `File.content`). Falls kein Chunk existiert (kleine Dateien),
weiterhin `File.content` — ein Codezweig, kein Datenmigration.

### 6. `File.content` = Dokumentkopf, `contentKind = 'chunked'`

Rückwärtskompatibilität für pgTeasers (liest Kopf), Offline-Fallback und
Bestandsabfragen. Der Kopf = erster Chunk (≤8.000). Alte 'summary'-Inhalte
der 9.095 Dateien werden durch den Dokumentkopf ersetzt (sie sind die
Verlustkompression, die wir loswerden).

### 7. Backfill als resumables Script (pgAddVecs-Muster)

Task-reihenfolge: (1) Chunker + Ingest, (2) Embeddings-Backfill
(Batch-Script, resume via fehlende Chunk-Vektoren), (3) Recall/Reranker-
Umschaltung, (4) pgSummarize-Abschaltung. Abbruch → Neustart setzt bei
fehlenden Chunks/Vektoren fort; Re-Runs ersetzen statt duplizieren.
Reihenfolge garantiert, dass die Suche nie auf halbfertigen Zuständen
läuft: Umschaltung erst, wenn Backfill vollständig ist (Kill-Switch-
Env-Var wie `RISKI_CHUNK_RECALL=0` für sofortigen Rollback auf
Ein-Vektor-Suche).

## Risks / Trade-offs

- [Klartext-Chunks enthalten Briefkopf-/Adress-Boilerplate] → Reranker
  urteilt über den echten Abschnitt (stärkerer Filter als vorher); GeoGate-
  Prinzip „permissiv, nur klarer Fall“ gilt für Anzeige, nicht für Recall.
  Recall/Precision-Trade mit den Testsqueries verifizieren (Task 7).
- [~30–38k neue Embeddings: Kosten/Zeit] → einmalig, DeepInfra-Batch
  (resume-safe); Größenordnung DeepInfra bge-m3 vernachlässigbar gegenüber
  den eingesparten Mistral-Summary-Aufrufen.
- [pgvector-Index: mehr Zeilen] → ivfflat/HNSW-Parameter prüfen; 120k
  Vektoren @1024 dims bleiben klein (~450 MB).
- [pgSummarize-Abschaltung betrifft auch zukünftige kleine Dateien nicht] →
  kein Risiko: <8k-Pfad bleibt unverändert ('fulltext').
- [Dummy-Responses beim Embedding-Backfill] → plausibilisierung: Chunk
  ohne Vektor = fehlt → Resume-Logik deckt ab.

## Migration Plan

1. Task 1–2 (Chunker, Ingest, Backfill) — rein additive Tabellen/Spalten;
   Suche läuft unverändert weiter.
2. Task 3–4 (Recall-Aggregation + Reranker-Umschaltung) hinter
   `RISKI_CHUNK_RECALL` (Default: aus bis Backfill komplett).
3. Task 5: pgSummarize-Pfad für >8k abschalten; Verification mit
   Testsqueries (Task 7).
4. Rollback: `RISKI_CHUNK_RECALL=0` (sofort) bzw. revert; Chunk-Tabellen
   bleiben ohne Schaden.

## Open Questions

- Chunk-Zielgröße 7.000 vs. 6.000 Zeichen (Embedding-Modell bge-m3 hat
  8.192-Token-Fenster — 8.000 Zeichen ≈ 2.000–3.000 Tokens, ausreichend
  Abstand zur Grenze; 7.000 ist konservativ gewählt).
- Sollen zukünftige kleine Dateien ebenfalls als `chunk_index = 0`-Zeile in
  `File_chunks` gespiegelt werden (einheitliche Abfragebasis) oder bei
  `File.content` bleiben? (Task 1 offen lassen, kein Verhaltensunterschied.)
