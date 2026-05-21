## 1. Setup

- [ ] 1.1 Create `last_run.txt` file handling utilities (read/write timestamp)
- [ ] 1.2 Add command‑line argument `--created-since` to the existing fetch script
- [ ] 1.3 Register SIGINT handler for graceful shutdown and cursor persistence

## 2. Core Implementation

- [ ] 2.1 Modify fetch logic to append `?createdSince=<timestamp>` when the argument is provided
- [ ] 2.2 Implement idempotent upsert into PostgreSQL using `INSERT ... ON CONFLICT DO UPDATE`
- [ ] 2.3 Ensure the script updates `last_run.txt` with the maximum timestamp seen in each successful run

## 3. Fallback & Validation

- [ ] 3.1 Add detection for endpoints that do not support `createdSince` and fallback to full fetch with warning
- [ ] 3.2 Validate timestamp format on read and write, handling corrupted `last_run.txt`

## 4. Testing & Documentation

- [ ] 4.1 Write unit tests for timestamp utilities and graceful shutdown behavior
- [ ] 4.2 Add integration tests mocking OParl responses with incremental data
- [ ] 4.3 Update README with usage instructions and configuration details
