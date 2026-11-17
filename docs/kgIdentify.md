# kgIdentify — request/response pair identification

Stage 1 of the kg prototype (change `kg-statement-extraction`). Discovers
request/response document pairs around "Gemeinderat" decisions from the
OParl database structure **alone** (read-only, RO user) and writes them
into a local SQLite store, including the **full input-document list per
pair** (document id, file name, pair role) and per-pair chunk counts.

## Usage

```bash
# sample: first N candidates only (console round-trip check)
python -m src.kg.kgIdentify --sample 20

# full run (resumable: already stored pairs are skipped)
python -m src.kg.kgIdentify

# discard earlier results for this stage and reprocess
python -m src.kg.kgIdentify --store results/kg_statements.sqlite --force
```

## How it works

* `Paper.papertype` → normalized request type via `config/kg_vocabulary.yaml`
  (`papertypes` table, case/hyphen/wording-tolerant patterns).
* `Paper → Paper__consultation__Consultation → Consultation → Meeting /
  AgendaItem`. Only meetings matching `meeting_scope.meeting_name_patterns`
  (Gemeinderat) are kept; other bodies are excluded and **counted in the
  summary output** (never silently dropped).
* Outcome (zugestimmt / abgelehnt / beschlossen / kenntnisnahme / vertagt /
  erledigt / verwiesen) is normalized from `AgendaItem.result` through the
  `results` table.
* Confidence + provenance per pair: `signal` = `db-column` (all structural
  columns decided it), `db-partial` (some missing — later escalated by
  `kgEscalate`, tiers 2/3).
* Documents: paper files → role `request` (or `modification` for
  Änderungs-/Ergänzungsanträge), agenda-item files → role `response`.
  Chunk counts per file → `file_meta` (used by the statistics report).

## Output (SQLite)

| table | contents |
|---|---|
| `pairs` | pair key = `<paper_oparl_id>\|<meeting_oparl_id>`, request type, outcome, meeting date, confidence, signal, status |
| `pair_documents` | full document list (doc id = oparlId, filename, role) |
| `file_meta` | chunk counts per paired document |

Status reporting goes to console with a maximum 10s silence interval.

## Statistics report

After a full run, `kgStats.py` (or table inspection) verifies the plan
assumptions (documents ≤ 5 chunks, response counts, modification chains)
from `file_meta` / `pair_documents`.

## Notes

* Unknown papertypes/wording are reported as `excluded_class` in the run
  summary — extend `config/kg_vocabulary.yaml` rather than the code.
* The database can also be reconstructed from web-scraping with sparse
  tables; the script needs only the columns named in the traversal above
  and degrades to lower confidence instead of failing.
