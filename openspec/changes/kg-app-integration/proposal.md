# Proposal

## Why

The kg layer is complete and live in PostgreSQL (`kg_*` tables: 8,301
pairs with verified outcomes, 15,400 statements with per-field failure
flags, 52,912 kg-topic tags on 25,343 files/6,266 request topics) — but
the riski app does not consume any of it yet: hybrid search ignores
topic tags as a *similarity* signal, the summarizer answers without
grounding statements, the intent router cannot focus documents by
topic, and follow-up questions ("was war dort 2023?") restart from
zero. Consuming the kg layer turns riski from "answer + document list"
into a navigable, grounded, conversational explainer — the `/wissen`
promise.

## What Changes

- **Related-documents pane via topic tags** — the top documents of a
  search trace their kg-topic tags; documents sharing ≥ 2 topics are
  offered as "thematically related" (score = shared-topic count with
  confidence weighting; no new model calls). Exposed on
  `/search`-responses and rendered as a link list (network-graph
  optional, not required).
- **Statement-grounded summarizer** — `pgResultSummarizer` receives
  extracted statements (topic, requested action, outcome, cost, dates,
  author) for its documents and is instructed to use them as grounding:
  the answer cites facts; fields flagged `_flags` (hallucination
  suspects, blanked by kgFlagFailures) are excluded from grounding
  wholesale. The prompt states evidence origin ("extrahierte
  Fakten aus Vorlage + Beschluss") and skips pairs whose cross-check
  failed and was not repaired.
- **Intent routing with topic tags** — `pgIntentRouter` gains a cheap
  topic-focus step: the query is embedded (bge-m3, existing embed
  endpoint oncerett) and compared against the 23 ris-ki topic
  descriptions; the top topic (score ≥ threshold, else none) scopes or
  boosts the retrieval for the intents that benefit (`search_topic`,
  `ask_decision_date`) — pure DB filter join over `File_tags_assoc`
  (scheme `kg-topic`), no changes to the intent configs.
- **Follow-up questions with authorisable state** — after each answer
  the backend emits **3–5 follow-up questions** (LLM-generated from the
  answer + statements, German, cheap decision-vertex prompt) and passes
  conversation state to the client as an **opaque sealed token**
  (auenBot pattern: `seal_state/open_state`, AES-GCM key derived from
  `STATE_TOKEN_SECRET` + session id, session-id-bound AAD, expiry) —
  the backend stays stateless (no shadow session DB); the frontend
  returns the token + chosen question on the next turn. Each follow-up
  turn reuses the previous round's statements/documents as context
  (token payload carries the minimum: query, top doc ids, statement
  refs) with size caps.

Capabilities covered (new specs):
- `kg-related-documents` (tags → related docs pane)
- `kg-grounded-summary` (statement-grounded summarizer prompt)
- `kg-topic-routing` (topic-tag-boosted intent routing)
- `kg-followup-questions` (sealed-state follow-up loop)

Existing capabilities NOT modified: `semantic-search` (hybrid recall
unchanged — topic filter/boost is applied as a post-recall weighting),
`result-summarizer` (gains an optional grounding block; prompt falls
back to today's behaviour when no statements exist per document),
`intent-routing` (new bolt-on step; existing intents unchanged),
`staged-results` (sessionId pattern reused, not replaced).

## Impact

- `src/apiServer.py` — /search response gains `related_documents`;
  `/ask` gains follow-up loop (`followups`, `state` token); new
    `/followup` entry point or reused `/ask` with state.
- `src/pgResultSummarizer.py` — grounding prompt + statement fetch
  (`kg_statements` JOIN `kg_pairs` on `paper_sid`).
- `src/pgIntentRouter.py` — topic-focus step (embed once per query;
  compare against 23 topic description vectors, cached).
- `src/kg/kgFollowups.py` (new) — follow-up generation + seal/open
  state helpers (port of auenBot `botQa.seal_state/open_state`,
  STATE_TOKEN_SECRET env).
- Frontend `app/` — follow-up chips (3–5 buttons) + related-docs list;
  no visual re-design.
- Config: `STATE_TOKEN_SECRET` env (warning when unset — auenBot
  pattern), nothing else.
