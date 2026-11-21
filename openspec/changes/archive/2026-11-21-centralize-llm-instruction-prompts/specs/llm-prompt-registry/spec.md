# Spec Delta

## Purpose

Central registry for LLM instruction prompts with call-level identification: every prompt-bearing call to a `/chat/completions` or `/systemone` endpoint resolves its instruction part from a JSON catalog, carries a prompt id and a call id, and is fully inspectable in a per-call debug log including results.

## ADDED Requirements

### Requirement: Instruction prompt catalog
The system SHALL maintain a JSON catalog file in the project `config/` directory that contains the instruction part of every distinct prompt sent to endpoints ending in `/chat/completions` or `/systemone`, each stored as a verbatim instruction text identified by a stable, unique prompt id. Instruction parts for these endpoint types MUST NOT be inlined verbatim in module code; they SHALL be stored only in the catalog.

#### Scenario: Call site resolves instruction from catalog
- **WHEN** a script issues a prompt-bearing call to a `/chat/completions` or `/systemone` endpoint
- **THEN** the instruction part of the prompt is taken from the catalog entry named by the call's prompt id

#### Scenario: Catalog covers all existing call sites
- **WHEN** any of the migrated production call sites (including its per-intent/per-question template variants) resolves its instruction
- **THEN** a matching catalog entry exists whose text is verbatim-identical to the previously inlined instruction text

### Requirement: Catalog loading with endpoint configuration
The shared model-client layer SHALL load the prompt catalog the same way it loads endpoint base URLs and keys, at startup, from a documented default path with an environment-variable path override available. A missing or unparseable catalog file SHALL be reported through the error log, and calls whose prompt id cannot then be resolved SHALL be flagged as errors.

#### Scenario: Catalog loads at startup
- **WHEN** the client layer starts normally
- **THEN** the catalog is loaded once and prompt lookups use the in-memory copy

#### Scenario: Catalog file missing
- **WHEN** the catalog file does not exist or cannot be parsed
- **THEN** an error is logged at startup and any call referring to a prompt id fails resolution with an error log entry instead of a silent fallback

### Requirement: Call identification
Every prompt-bearing call to a `/chat/completions` or `/systemone` endpoint SHALL carry a prompt id referencing the catalog instruction and a call id of the form `<script>.<function>.<call-index>` identifying the origin (script name, function, and call site index). Both ids SHALL be recorded in the per-call debug log entry.

#### Scenario: Identifiable call logged
- **WHEN** a prompt-bearing call that includes prompt id and call id is issued
- **THEN** the call's debug-log entry contains the call id, the prompt id, the endpoint, and the model

#### Scenario: Call id pinpoints origin
- **WHEN** an entry with a given call id is inspected in the debug log
- **THEN** the call id uniquely identifies the script, function, and call site that issued the request

### Requirement: Missing-id enforcement
A prompt-bearing call to one of those endpoint types issued without a prompt id or without a call id MUST be flagged and logged as an error. In default (soft) mode the call still proceeds after logging; in strict mode - selected via environment variable - the client layer MUST refuse the request before it is sent.

#### Scenario: Call without params flagged as error
- **WHEN** a prompt-bearing call omits the prompt id, the call id, or both
- **THEN** an error-level log entry (and an error-flushed entry in the call debug log) records the missing identifiers, without changing the call's result by default

#### Scenario: Strict mode refuses non-compliant call
- **WHEN** strict enforcement is enabled and a prompt-bearing call lacks prompt id or call id
- **THEN** the request is not sent and an error is raised identifying the offending call site

### Requirement: Per-call debug log with results
The client layer SHALL record every prompt-bearing call in a fixed debug log file inside the project `log/` directory as single-line, append-safe JSON entries containing an ISO-8601 timestamp, call id, prompt id, endpoint, model, the full prompt (resolved instruction and data messages), and the full model result. The log SHALL be enabled for all prompt-bearing calls by default with an opt-out via an environment variable.

#### Scenario: Full request inspectable
- **WHEN** any prompt-bearing call completes
- **THEN** the log contains one entry from which the full prompt (instruction and data) and ids can be reconstructed

#### Scenario: Result inspectable
- **WHEN** a prompt-bearing call returns a result
- **THEN** the corresponding entry includes the full parsed result (content/answers) as returned to the caller

#### Scenario: Log opt-out
- **WHEN** the opt-out environment variable is set before the client layer starts
- **THEN** no call-log entries are written and call behavior is unchanged

### Requirement: Call log must not affect calls
The call debug log MUST NOT alter the traced call's processing or result in any way, and log-write failures MUST be reported through the regular error logging without affecting the call.

#### Scenario: Log failure does not break calls
- **WHEN** writing a debug entry fails (e.g. disk error)
- **THEN** the call result is unaffected and the failure is only reported via the regular logging
