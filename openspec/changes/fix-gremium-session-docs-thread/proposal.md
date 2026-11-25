# Proposal: fix-gremium-session-docs-thread

## Why

Live observations, 2026-11-25:

1. **`ask_gremium_recent` returns "keine Sitzungsdokumente gefunden"** for
   "themen der letzten gemeinderatssitzung" and "letzte sitzung
   umweltausschuss" — although routing is CORRECT (Gemeinderat/Umweltausschus
   + latest held meeting). **Data artifact confirmed**: the DB's November
   2026 GR/UA meetings have 0 agenda items and 0 files (OParl imports the
   meeting rows long before their documents publish; the last GR meeting
   WITH documents is 20.10.2026 — 36 items). `resolve_gremium` picks the
   latest held meeting regardless of whether it carries any documents, so
   empty future/placeholder meetings generate the empty answer.
2. "themen der gemeinderatssitzung **im september**" — no month/year-based
   meeting resolution exists: month names (Akko) resolve nowhere; queries
   with a month without a year must default to the current year.
3. Picking a chip the first time fails: **"Follow-up fehlgeschlagen (base
   is not defined)"** — `app/src/api.js followup()` uses a stale
   `base`/`jsonHeaders` helper (duplicates exist; the shared `post()` is
   the working path).
4. The follow-up/context (thread) logic is perceived as wrong by the user
   and needs an explicit **state/sequence diagram** to reason about before
   any redesign.

## What Changes

- `ask_gremium_recent` SHALL resolve the latest held meeting **with
  documents**; placeholder meetings without documents are skipped with a
  clear note ("Dokumente für die Sitzung am … sind noch nicht
  veröffentlicht — siehe die letzte Sitzung mit Dokumenten vom …").
- New meeting-date extraction: German month names (+ optional year) in the
  query select the target meeting ("…im september" → Sept of the current
  year when the year is missing; "<<month>> letzte" variants). Ambiguity
  falls back to the current behaviour (latest held with docs) plus a note.
- Fix `app/src/api.js followup()` to use the shared `post()` helper (kill
  the stale `base`/`jsonHeaders` duplicate).
- Deliver `docs/kg-thread-state.md`: state + sequence diagram of the
  thread/chips/followup machinery (turn states, state token, clarification
  mode, chip mode, followups), plus identified logical issues to work on in
  a follow-up change (explicit no-redesign rule here).

## Capabilities

- **New Capabilities**: none
- **Modified Capabilities**:
  - `intent-routing` — gremium/meeting resolution: latest meeting WITH
    documents + month/year extraction from the query.
- **New capability** (small): none — the thread diagram is documentation-only.

## Impact

- Code: `src/pgIntentRouter.py` (`resolve_gremium`, `ask_gremium_recent`
  handler, `meeting_scope_result` notes), `app/src/api.js` (followup()).
  Docs: `docs/kg-thread-state.md` (new; state machine + sequence diagram).
- No API contract changes; frontend unchanged besides the followup() fix.
- Thread redesign explicitly OUT of this change (separate change once the
  diagram is reviewed).
