# Proposal: content-chunking

## Why

Der Inhaltsektor der Suche komprimiert heute jedes Dokument auf ≤8.000 Zeichen:
49 % der Dateien liegen nur als LLM-Zusammenfassung vor (verlustbehaftet),
der Rest wird an 8.000 Zeichen abgeschnitten. Der Retrieval-Vektor misst damit
Ähnlichkeit gegen eine Kompression statt gegen den Dokumentinhalt, und der
Reranker beurteilt den komprimierten Text statt den tatsächlich passenden
Abschnitt. Zusätzlich kostet die Zusammenfassungsschicht (pgSummarize) einen
LLM-Aufruf pro großem Dokument bei jedem Import — die Ursache der wiederholten
Mistral-Budget-Ausreißer. Chunking auf Klartext behebt alle drei Punkte und
schafft zugleich die Abruf-Einheit („Belegstelle“) für die geplante
Wissensextraktion.

## Scope (bestätigt)

Nur Dateien, deren Markdown in `/mnt_ai/data/odd26/ris/ko_extracted` **über
8.000 Bytes** liegt: **10.198 Dateien** (9.095 aktuell als 'summary' gespeichert,
1.095 als 'fulltext' gecappt, 8 ohne File-Match). **Alle kleineren Dateien
(41.624) bleiben unangetastet** — ihr einzelner Vektor entspricht bereits einem
Ein-Chunk-Vektor.

## What Changes

- **Chunk-Tabelle `File_chunks`** — Klartext-Chunks (~6.000–8.000 Zeichen) mit
  `chunk_index` und Zeichen-Offsets, Grenzen bevorzugt an Markdown-Überschriften
  (kein Blind-Cut, kein Overlap nötig). Quelle ist `ko_extracted/*.md`
  (OCR-Output als Source of Truth), **nicht** `ko_sums`.
- **`chunkIndex` in `contentEmbeddings`** — ein Vektor pro Chunk; bestehende
  Einzel-Vektoren kleiner Dateien werden als `chunk_index = 0` geführt.
  Ein Datei-Treffer = bester Chunk (`min(distance) GROUP BY oparlKey`); die
  RRF-Fusion bleibt unverändert dateibasiert.
- **Reranker liest den besten Chunk** — statt der Zusammenfassung den
  tatsächlich passenden Abschnitt (diskriminanter, weniger Text).
- **pgSummarize-Pfad für >8k-Dateien eingestellt** — keine LLM-Aufrufe mehr für
  die Inhaltsebene; `File.content` behält den Dokumentkopf (erster Chunk) als
  Rückwärtskompatibilität für pgTeasers/Offline-Fallback; `contentKind`
  um einen `chunked`-Marker erweitert.
- **Backfill** — 10.198 Dateien, resume-safe, ~30.000–38.000 neue Embeddings
  via DeepInfra; bestehende Einzel-Vektoren der kleinen Dateien bleiben.
- **Kein Teaser-Verfahrenswechsel** — Teaser bleibt LLM über den Dokumentkopf;
  keine Per-Chunk-Zusammenfassungen (unnötige LLM-Kosten).

## Capabilities

### New Capabilities

- `content-chunking`: Chunk-basierte Inhaltsverarbeitung — Chunking
  (heading-bewusst), Speicherung (`File_chunks`), Backfill und
  Chunk-Einbettung als Abruf- und Belegebene.

### Modified Capabilities

- `semantic-search`: Content-Vektor-Recall auf Chunk-Ebene (bester Chunk pro
  Datei), Reranker-Eingabe = passender Chunk.
- `data-enrichment`: Content-Laden für >8k-Dokumente über Chunks aus
  `ko_extracted` statt LLM-Zusammenfassung; `contentKind` um `chunked`
  erweitert.

## Impact

- **Backend**: neuer Chunker + Ingest (Erweiterung der pgAddSummaries-Rolle),
  `pgHybridSearch.content_vector_candidates` (Chunk-Aggregation),
  Reranker-Eingabe in `pgTimeline`, Abschaltung des pgSummarize-Pfads für
  >8k-Dateien.
- **Datenbank**: Tabelle `File_chunks`, Spalte `chunk_index` in
  `contentEmbeddings` (NULL = legacy Ein-Chunk); keine Breaking-Änderung an
  bestehenden Tabellen.
- **Kosten**: Backfill ~30–38k Embeddings (einmalig, DeepInfra); laufend
  **Null LLM-Aufrufe** für die Inhaltsebene statt einem pro >8k-Dokument.
- **Risiko**: Klartext-Chunks enthalten Briefkopf-/Adress-Boilerplate, das
  Zusammenfassungen teilweise herausgefiltert haben — Reranker urteilt jetzt
  über den echten Abschnitt; Recall/Precision-Trade mit den Testsqueries
  verifizieren.
