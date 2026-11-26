# Proposal

## Why

In the meeting-scope (gremium session) answer, every file card link points at
the file's OParL entry URL (e.g. `https://web2.karlsruhe.de/ris/oparl/bodies/0001/files/680643`)
instead of the document PDF: the file-list assembly reads `data->>'downloadurl'`
from the JSON blob while the stored key is camelCase `downloadUrl`, so the value
is always NULL and the `or r.oparlId` fallback kicks in for every file. Users
who click a TOP document land on JSON metadata, not the document.

## What Changes

- The session-view file list (`meeting_scope_result`) resolves each file's
  download URL from the File row (by oparlId) instead of the JSON
  `downloadurl` key lookup with an `oparlId` fallback.
- File links in topic popups and `top_files` carry the real `downloadUrl`;
  files without one render as plain text (frontend already handles this).
- No change to file discovery, search pipeline, graph build, or frontend
  components.

## Capabilities

### New Capabilities

- (none)

### Modified Capabilities

- `intent-routing`: the "Gremium session scopes are head-of-chain minimal views"
  requirement already mandates download-URL document links; the delta pins the
  payload contract — file list entries carry the File row's `downloadurl`
  resolved by oparlId, and the OParL entry URL (`oparlId`) is never substituted
  as a document link.

## Impact

- `src/pgIntentRouter.py` (`meeting_scope_result`): `_file_row`, the two
  `downloadurl` SELECT expressions (agenda/Paper assoc files, meeting files).
- Tests in `src/tests/` covering the meeting-scope payload file entries.
- No API contract shape change (field stays `downloadurl`), no frontend change.
