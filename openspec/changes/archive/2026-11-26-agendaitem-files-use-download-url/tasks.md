# Tasks

## 1. Backend fix — session file list uses downloadUrl

- [x] 1.1 In `src/pgIntentRouter.py` `meeting_scope_result`: change `_assoc_files()` and the meeting-files SELECT to read the File table's `downloadurl` column (`f."downloadurl" AS downloadurl`) instead of `f.data->>'downloadurl'`. Verify: the SELECT strings no longer contain `data->>'downloadurl'`.
- [x] 1.2 In `_file_row()`: drop the `oparlId` fallback so `"downloadurl"` carries the stored value only (`r.downloadurl`, None when missing); keep the separate `oparlId` field. Verify: grep shows no `or r.oparlId` on the downloadurl line.

## 2. Tests

- [x] 2.1 Add a unit test in `src/tests/test_unit_pgIntentRouter.py` covering `_file_row`: a row with `downloadurl="https://…/downloadfiles/x.pdf"` yields that URL in `downloadurl` (and `oparlId` unchanged); a row with `downloadurl=None` yields `downloadurl=None` — never the `oparlId`. Verify: `python -m pytest src/tests/test_unit_pgIntentRouter.py -q` passes.
- [x] 2.2 Run the existing meeting/gremium-related suites to confirm no regression: `python -m pytest src/tests/test_unit_pgIntentRouter.py src/tests/test_unit_staged_pipeline.py src/tests/test_unit_agendaExpansion.py -q`. Verify: all pass.

## 3. Consistency check

- [x] 3.1 Repo-wide grep for remaining `data->>'downloadurl'` consumers: confirm no other payload builder depends on the broken key (`rg "downloadurl'" src/`). Verify: any hits are listed and either out-of-scope-justified or fixed.
