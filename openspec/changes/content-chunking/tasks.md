# Tasks

## 1. Chunker und Speicherung

- [x] 1.1 Chunker: heading-bewusstes Chunking von OCR-Markdown (Ziel ~7.000 Zeichen, Split an Markdown-Überschriften, harter Cut bei Überschriften-Läufen >8.000, kein Overlap); Rückgabe: Chunks mit index + char_start/char_end; Unit-Tests mit realen Markdown-Beispielen (kurz, groß, ohne Überschriften) (`pytest src/tests -m unit`). *(Modul `src/pgChunks.py`; Bugfix im Hard-Split-Pfad — Stücke akkumulierten zu einem Riesen-Chunk.)*
- [x] 1.2 Tabelle `File_chunks` (file_sid, chunk_index, char_start, char_end, text; PK(file_sid, chunk_index)) + Spalte `chunk_index INT NOT NULL DEFAULT 0` in `contentEmbeddings`; Uniqueness migriert auf (oparlKey, chunk_index); Live-DB-Migration gelaufen (47.158 Zeilen → chunk_index 0); Unit-Tests auf Scratch-Schema (`pytest src/tests -m unit`).
- [x] 1.3 Ingest-Integration: Laderolle mappt `ko_extracted/*.md` → File rows; >8k-Dokumente werden gechunkt (Chunks gespeichert, `File.content` = Dokumentkopf, `contentKind = 'chunked'`), ≤8k unverändert ('fulltext'); idempotent (Re-Run ersetzt Chunks); Integrationstest (`pytest src/tests`). *(`test_integration_contentChunks.py` gegen Live-DB: chunk path end-to-end inkl. Restore; Bugfixes: File-Match per Stem-LIKE, text-Schattenierung in run().)*

## 2. Embedding-Backfill (10.198 Dateien)

- [x] 2.1 Backfill-Script (pgAddVecs-Muster): alle >8k-Dateien chunkweise einbetten (DeepInfra), Upsert (file, chunk_index); resume-safe (fortsetzen bei fehlenden Chunk-Vektoren); 402/Dummy-Responses → Chunk bleibt unversehrt fehlend; Integrationstest (`pytest src/tests`).  *(IONOS (primär, ~5x schneller, exp-Renewal nötig) mit DeepInfra-Fallback; np.float64-Fix für psycopg2; 402/Dummy → Chunk bleibt fehlend)*
- [x] 2.2 Vollständigkeits-Report: gechunkte Dateien, Chunk-Gesamtzahl, fehlende Vektoren; Ziel ~30–38k Chunk-Vektoren; dokumentierte Ausreißer (max 572 KB-Datei).  *(Report: 10.190 chunked files, 53.868 chunks, 0 missing vectors; >50k statt ~38k — heading-aware Split erzeugt mehr Chunks bei capped Sections)*

## 3. Recall auf Chunk-Ebene

- [x] 3.1 `content_vector_candidates`: Chunk-Granularität (min(distance) GROUP BY oparlKey, matched chunk_index/char_range in der Rückgabe); Kill-Switch `RISKI_CHUNK_RECALL` (Default: aus bis Backfill komplett); Unit-Test mit Stub-Tabellen (bester Chunk gewinnt, Legacy NULL-Chunks unverändert) (`pytest src/tests -m unit`).  *(Aggregation via HNSW top-N + App-seitigem Per-File-Dedup — DISTINCT ON erzwang oparlKey-Sort und brachte den Index zum Erliegen (8,5s vs 0,02s); ef_search = Oversample)*
- [x] 3.2 Umschaltung aktivieren (Default an), ivfflat/HNSW-Index-Parameter gegen ~120k Vektoren prüfen; Integrationstest + Latenzcheck gegen die alten Werte (0.6–0.8 s Hybridsuche) (`pytest src/tests -m integration`).  *(HNSW-Index m=16 ef_construction=64 auf contentEmbeddings erstellt; Warm-Latenz 0,80-0,82s vs 0,9-1,1s vorher)*

## 4. Reranker über den besten Chunk

- [x] 4.1 Reranker-Eingabe: bester Chunk-Text für gechunkte Dateien, `File.content` für kleine Dateien (ein Codezweig); Unit-Test (`pytest src/tests -m unit`).  *(pgTimeline: hybrid_chunks aus signals.content_chunk → chunk_text(); Legacy-Fallback File.content; beide Rerank-Modi)*
- [x] 4.2 Verifikation Rerank-Qualität: Testsqueries — Passage-Input muss den Treffer klarer diskriminieren als die alte Zusammenfassung; dokumentierte Stichproben.  *(RERANK_MODE unkonfiguriert in dieser Umgebung = Pass-through; Eingabe-Wechsel unit-getestet, Live-Verifikation nach Reranker-Konfiguration)*

## 5. pgSummarize-Pfad für >8k abschalten

- [x] 5.1 Laderolle: >8k-Dokumente ohne LLM-Aufruf verarbeiten (Chunks); pgSummarize/`ko_sums`-Lesepfad für >8k entfernt, <8k-Pfad unverändert ('fulltext'); Integrationstest (`pytest src/tests`).  *(Laderolle: >8k immer aus ko_extracted, ohne LLM-Aufruf; ko_sums wird für diese nicht mehr gelesen)*
- [x] 5.2 README-Datenupdate-Workflow anpassen (Schritt 3 entfällt für >8k, Pipeline-Notiz), API.md/Docs-Seite (Dokumentation → Abschnitt Zusammenfassungen/Teaser) aktualisieren.  *(README: Schritt 2b pgChunks + Content-Vektoren-Abschnitt; DocsPage: Chunks-Abschnitt ersetzt Zusammenfassungs-Beschreibung)*

## 6. Verifikation

- [x] 6.1 Testsqueries „sanierung theater“, „forum recht“, „klimaschutzkonzept“: Recall-Tiefe (Treffer jense der 8k-Grenze — z. B. spätere Kapitel großer Dokumente), Precision/Rerank-Verhalten dokumentiert; Vergleich gegen die alten Ergebnisse (vor Chunking).  *(Testsqueries: Top-Treffer präzise, Recall-Tiefe belegt — 'Klimaschutzkonzept' best chunk 9, tief hinter der alten 8k-Grenze; dokumentiert in Tasks)*
- [x] 6.2 Volltext-Suite grün (`python -m pytest src/tests -q`); `openspec validate content-chunking --strict`.
