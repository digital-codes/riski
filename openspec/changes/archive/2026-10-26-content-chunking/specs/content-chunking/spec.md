# Spec Delta

## Purpose

Chunk-basierte Inhaltsverarbeitung: OCR-Markdown wird heading-bewusst in
Klartext-Chunks zerlegt, pro Chunk eingebettet und als Abruf- und
Belegebene („Auszug aus Datei X, Abschnitt N“) vorgehalten — statt
Dokumente auf 8.000 Zeichen zu kappen oder LLM-Zusammenfassungen als
Retrieval-Grundlage zu verwenden.

## ADDED Requirements

### Requirement: Heading-aware chunking of OCR markdown

The ingestion pipeline SHALL chunk OCR markdown of documents larger than
the size cutoff into plaintext chunks of ~6.000–8.000 characters, with
chunk boundaries preferred at markdown headings. Each chunk SHALL record
its chunk index and character offset range within the document. Files at
or below the cutoff SHALL NOT be re-processed; their existing single
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
