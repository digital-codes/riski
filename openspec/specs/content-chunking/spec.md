# content-chunking Specification

## Purpose

Chunk-basierte Inhaltsverarbeitung: OCR-Markdown wird heading-bewusst in
Klartext-Chunks zerlegt, pro Chunk eingebettet und als Abruf- und
Belegebene („Auszug aus Datei X, Abschnitt N“) vorgehalten — statt
Dokumente auf 8.000 Zeichen zu kappen oder LLM-Zusammenfassungen als
Retrieval-Grundlage zu verwenden. `File_chunks` ist die einzige
Ablage von Dokumenttext; `File.content` und `contentKind` sind
abgeschafft.

## Requirements

### Requirement: Heading-aware chunking of OCR markdown

The ingestion pipeline SHALL store ALL document text in `File_chunks` —
`File_chunks` is the single source of document text. Oversized OCR
markdown (larger than the size cutoff) is chunked into plaintext chunks of
~6.000–8.000 characters with chunk boundaries preferred at markdown
headings (chunk_index 1..n); each chunk SHALL record its chunk index and
character offset range within the document. Non-oversized documents SHALL
be stored as a single chunk at `chunk_index = 0` holding the complete
text — the legacy `File.content` column SHALL be retired (NULL after
migration) and SHALL NOT be written by any pipeline step. The legacy
`contentKind` column (a storage-mode provenance marker, never a document
attribute) SHALL be dropped together with its index. Files at or
below the cutoff SHALL NOT be re-processed; their existing single
embedding SHALL be carried as `chunk_index = 0`.

#### Scenario: Large document yields ordered chunks

- **WHEN** a 572 KB markdown is ingested
- **THEN** ordered chunks of ~6.000–8.000 characters are stored, each with
  index and character offsets covering the document

#### Scenario: Small document untouched

- **WHEN** the chunker runs over a document below the cutoff
- **THEN** the file is skipped and its existing single embedding remains

#### Scenario: Chunking is idempotent

- **WHEN** the chunker re-runs over an already chunked document
- **THEN** its chunks are replaced in place (same chunk identity), without
  duplicates

#### Scenario: Single-chunk documents

- **WHEN** a document's extracted text does not exceed the size cutoff
- **THEN** the complete text is stored as one `File_chunks` row at
  `chunk_index = 0` and `File.content` is not written

#### Scenario: Oversized documents unchanged

- **WHEN** a document's extracted markdown exceeds the cutoff
- **THEN** heading-aware chunks 1..n are stored exactly as before

#### Scenario: Content column retired

- **WHEN** the migration has run
- **THEN** `File.content` is NULL for all rows and no pipeline step reads
  or writes it

#### Scenario: contentKind column dropped

- **WHEN** the retire step runs
- **THEN** the `contentKind` column and its index are dropped; the geo
  gate's document-type prompt field falls back to "unbekannt" (the same
  path agenda-item gating already exercises) and the coverage report no
  longer lists a contentKind layer

#### Scenario: Text resolution for consumers

- **WHEN** a consumer (summarizer fallback, reranker, teaser generation,
  geo gate) needs a document's text
- **THEN** it reads it from `File_chunks` (single chunk 0 for small
  documents, the matched/all chunks for oversized ones)

### Requirement: Vector-preserving content migration

The migration from the dual storage (`File.content` + `File_chunks`) to
chunk-only storage SHALL preserve every existing content embedding: the
text of each `fulltext`/`summary` file SHALL become a `chunk_index = 0`
chunk row matching the file's existing `chunk_index = 0` embedding key,
so no vector is recomputed, re-keyed, or lost. The migration SHALL be
idempotent (re-runs skip already-migrated files) and SHALL be preceded by
a verified database snapshot.

#### Scenario: Vectors preserved without re-embedding

- **WHEN** the migration writes single chunks for `fulltext`/`summary`
  files
- **THEN** every pre-existing `contentEmbeddings` row still matches a
  chunk row by `(oparlKey, chunk_index)` and no embedding is recomputed

#### Scenario: Idempotent re-run

- **WHEN** the migration is executed again
- **THEN** files already carrying chunk rows are skipped and no duplicate
  rows are created

#### Scenario: Retrieval equality

- **WHEN** the same queries run before and after the migration
- **THEN** hybrid search results (file order, distances, match signals)
  are identical — verified separately for single-chunk and multi-chunk
  files

### Requirement: Chunk-level embeddings

Each chunk SHALL have its own content embedding keyed by file and chunk
index (upsert semantics). The content-vector recall SHALL match chunks by
cosine similarity and aggregate to file level by taking the best-matching
chunk per file; downstream fusion SHALL remain file-based and unchanged.

#### Scenario: Best chunk wins per file

- **WHEN** multiple chunks of one file match a query
- **THEN** the file appears once in recall with its best (lowest-distance)
  chunk

#### Scenario: Reranker sees the matching passage

- **WHEN** reranking runs over recalled files
- **THEN** the reranker input for a file is the text of its
  best-matching chunk, not a stored summary

### Requirement: Backfill over oversized documents

A backfill SHALL chunk and embed all stored documents whose OCR markdown
exceeds the cutoff (~10.200 files), resumable and idempotent: an
interrupted run continues with the remaining documents, and re-runs
replace rather than duplicate chunks and embeddings.

#### Scenario: Interrupted backfill resumes

- **WHEN** the backfill is stopped and restarted
- **THEN** already-processed documents are skipped and the remaining ones
  are processed

#### Scenario: Superseded summary embedding replaced

- **WHEN** a previously summarized (>cutoff) file is chunked
- **THEN** its chunk embeddings replace the single summary-based embedding
  for retrieval purposes
