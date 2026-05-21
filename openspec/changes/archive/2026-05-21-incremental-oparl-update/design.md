## Context

The current ``oparl_update`` script in ``references/oparl/oparl_update.py`` performs a full breadth‑first crawl of the OParl system on every execution. This results in unnecessary network traffic, duplicate file writes, and long runtimes, especially as the dataset grows. The OParl API supports a ``createdSince`` query parameter that returns only resources created or modified after a given timestamp. By leveraging this feature and persisting the most recent timestamp, we can turn the update process into an **incremental** crawl.

## Goals / Non-Goals

**Goals:**
- Fetch only new or modified OParl resources since the last successful run.
- Avoid re‑writing unchanged JSON files.
- Preserve the existing filename convention used by the fetch script.
- Gracefully handle list‑type responses and API pagination.
- Allow the user to interrupt the crawl (Ctrl‑C) without losing progress.

**Non‑Goals:**
- Changing the schema of the saved JSON files.
- Introducing new external dependencies beyond ``requests`` and the Python standard library.
- Implementing a full change‑detection system for every possible OParl field (only ``modified``/``created`` timestamps are considered).

## Decisions

1. **Timestamp persistence** – Store the newest ISO‑8601 timestamp in ``src/last_run.txt``. This file is read at start‑up and updated after the crawl finishes.
2. **API query** – Use ``?createdSince=<timestamp>`` on the ``bodies/0001`` collection to limit results. Other collections (consultations, papers, agendaItems) do not support the filter, so they are still crawled but guarded by ``should_save`` which compares timestamps before writing.
3. **File naming** – Re‑use the existing ``generate_descriptive_filename`` logic to keep filenames identical to those produced by ``oparl_fetch.py``.
4. **Graceful shutdown** – Wrap the main crawl in a ``try/except KeyboardInterrupt`` block and persist the latest timestamp even if the user aborts.
5. **Error resilience** – Catch ``AttributeError`` when a response is a list and treat it as having the current UTC time, ensuring the crawler never crashes on unexpected structures.

## Risks / Trade‑offs

- **Risk:** If the OParl API changes its pagination or timestamp field names, the incremental logic may miss updates.
  - *Mitigation:* Keep ``get_resource_timestamp`` tolerant (fallback to ``datetime.utcnow()``) and log any missing fields.
- **Risk:** Resources that are modified without changing the ``modified`` timestamp will not be re‑fetched.
  - *Mitigation:* Accept this limitation as part of the non‑goal; a deeper diff mechanism can be added later if required.
- **Risk:** The ``createdSince`` filter only applies to the top‑level bodies endpoint; other collections may still be crawled fully each run.
  - *Mitigation:* The ``should_save`` check prevents redundant writes, keeping I/O overhead low.

## Migration Plan

1. Add ``src/oparl_update.py`` (the new incremental script) and ``src/last_run.txt`` (initialised to the epoch on first run).
2. Run the script once to generate an initial full snapshot and create the timestamp file.
3. Subsequent executions will automatically fetch only newer resources.
4. No database migrations or schema changes are required.

## Open Questions

- Should we add support for the ``updatedSince`` parameter on other collections in a future iteration?
- Do we need to expose the timestamp via a CLI flag for debugging?

*Design decisions are based on the existing code base and OParl specification. No breaking changes to external consumers are introduced.*
