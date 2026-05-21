## Why

The existing ``oparl_update`` script crawls the entire OParl system every run, which is inefficient and wastes bandwidth. An incremental update is needed to fetch only new or modified resources since the last successful run.

## What Changes

- Add timestamp tracking (`last_run.txt`).
- Query OParl collections with ``createdSince`` to limit results.
- Skip unchanged resources by comparing ``modified``/``created`` timestamps with existing files.
- Persist the newest timestamp after each crawl.
- Graceful handling of list responses and Ctrl‑C interruptions.
- Move the new script to ``src/oparl_update.py`` and keep the same filename conventions as the original fetch.

## Capabilities

### New Capabilities
- `incremental-oparl-update`: Enables efficient incremental crawling of OParl resources.

### Modified Capabilities
- None (no existing specs are altered).

## Impact

- Introduces new files: ``src/oparl_update.py`` and ``src/last_run.txt``.
- Updates logging and output directories (`ko_update/`, `ko_update_pdf/`).
- No external dependencies other than the existing ``requests`` library.
