# kgTags — ris-ki file-tags assignment

Stage 2 of the kg prototype (uses the tag table seeded by
`kgTagSchema.py`). Classifies the identified pair documents against the
23 German ris-ki tag descriptions with confidence values and assignment
strictness:

* **vector tier** — bge-m3 embedding of the document head (≤ 6 chunks,
  ≤ 12,000 chars; teaser fallback) vs. each tag description
* **strict threshold** — assignments below `MIN_CONFIDENCE`
  (default 0.55, CLI `--min-confidence`) are not written; low
  confidence is never forced, untagged docs are counted in the summary
* **qualifiers** — phrase detection from the tag's `qualifier_hint`
  (Building Construction / Road construction: Neubau, Sanierung =
  reconstruction, Erweiterung, Ausbau, Rückbau); note the
  vocabularies' warning that "Sanierung" is reconstruction, not
  maintenance
* provenance per assignment is `vector` in v1 — an LLM tier follows in
  the kgStatements stage for the untagged remainder

## Usage

```bash
# strictness + sample size (default threshold 0.55)
python -m src.kg.kgTags --limit 50

# all pair documents (resumable: file_tags is keyed (doc, tag) upsert)
python -m src.kg.kgTags

# re-run with a looser threshold (re-writes existing rows)
python -m src.kg.kgTags --min-confidence 0.45

# print the tag table
python -m src.kg.kgTagSchema --list
```

## Output (SQLite)

| table | contents |
|---|---|
| `file_tags` | doc → tag with confidence, optional qualifier, provenance |
| `tags` | 23 ris-ki tags with descriptions (seed) |

Console output prints the progress counter with ≤ 10s intervals and a
final `tagged/untagged` summary.

## Observed behaviour (50-doc sample, 2026-11-17)

- 6/50 tagged, 7 assignments — the strict threshold keeps most
  documents untagged until the LLM tier (planned in kgStatements).
- Typical assignments: Climate with 0.57–0.62, city development,
  Childcare, Work/Labour at ~0.55–0.56.
