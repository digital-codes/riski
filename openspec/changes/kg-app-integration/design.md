# Design

## Context

kg layer complete and live in PostgreSQL (`kg_pairs` 8,301 pairs,
`kg_statements` 15,400 rows with `_flags`/`_flagged` quality blocks,
52,912 kg-topic tag associations on 25,343 files). riski's existing
surface: `semantic-search` (hybrid signals + facets),
`result-summarizer` (query-guided, teaser- and content-layer), staged
results over an in-memory `sessionId` store (no persistence),
`intent-routing` (3 intents + fallback, decision model `pgIntentRouter`).
The `/wissen` page promises a knowledge layer that none of these
consume yet.

Operator requirements (2026-11-20): integrate tags as related-document
signal, statement-ground the summarizer, let intent routing profit from
topic tags, and add 3–5 follow-up questions per answer with backend
state carried in a sealed token — referencing
`digital-codes/auenBot` (`botCtl/botQa.seal_state` pattern,
`metis-decision-routing` branch) as the state transport.

## Goals / Non-Goals

**Goals:**
- Zero-model related docs via shared tags (cheap, deterministic).
- Statement-grounded summaries with flag-aware exclusion.
- Topic-focus bolt-on for intent routing.
- Stateless follow-up loop with sealed session tokens (3–5 questions).
- App surfaces (apiServer response fields; chips + related-docs list
  in the frontend).

**Non-Goals:**
- No changes to hybrid search internals (discovery recall unchanged).
- No new model deployments (reuse OLC / greenpt metis / CCLLM).
- No visual redesign; minimal frontend additions (chips + list).
- No per-user auth/personalization (session id + secret only, as auenBot).

## Decisions

### D1: Related-documents as a post-recall SQL join, no index
`File_tags_assoc` is keyed `(oparl_key, tag_id, scheme)`. A query per
response fetches the TOP document's tag set, then joins other documents
sharing ≥ 2 tags; the join is two indexed lookups on 52k rows
(no new index needed — `oparl_key` is indexed via existing partial
weight). Relatedness score = Σ shared_tag_confidence × count, capped
at 10 related docs. **Deduplicated against the top list** (the pane is
for *other* documents). Cost ≈ 2 SQL queries per `/search` response.
Frontend renders a simple list (network-graph integration deferred).
Alternative considered: materializing a `kg_tag_cooccurrence` pair
table — rejected for v1 since the co-occurrence is cheap to compute
lazily and updates whenever tags change; revisit if the pane becomes
heavily used (>10 % of sessions).

### D2: Grounding block injected into the prompt via session data
`ResultSummarizer` optionally takes `grounding: list[pair_statement]`
built by the API layer when a document's `paper_sid` has
`kg_statements` rows. Each grounding entry is a fixed-format block:

```
Für [Datei 12345]: Thema: … · Gefordert: … · Ergebnis: …
Kosten: … · Zeitraum: … · Einbringer: …
```

Fields carrying `_flags` / present in `_flagged` are omitted — except
those explicitly marked `__unsicher` in `_flagged` note text
(kgFlagFailures guarantees values are blanked; the note is the only
carrier). Prompt instruction: "Nutze, wenn relevant, diese
extrahierten Fakten als Beleg — verlasse dich nur auf geprüfte
Angaben." The provenance footer gains
`grounding=kg-StatementLayer/pairs=N` when ≥ 1 document was grounded.
Fallback: no pair → no block → today's behaviour. Prompt token cost:
~150 tokens/document, well within the OLC_SUMMARY budget.

### D3: Topic focus as a *pattern*, not a rewrite of intent routing
A two-class topic vector cache is built once at startup: bge-m3 embed
of the 23 topic descriptions (from `config/kg_vocabulary.yaml`, single
source of truth held by kgTagSchema) and stored in memory. Per query,
`pgIntentRouter` reuses the existing embed call (bge-m3 already used
by hybrid search) and adds a dot-product against the 23 cached vectors —
cos ≥ 0.55 marks the intent's `topic_focus`. Re-ranking model: boost =
multiplicative score multiplier (×1.2) on documents carrying the focus
tag (constant, no priority inversion — the boost never overtakes
lexical top hits). All 3 current intents unaffected; `search_topic`
and `ask_decision_date` consume the focus via the retrieval join.

### D4: Follow-up loop with a sealed state token (auenBot pattern, ported)
`src/kg/kgFollowups.py` implements
`seal_state(state, session_id)`/`open_state(token, session_id)` — an
AES-GCM blob over `state + _ts`, key =
`HMAC-SHA256(STATE_TOKEN_SECRET, session_id)`, AAD = session id, token
`v1.<b64url>`; expiry sealed in `_ts`,
`STATE_TOKEN_MAX_AGE` (default 7d). Payload minimised:
`{q0, top_docs: [oparlKey ≤ 8], stmt_refs: [pair_id ≤ 6], topic?: …}`.
Flow:

1. `/search` (with summary) or `/ask` response includes
   `followups: [3–5 questions]` + `state: <sealed token>`.
2. Client renders chips; clicking one calls `/ask` with
   `question + state` (POST body).
3. `/ask` opens the token → scoped retrieval/grounding → new answer →
   new followups → new sealed token (fresh `_ts`, chain continues).
4. Backend stateless apart from the existing audit rows
   (`oparlUpdateRuns`-style). A follow-up question assembly uses the
   cheaps decision model (mis/reuse of greenpt metis) or CCLLM —
   whichever is cheaper to run per call; the questions are 5-a-side
   and are effectively bounded (operator bounds 3–5).

Question generation prompt (CCLLM by default): given the answer plus
two or three statement facts and the top kg-topic labels, ask 3–5
targeted follow-up questions in German. Size hard-capped at 5; fewer
allowed when aspects are exhausted. No personalization, no user
history beyond the sealed token.

### D4b: Clarification pass for short/fuzzy queries
Verified live: short queries like "staatstheater" DO resolve through the
trigram lexical signal (`Bad.Staatstheater`, `CDU Staatstheater` … all
lexical=True at scores 0.25–0.38), but the resulting documents can fan
out over multiple kg topics — cultural venue vs cost debates vs visitor
statistics. The follow-up loop (D4) therefore gains a **clarification
mode**: when the top documents span ≥ 3 distinct kg-topic clusters, the
first response presents clustered options instead of/alongside the
summary — "Meintest du das Badische Staatstheater (Culture), oder die
GfK-Kosten-Debatte (Economy), oder die Besucherzahlen-Frage (Culture/Sport)?".
Each option is a follow-up chip generated from the cluster's dominant
statement topic, sealed into the same state token; the next turn replays
with the chosen cluster as the topic focus (D3). Trigger: top-5 docs
span ≥3 distinct topics AND the query is ≤3 tokens (short/fuzzy class) —
or the query has no embed match at all (lexical-only recall). This is
the auenBot options-flow (options + followup pick) mapped onto kg topics.

### D5: Security posture (auerBot lessons adopted)
* `STATE_TOKEN_SECRET` must be set; without it, seal/open uses a
  random per-process secret and logs a warning (auenBot prints the
  same). Tokens survive only within one process lifetime — operator
  must supply a secret in production.
* Session id validation: `^[A-Za-z0-9_-]{1,64}$` (auenBot `_SESSION_RE`).
* All new endpoints sanitize the input as `/search` does today
  (letters/umlauts/numbers/punct, ≤ 250 chars).
* No state in cookies; the frontend stores the token in memory.

### D6: Frontend surface — chips and related docs pane
`FollowupChips.vue` (new component under `app/src/components/`):
renders up to 5 chips; on click re-issues `/ask` with the sealed `state`.
`RelatedDocsList.vue`: the ≤ 10 related documents as a
download-linking list (link text: file name; tooltip: shared-topic
list) at the bottom of the work page. Reuses app-wide styles; no new
network calls on the client except the clicks themselves.

### D7: Query threads with followup-intent detection (added 2026-11-20)
The chip flow becomes the *entry* of a sequenced conversation with
**threads** (Aufeinanderfolgende Fragen, die zusammen gehören):

* **Thread start (chips mode)** — occurs when (a) the app loads, (b)
  the intent router indicates a non-thematic intent
  (`ask_gremium_recent` "wann war die letzte Sitzung", decision-date
  lookups etc.), or (c) the intent is `search_topic` but hybrid recall
  yields no document above the confidence floor. In these cases the
  server responds with a **new history sequence** (`thread_id` fresh,
  `turn=0`), proposes 5 kg-topic chips (clarification options from
  `_kg_enrich`'s cluster detection, falling back to the global topic
  list), and asks the user to make a more defined request — **no other
  cards are presented** (timeline, graph, related docs and summary are
  suppressed; the frontend renders the chips sheet plain).
* **Chip pick** — amends the initial query with the chip description
  (`chip.topic` + `chip.example`) and starts a *new search* which is
  evaluated through the normal card surface; **chips disappear** (the
  thread is established — thread_id stays, turn=1).
* **Followup detection on subsequent turns** — when the intent router
  sees a query with **no clear target** (anaphoric prompts like "welche
  umweltauswirkungen hat das", "warum haben die grünen dem
  zugestimmt" — signals: deictic pronouns ("das", "die"), no head noun
  that maps to a kg-topic vector, intent router confidence below the
  topic threshold), it is classified as `thread_followup`. The
  **effective query is the concatenation of the prior turn's query and
  the new one** (oldest→newest, dot separated, max retained = per D8
  window), run through the normal pipeline. The summarizer's prompt
  notes that prior turns provide context ("Vorherige Fragen des
  Nutzers in diesem Thema: …") so answer continuity survives
  concatenation.
* **Thread break** — a query whose intent resolves with clear target
  (topic fire ≥ threshold, gremium/decision slots filled) starts a
  **new thread**: fresh `thread_id`, turn reset, empty history.
* **Hard budget — 5 rounds** — after the 5th turn in one thread the
  next query is treated as a break (new thread) regardless of intent
  confidence; the user gets an informational note ("Neues Thema —
  Thread begrenzt auf 5 Nachfragen").
* State stays in the existing sealed token (D4/D5) — the augmentations
  are `thread_id`, `turns` (list of queries, oldest first) and
  `origin` ("chips"|"search"); tokens rotate per turn as before.

### D8: Followup mechanics, frontend surface
* `/search` and `/ask` accept an optional `thread` field; when present
  and valid (token + session id) the endpoint opens it before the
  intent classification and hands `turns` + `turn_count` to the
  router, which decides followup-vs-break **before** recall runs.
* Concatenation is capped: `turns[-3:]` (rolling window, ≥ effective
  ≤ 3 query strings padded to ≤ 750 chars total after sanitization);
  the *topic focus* (D3) is computed over the concatenated string, the
  retrieval boost retains the turn-1 topic so the thread doesn't
  drift.
* Frontend (`WorkPage.vue`):
  - on chips-mode responses render ONLY the chips sheet + the
    "make it more defined" hint (hide summary/timeline/graph/related),
  - on chip pick run a normal `/search` (cards show), dropping the
    sheet,
  - on regular turns send `{query, thread: {state, sessionId}}`,
  - after 5 turns the server's "new thread" note renders as an inline
    notice above the cards,
  - a small "Neues Thema" reset button exists after ≥2 turns even
    without a hard break (user-initiated thread break).
* No LLM classifier for followup detection — it is a deterministic
  router rule (deictic lexicon + no-topic-fire + low router
  confidence). Cheap, auditable, no extra model calls.

## Risks / Trade-offs

- [Token payloads can carry statement references that later get
  flagged] → on open, `open_state` returns refs; the follow-up
  pipeline re-reads statements from PG at answer time (never trusts
  token content as fact source) — flagged fields are excluded
  regardless of when sealing happened.
- [Topic boost could narrow results unintentionally] → boost-only per
  D3 with multiplier 1.2; lexical top hits stay ahead of unboosted
  candidates; focus is also displayed on the answer card ("Schwerpunkt:
  Mobilität") so narrowing is visible and explainable.
- [Related pane quality depends on tag strictness (0.5 threshold)] →
  53 flagged & 23 distinct topics give disciplined co-occurrence;
  evaluation gate (spec accept): "≥ 2 shared topics" filter catches
  accidental hallway co-tagging.
- [‖ KG statements contain only 8,266 request + 791 response
  statements (others are authors/links)] → grounding limited to
  request/response; the block references pair_id for traceability.
- [Follow-up model cost] → the chip prompt reuses the decision model;
  ~0.3 s/pair; 5 questions per answer bounded.

## Migration Plan

Additive: new endpoint fields, new component, new helper module. The
`/search` and `/ask` API responses keep all current fields (constraint
for API clients). Rollback = route to the no-kg response shape (config
flag `KG_APP_INTEGRATION=0` short-circuits the new fields, path kept
during rollout).

## Open Questions

- Should related-documents be ranked with a time component
  (newest-first per shared topic?) or pure score? (Proposal: pure
  score; defer a recency tie-breaker until user feedback.)
- Whether `followups` for the `/search` flow should ship immediately at
  stage 1 results (before the summary completes) or with the summary
  card (proposal: with the summary — the questions reference its
  content).
