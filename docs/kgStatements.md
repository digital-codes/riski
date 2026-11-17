# kgStatements — request/response statement extraction

Stage 4 (tasks 5.1/5.2): for each identified pair, two JSON-constrained
LLM calls (design D5/D11) extract concise German grounding statements.
Output goes into the SQLite `statements` table; processed pairs move
`identified → statements` (resume-safe — re-runs skip them).

## Extraction fields

**Request stage** (source: request + modification documents):

| field | note |
|---|---|
| topic | topic/title of the request |
| request_type | from the DB (papertype), not model-guessed |
| meeting_date | DB meeting date (the session where discussed, NOT file date) |
| document_id / file_names | from the DB pair document list |
| author | joined from the `kgAuthors` stage (empty = unknown) |
| intended_impact | intended impact / outcome |
| audience | who is affected |
| action_actor | who should take action |
| requested_action | the precise requested action |
| start_date / end_date | only when stated in the text |
| expected_benefit / involved_cost | only when stated (else "") |
| source_refs | list of document ids/names the facts came from |

**Response stage** (source: verified protocol/agenda response documents +
the DB outcome as a preamble):

| field | note |
|---|---|
| response_type | zugestimmt/abgelehnt/vertagt/verwiesen/zur_kenntnis/erledigt/… |
| result | the result of the response |
| planned_action / action_executor | which action, who executes |
| expected_cost / start_date / end_date | only when stated |
| request_modifications | changes to the request ("" if none) |
| dependencies_constraints | conditions (third-party funding, Haushaltssperre, …) |
| outcome_db | the DB-derived outcome (metadata) |

**Strict rules in both prompts:** ALL field contents in German (the
model must not translate to English — an earlier mistral run produced
mixed-language output until the instruction was added), empty string
when the source has nothing, never invent facts.

## Modification chains

Modification pairs (Änderungs-/Ergänzungsantrag) are linked to their
original request pair deterministically: difflib title similarity
(ratio ≥ 0.75, temporal proximity ±1 year adds 0.1) over the
**Paper** names from PostgreSQL — attachment names are boilerplate and
unusable. Result: `statements` row with stage `link`:
`{"modifies": <pair_key>, "title_ratio": …}`.

## Usage

```bash
# sample
python -m src.kg.kgStatements --limit 5 --model mistral:latest

# full run (default model granite4.2:8b; see kgModelSelect for QA)
python -m src.kg.kgStatements --model mistral:latest

# responses only / requests only
python -m src.kg.kgStatements --skip-request
python -m src.kg.kgStatements --skip-response
```

**Checkpointing:** the store commits every N pairs (`--commit-every`,
default 5) and processed pairs are skipped on restart
(`status='statements'`) — the bulk run can be interrupted and resumed
at any time without repeating LLM work. See `docs/kgStatus.md` for the
current checkpoint state and the exact resume command.

## Model + context notes (verified 2026-11-17)

* The ollama runner keeps the KV cache in VRAM while a model is hot; a
  full 80k default context crowd-outs other work. `kgRemote` therefore
  calls the **native** `/api/chat` with `options.num_ctx` (default
  16384; smoke test ran at 8192 → 6.7 GB VRAM instead of 15.9 GB).
  `KgRemote.unload(model)` frees a stuck runner (keep_alive=0).
* **Stop the previous model before switching** — three hot models
  share GPU/CPU and make everything slow (`curl …/api/generate -d
  '{"model":…,"keep_alive":0}'`).
* Bench on a German extraction prompt (8k ctx):
  granite4.2:8b 74 s/2295 tok, qwen3.5:4b 59 s/2191 tok,
  granite4.2:3b 26 s/1121 tok, mistral:latest **9 s/93 tok** (most
  concise). mistral was chosen for bulk extraction; kgModelSelect
  (task 7.1) does the formal quality comparison.

## Output (SQLite)

| table | contents |
|---|---|
| `statements` | stage `request`/`response` per pair (fields JSON), stage `author`, stage `link` |
| `pairs.status` | `identified → statements` after extraction |

Observed: request stage extracts real facts with empty fields where
absent; response stage is skipped when the pair has no response
document (structurally rare — 230 verified protocol attachments).
