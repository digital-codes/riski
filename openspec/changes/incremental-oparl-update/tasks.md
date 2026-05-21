## Implementation Tasks

1. **Add timestamp handling**
   - Create `src/last_run.txt` if missing; initialize to epoch.
   - Implement `load_last_run` and `save_last_run` (already done).

2. **Update crawl logic**
   - Modify `crawl_oparl` to accept `start_from` and build initial queue with `createdSince` filter.
   - Track `latest_ts` during crawl and persist after completion.
   - Ensure pagination (`next` links) is followed automatically.

3. **File‑save guard**
   - Implement `should_save` to compare incoming resource timestamps with existing files.
   - Skip unchanged resources, logging the decision.

4. **Robust timestamp extraction**
   - Update `get_resource_timestamp` to handle list responses gracefully.
   - Add docstrings and fallback to `datetime.utcnow`.

5. **Graceful shutdown**
   - Wrap main crawl in `try/except KeyboardInterrupt` to allow Ctrl‑C and still persist progress.

6. **Move script**
   - Relocate the updated script to `src/oparl_update.py` (already placed).
   - Ensure output folders (`ko_update`, `ko_update_pdf`) match fetch script.

7. **Testing / verification**
   - Run the script once to generate `last_run.txt` and verify incremental behaviour.
   - Confirm that subsequent runs only fetch newer resources.

8. **Documentation**
   - Update README (optional) to mention the new incremental update command.

**Dependencies**: No new third‑party packages; uses existing `requests` and standard library.

**Acceptance criteria**
- Running `python src/oparl_update.py` completes without error.
- `last_run.txt` is created/updated.
- On a second run, no duplicate JSON files are written for unchanged resources.
- Ctrl‑C aborts cleanly and preserves the latest timestamp.
