# Spec Delta

## Purpose

Provides the single shared database access layer for the refactored package, replacing per-script connection boilerplate: credential resolution, a process-wide engine, schema inspection, generic upsert, and read-only role support.

## ADDED Requirements

### Requirement: Credential resolution
The database layer SHALL resolve connection credentials in order: an explicit `POSTGRES_URL` environment variable, then a `private.py` module (`DB_USER`, `DB_PWD`, `DB_HOST`, `DB_NAME`), then `DB_*` environment variables, then safe local defaults. Read-only modules SHALL additionally support `RO_USER`/`RO_PWD` (falling back to the read/write credentials) and MUST use them for query-only connections.

#### Scenario: Explicit URL wins
- **WHEN** `POSTGRES_URL` is set in the environment
- **THEN** connections use exactly that URL, ignoring all other credential sources

#### Scenario: Environment fallback
- **WHEN** no `POSTGRES_URL` and no importable `private.py` exist but `DB_USER`/`DB_PWD` are set
- **THEN** the engine connects using those environment variables against the configured database and host

### Requirement: Process-wide engine singleton
The layer SHALL expose a function returning a lazily-created, reusable engine (connection-pool health checks enabled) so that repeated calls return the same engine for the same URL. Requesting an engine for a different URL SHALL return a separate engine without disturbing the default.

#### Scenario: Repeated calls share the engine
- **WHEN** the engine getter is called twice with no arguments in one process
- **THEN** both calls return the same engine instance and a test query (`SELECT 1`) succeeds

### Requirement: Schema inspection and generic upsert
The layer SHALL provide a predicate that reports whether a table exists in the connected database, and a generic upsert helper that inserts a row or updates it on primary-key conflict, committing on success.

#### Scenario: Upsert inserts then updates
- **WHEN** the upsert helper is called twice with the same primary key and different values for an existing table
- **THEN** the table contains one row for that key whose values match the second call

#### Scenario: Missing table is detected
- **WHEN** the existence predicate is asked about a table name that was never created
- **THEN** it returns false without raising

### Requirement: Valid structured logging
The layer SHALL provide named loggers using format strings that are valid for the logging framework; emitting a log record MUST NOT raise.

#### Scenario: Log emission does not raise
- **WHEN** a message is logged at any level through the layer's logger factory
- **THEN** the record is formatted and emitted without an exception

### Requirement: Connection context manager
The layer SHALL provide a context manager that yields a connection from the default engine and guarantees commit on normal exit, rollback on exception, and close in all cases.

#### Scenario: Rollback on error
- **WHEN** an exception is raised inside the connection context manager after executing a write
- **THEN** the write is rolled back and the connection is closed
