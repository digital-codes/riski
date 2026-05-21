## Context

The current data ingestion pipeline periodically loads full data snapshots into PostgreSQL, which results in high network bandwidth usage, excessive database load, and potential downtime. The system already supports fetching data via OParl endpoints that can filter by `createdSince`. We aim to leverage this capability to implement incremental updates.

## Goals / Non-Goals

**Goals:**
- Enable incremental synchronization of PostgreSQL tables by fetching only new or modified records since the last successful run.
- Reduce data transfer volume and processing time.
- Ensure safe shutdown and resume capability via persisted cursor state.

**Non-Goals:**
- Redesign of the entire data model or migration of existing historical data.
- Support for complex conflict resolution beyond timestamp-based upserts.

## Decisions

1. **Timestamp Tracking:** Store the latest processed timestamp in a plain‑text file (`last_run.txt`) at the project root. This file is read at start of each run and updated after successful processing.
2. **CreatedSince Query:** When the OParl endpoint supports the `createdSince` parameter, append it to the request URL to fetch only newer resources.
3. **Idempotent Upserts:** Use PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` semantics to upsert records based on primary key, ensuring re‑processing of already‑ingested rows does not cause duplication.
4. **Graceful Shutdown:** Register a `SIGINT` handler to write the current cursor to `last_run.txt` before exiting, preserving progress on user interruption.
5. **Fallback Behavior:** If `createdSince` is not supported, fall back to full fetch but log a warning; this maintains functional correctness while highlighting the need for endpoint support.

## Risks / Trade-offs

- **Risk:** Missing or inconsistent timestamp columns in source data could cause records to be skipped or duplicated.
  - *Mitigation:* Require that source tables include a reliable `updated_at` or `created_at` column indexed for efficient queries.
- **Risk:** The `last_run.txt` file could become corrupted.
  - *Mitigation:* Write updates atomically (write to temp file then rename) and validate timestamp format on read.
- **Risk:** Endpoint may return out‑of‑order records.
  - *Mitigation:* Use the maximum timestamp observed in the batch as the new cursor, ensuring no newer records are missed.

## Migration Plan

1. Deploy script changes behind a feature flag.
2. Run a one‑off full sync to populate initial data.
3. Enable incremental mode; monitor logs for any missed records.
4. Roll back by disabling the flag if regressions are observed.

## Open Questions

- Do all OParl endpoints in use support the `createdSince` filter reliably?
- Should we support a configurable cursor storage location (e.g., S3) for distributed environments?
