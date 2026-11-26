# Design

## Context

The meeting-scope (gremium session) answer assembles its file lists in
`src/pgIntentRouter.py` (`meeting_scope_result`):

- `_assoc_files()` SELECTs files per association and reads the download URL
  as `f.data->>'downloadurl'` — but the OParL JSON blob stores the field
  camelCase (`downloadUrl`), so this expression always yields NULL.
- `_file_row()` then substitutes the file's OParL entry URL:
  `"downloadurl": r.downloadurl or r.oparlId` — every entry ends up with
  `…/files/<id>` as its link.
- The same broken expression is used for meeting files (`File__meeting__Meeting`,
  the "events" case), and `top_files` propagates the result.

The File table has a first-class `downloadurl` column, populated uniformly
at import (the `/file-proxy` route already selects it and streams bytes).
The frontend (`TopicList.vue` popup) renders `file.downloadurl` as the href
and falls back to plain text when it is absent — no frontend change needed.

## Goals / Non-Goals

**Goals:**
- File-list entries in the session answer carry the File row's real
  `downloadurl` (resolved by oparlId), never the OParL entry URL.

**Non-Goals:**
- No change to file discovery/search/recall, graph build, expansion, or
  any other payload.
- No frontend changes (TopicList already handles present/absent
  `downloadurl` correctly).
- No change to the `/file-proxy` route or related-document lists.

## Decisions

- **Read the stored column, not the JSON blob.** The file-list SELECTs use
  the File table's `downloadurl` column (`f."downloadurl"`), which is
  uniformly populated, instead of `f.data->>'downloadurl'` (wrong key,
  always NULL). Alternative: read `f.data->>'downloadUrl'` (camelCase) —
  rejected because the raw blob is not the source of truth for other
  routes and the column avoids depending on blob shape.
- **No `oparlId` fallback.** `_file_row` returns `downloadurl` as-is (None
  when missing). The OParL entry URL remains available in its own
  `oparlId` field for the detail panel's "OParl-Datensatz öffnen" button,
  which is labeled as the record, not the document.

## Risks / Trade-offs

- [A few File rows might genuinely lack a `downloadurl` column value]
  → Those entries render as plain text (existing frontend behavior); no
  metadata link masquerades as a download.
- [Other code paths selecting `data->>'downloadurl'`] → Out of scope;
  a repo-wide check is part of verification to confirm no other consumer
  depends on the broken expression.

## Migration Plan

None — pure payload-value fix, no schema/API shape change. Rollback is
reverting the one file.

## Open Questions

None.
