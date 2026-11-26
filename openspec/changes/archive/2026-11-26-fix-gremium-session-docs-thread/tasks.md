# Tasks: fix-gremium-session-docs-thread

## 1. Session scope skips document-less meetings

- [x] 1.1 `resolve_gremium` (src/pgIntentRouter.py): document-check (EXISTS AgendaItem / File__meeting__Meeting) on the selected meeting; skip empty rows backwards (≤ 3) and collect `skipped_note` with the skipped meeting date(s)
- [x] 1.2 `meeting_scope_result`: carry the `skipped_note` into the response notes; keep "keine Sitzungsdokumente gefunden" only for a real fallback where even the older meeting has nothing
- [x] 1.3 Unit test: latest meeting empty → older meeting with docs selected + note names the skipped date; all-empty → explicit empty response

## 2. Month/year meeting resolution

- [x] 2.1 German month regex (Januar/…/Dezember + abbreviations) with optional 4-digit year; missing year → current year; word-boundary matching
- [x] 2.2 `resolve_gremium(month=…, year=…)` filter: latest held meeting with documents in that month/year; none → `empty=True` response naming the month and neighbouring months with documents (no silent fallback)
- [x] 2.3 `ask_gremium_recent` handler passes month/year from the raw query; unit tests "themen der gemeinderatssitzung im september" (held + docs → that meeting), "im september 2025" (empty → explicit message), chip flow unaffected

## 3. Frontend followup call bug

- [x] 3.1 `app/src/api.js`: `followup()` routes through the shared `post()` helper; remove the stale `base`/`jsonHeaders` duplicate (fix for "Follow-up fehlgeschlagen (base is not defined)")
- [x] 3.2 `vite build` green; live check: chip pick issues `/api/followup` and returns (no ReferenceError)

## 4. Thread/followup state documentation deliverable

- [x] 4.1 New `docs/kg-thread-state.md`: state machine (normal turn / chips mode / clarification mode / forced-break reset), sealed-state token lifecycle (seal → open → advance), component boundaries (apiServer `_thread_turn`, kgFollowups, classify_thread_turn, FollowupChips + RelatedHintsCard on the UI side)
- [x] 4.2 Mermaid sequence diagram: user query → /search (thread turn) → weak recall vs recall-confident branch → chips vs thread state seeding → followup/chip pick → /followup → new token; plus identified logic issues list (input for the follow-up redesign change; no code changes to the thread logic in this change)

## 5. Verification + docs

- [x] 5.1 Integration test: "themen der letzten gemeinderatssitzung" resolves to the latest GR meeting WITH documents (today: 20.10.2026) and carries the skipped note — currently returns documents > 0
- [x] 5.2 Full unit suite + README/intent-routing doc sync (gremium time-scope note, followup call not user-visible documentation; KG thread doc link from README if a thread section exists)

## 6. Follow-up discoveries during apply (live verification)

- [x] 6.1 Fast followups LLM call on meeting-scope answers skipped (`_kg_enrich` gates generate_followups on existing summary text) — /ask list_topics has zero model calls besides the intent decode
- [x] 6.2 Graph expansion merge cost O(n²): per-child partials merged once after the loop in `meeting_scope_result` (9.1 s → 2.4 s on GR 20.10)
- [x] 6.3 `/ask "themen letzte sitzung gr"` 13.4 s → 3.4 s live; integration test test_gremium_documentless_skipped passes on the fixed path
