# Design: fix-gremium-session-docs-thread

## Context

Three live findings (2026-11-25) with established facts:

- **Data artifact**: `resolve_gremium` selects the latest held meeting row;
  OParl inserts meeting rows before publishing agenda items/files. Today:
  GR 24.11 + UA 17.11 (+ GR 15.12, UA 12.11/2027 …) have 0 agenda items and
  0 files, while GR 20.10 has 36. `meeting_scope_result` therefore renders
  an empty session with the note "keine Sitzungsdokumente gefunden".
- **No month/date parsing** exists for the gremium scope ("im september"
  is ignored), and
- `app/src/api.js followup()` references an undefined `base`/`jsonHeaders`
  (stale duplicate of the shared `post()` helper), producing the first-chip
  error "Follow-up fehlgeschlagen (base is not defined)".

The thread/followup machinery itself (`_thread_turn`, chips mode,
clarification mode, `classify_thread_turn`, sealed-state tokens) is only
documented — its deliberate redesign is a follow-up change on top of the
new diagram.

## Goals / Non-Goals

**Goals**
- Session scope skips document-less meetings (note instead of empty result).
- Month/year meeting filter for `ask_gremium_recent` (current-year default).
- Frontend followup() call fixed through the shared `post()`.
- `docs/kg-thread-state.md`: state machine + sequence diagram of
  thread/chips/followups, feeding the follow-up redesign.

**Non-Goals**
- No redesign of thread/context logic here.
- No import-pipeline change: the document-lag artifact is corrected at the
  query layer (imports would need their own fix if the observed lag in the
  OParl backend grows).

## Decisions

1. **Document-check at resolution time** (`resolve_gremium`): after picking
   the latest held meeting, verify the session has documents
   (`EXISTS AgendaItem.meetingSid OR File__meeting__Meeting`). Skip empty
   rows going backwards (bounded — max 3 skipped meetings) and carry a
   `skipped_note` with the placeholder date(s). No pipeline change and no
   schema change; bounded probe avoids pathological scan without indexes.
   *Alternative*: pre-compute per-meeting document counts in a materialized
   view during import — overkill for the current corpus size.

2. **Month parsing as a gremium slot pre-step** (`resolve_gremium` optional
   `month`, `year` args): a German month regex over the query
   ("(im )?september( \d{4})?"), month names January–December + abbrevs.
   Defaults: month has no year → current year. Selection: latest held
   meeting with documents in that month/year; if none → explicit response
   ("Für <Org> liegen für September 2026 keine Sitzungsunterlagen vor.")
   with `empty=True` — no silent fallback to another month. The chip-class
   slots (`config/intents.yaml`) are unchanged: this is handler-level
   extraction, minimizing decoder re-tuning.

3. **Frontend followup()** routes through the shared `post()` helper
   (`app/src/api.js`) — same request shape (`question`, `state`,
   `session_id`, `top_k`), one error-handling path.

4. **Thread documentation** (`docs/kg-thread-state.md`): state machine
   (idle → normal turns / chips mode / clarification mode / reset), token
   sealing/opening, and query→session→response sequence; includes the
   observations ("Follow-up fehlgeschlagen" bug fixed here; deeper logic
   issues listed for the follow-up change).

## Risks / Trade-offs

- [Skipping empty meetings changes behavior for genuinely document-less
  meetings] → typed above: bounded skip + explicit note; the empty answer
  was never useful.
- [Month filter raises expectations for months whose imports lag] → the
  explicit `empty` message names most-recent published months instead of
  masking.
- [Suffix walk on month regex false positives ("september" inside names)]
  → word-boundary regex; names like company names are in other slots.

## Migration Plan

Backend query-layer change + frontend call fix + new docs; no DB/schema
migration, rollback = revert.

## Extension: head-of-chain minimal gremium view (live feedback)

User decision (2026-11-25): the gremium session view shows ONLY topics +
session files — no graph, timeline, summary, related hints, followups; and
a gremium session query ALWAYS resets the thread context (head of chain).

1. **LLM gremium/date extraction**: new prompt `gremium-meeting-extract`
   (instruction_prompts.json): strict JSON `{gremium: <free text>,
   relative: "letzte"|"date", month: <1-12|0>, year: <int?>}`; fall back to
   the existing vocabulary/regex path (`extract_meeting_date`, slot vocab
   scan) when the call fails. One chat call only on the gremium path
   (never for themensuche).
2. **`_kg_enrich` skips meeting scope**: `answer_mode == "list_topics"`
   → no related_documents, no clarification, no followups (the LLM call
   removed in task 6.1 already covers the empty-summary case; this makes
   it explicit by intent).
3. **Thread reset**: /ask with `ask_gremium_recent` forces `new_thread()`
   (origin="search") and issues no sealed token for the prior context —
   `_thread_turn` is bypassed.
4. **UI**: WorkPage `list_topics` branch already skips timeline/summary;
   additionally skip `fetchGraph` + GeoMap + RelatedHintsCard/FollowupChips
   rendering for that answer mode (card order spec updated accordingly).

## Open Questions

None blocking. The state diagram doc is the deliverable that the planned
thread-redesign change will start from.
