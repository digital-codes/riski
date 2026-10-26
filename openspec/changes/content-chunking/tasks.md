# Tasks

## 1. Chunker und Speicherung

- [ ] 1.1 Chunker: heading-bewusstes Chunking von OCR-Markdown (Ziel ~7.000 Zeichen, Split an Markdown-Überschriften, harter Cut bei Überschriften-Läufen >8.000, kein Overlap); Rückgabe: Chunks mit index + char_start/char_end; Unit-Tests mit realen Markdown-Beispielen (kurz, groß 572 KB, ohne Überschriften) (`pytest src/tests -m unit`).
- [ ] 1.2 Tabelle `File_chunks` (file_sid, chunk_index, char_start, char_end, text; PK(file_sid, chunk_index)) + Spalte `chunk_index INT` in `contentEmbeddings` (NULL = legacy Einzel-Vektor); Migration per ADD COLUMN IF NOT EXISTS-Muster; Unit-Test auf Scratch-Schema (`pytest src/tests -m unit`).
- [ ] 1.3 Ingest-Integration: Laderolle mappt `ko_extracted/*.md` → File rows; >8k-Dokumente werden gechunkt (Chunks gespeichert, `File.content` = Dokumentkopf, `contentKind = 'chunked'`), ≤8k unverändert ('fulltext'); idempotent (Re-Run ersetzt Chunks); Integrationstest (`pytest src/tests`).

## 2. Embedding-Backfill (10.198 Dateien)

- [ ] 2.1 Backfill-Script (pgAddVecs-Muster): alle >8k-Dateien chunkweise einbetten (DeepInfra), Upsert (file, chunk_index); resume-safe (fortsetzen bei fehlenden Chunk-Vektoren); 402/Dummy-Responses → Chunk bleibt unversehrt fehlend; Integrationstest (`pytest src/tests`).
- [ ] 2.2 Vollständigkeits-Report: gechunkte Dateien, Chunk-Gesamtzahl, fehlende Vektoren; Ziel ~30–38k Chunk-Vektoren; dokumentierte Ausreißer (max 572 KB-Datei).

## 3. Recall auf Chunk-Ebene

- [ ] 3.1 `content_vector_candidates`: Chunk-Granularität (min(distance) GROUP BY oparlKey, matched chunk_index/char_range in der Rückgabe); Kill-Switch `RISKI_CHUNK_RECALL` (Default: aus bis Backfill komplett); Unit-Test mit Stub-Tabellen (bester Chunk gewinnt, Legacy NULL-Chunks unverändert) (`pytest src/tests -m unit`).
- [ ] 3.2 Umschaltung aktivieren (Default an), ivfflat/HNSW-Index-Parameter gegen ~120k Vektoren prüfen; Integrationstest + Latenzcheck gegen die alten Werte (0.6–0.8 s Hybridsuche) (`pytest src/tests -m integration`).

## 4. Reranker über den besten Chunk

- [ ] 4.1 Reranker-Eingabe: bester Chunk-Text für gechunkte Dateien, `File.content` für kleine Dateien (ein Codezweig); Unit-Test (`pytest src/tests -m unit`).
- [ ] 4.2 Verifikation Rerank-Qualität: Testsqueries — Passage-Input muss den Treffer klarer diskriminieren als die alte Zusammenfassung; dokumentierte Stichproben.

## 5. pgSummarize-Pfad für >8k abschalten

- [ ] 5.1 Laderolle: >8k-Dokumente ohne LLM-Aufruf verarbeiten (Chunks); pgSummarize/`ko_sums`-Lesepfad für >8k entfernt, <8k-Pfad unverändert ('fulltext'); Integrationstest (`pytest src/tests`).
- [ ] 5.2 README-Datenupdate-Workflow anpassen (Schritt 3 entfällt für >8k, Pipeline-Notiz), API.md/Docs-Seite (Dokumentation → Abschnitt Zusammenfassungen/Teaser) aktualisieren.

## 6. Verifikation

- [ ] 6.1 Testsqueries „sanierung theater“, „forum recht“, „klimaschutzkonzept“: Recall-Tiefe (Treffer jense der 8k-Grenze — z. B. spätere Kapitel großer Dokumente), Precision/Rerank-Verhalten dokumentiert; Vergleich gegen die alten Ergebnisse (vor Chunking).
- [ ] 6.2 Volltext-Suite grün (`python -m pytest src/tests -q`); `openspec validate content-chunking --strict`.
