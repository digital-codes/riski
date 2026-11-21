# api-debug-tracing Specification

## Purpose

Environment-gated end-to-end debug tracing of the API request flow: incoming queries, intent routing decisions with reasons, and responses sent to the frontend, written to a fixed log file with timestamp and source identification.

## Requirements

### Requirement: Activation via environment variable
The debug trace SHALL be activated by setting an environment variable (truthy value of `RISKI_DEBUG_TRACE`) before starting the uvicorn API service, and SHALL be disabled by default. When disabled, the API service MUST behave identically to the current system and MUST NOT create or write to the debug log file.

#### Scenario: Enabled at startup
- **WHEN** the API service is started with `RISKI_DEBUG_TRACE=1` and a query request arrives
- **THEN** debug entries are written to the fixed debug log file

#### Scenario: Disabled (default)
- **WHEN** the API service is started without `RISKI_DEBUG_TRACE` (or with a falsy value)
- **THEN** no debug log file is created and responses are byte-compatible with the untraced system

#### Scenario: Runtime activation is not required
- **WHEN** the environment variable is set or changed after the service has started
- **THEN** the service continues with the activation state captured at startup (no restart-free toggling required)

### Requirement: Fixed log file with structured entries
When enabled, all scripts involved in API interaction SHALL append debug entries to a single fixed log file inside the project's `log/` directory. Each entry MUST contain an ISO-8601 timestamp with timezone, the source script/module name, and a machine-readable event payload. Entries MUST be single-line and append-safe for concurrent writers.

#### Scenario: Entry structure
- **WHEN** any traced event occurs
- **THEN** one line is appended containing timestamp, source, and event fields (e.g. JSON with `ts`, `src`, `event` keys)

#### Scenario: Log file location is stable
- **WHEN** the trace is enabled and the service handles requests
- **THEN** entries accumulate in the fixed file under the project `log/` directory (e.g. `log/api_debug.log`), independent of the working directory the service was started from

#### Scenario: Concurrent writers do not corrupt the log
- **WHEN** multiple request handlers write entries concurrently
- **THEN** every entry remains a complete, parseable single line

### Requirement: Incoming query tracing
For every API request carrying a user query, the trace MUST record the endpoint, a sanitized form of the user query, the relevant request parameters, and a request identifier that links all trace entries of that request.

#### Scenario: Ask request traced
- **WHEN** a client sends a query to a query endpoint (e.g. `/ask`, `/search`, `/followup`)
- **THEN** the trace contains an entry with the endpoint, the sanitized query text, key request parameters, and the request identifier

#### Scenario: Non-query endpoints
- **WHEN** a client calls a non-query endpoint (e.g. `/health`)
- **THEN** such calls MAY be traced with endpoint and request identifier but MUST NOT be required to carry a query payload

### Requirement: Intent route decision tracing
For every request whose processing involves intent classification, the trace MUST record the selected intent, the decision reason(s) (including confidence, matched signals, slot resolutions, and fallback ladder steps), and any mode-affecting outcome such as clarification mode or thread-turn classification.

#### Scenario: Routed query
- **WHEN** a query is classified and routed to an intent handler
- **THEN** the trace contains an entry with the selected intent and the reasons for the selection

#### Scenario: Fallback and clarification paths
- **WHEN** empty results trigger a fallback ladder step or a multi-cluster short-fuzzy query triggers clarification mode
- **THEN** the trace records which fallback step was taken or that clarification mode was activated, with its reason

#### Scenario: Follow-up thread turn
- **WHEN** a follow-up request is classified as continuing or breaking a thread
- **THEN** the trace records the thread-turn classification and its reason

### Requirement: Frontend response tracing
For every response sent towards the frontend from a query endpoint, the trace MUST record the endpoint, response mode, and a compact summary of the payload (such as result counts, presence of summary/related documents/follow-up chips), linked to the request identifier. The entry MUST NOT contain the full raw response body.

#### Scenario: Normal response
- **WHEN** a query endpoint returns a result payload to the frontend
- **THEN** the trace contains an entry with endpoint, mode, request identifier, and payload summary fields

#### Scenario: Clarification response
- **WHEN** the system responds in clarification/chips mode
- **THEN** the response trace entry records the mode as clarification and the chips offered

### Requirement: Trace payload hygiene
Trace payloads MUST exclude secrets and credentials, MUST apply per-field size caps so long texts (queries, summaries) are truncated, and MUST NOT alter the traced request's processing or response in any way.

#### Scenario: Long query text
- **WHEN** a traced user query exceeds the per-field size cap
- **THEN** the traced value is truncated with an ellipsis marker while processing uses the full query

#### Scenario: Trace failure does not break requests
- **WHEN** writing a debug entry fails (e.g. disk error)
- **THEN** the request processing continues unaffected and the failure is reported only through the service's regular error logging
