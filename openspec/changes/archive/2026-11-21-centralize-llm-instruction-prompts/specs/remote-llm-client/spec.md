# Spec Delta

## ADDED Requirements

### Requirement: Chat prompt identification and registry resolution
Chat calls SHALL accept and forward prompt-id and call-id identification as required by the prompt registry policy. When called with a prompt id, the instruction part of the messages SHALL be resolved from the prompt catalog, and the call SHALL be recorded in the per-call debug log with its ids, endpoint, full prompt, and result. Calls lacking the identification parameters SHALL be flagged per the registry enforcement policy (error log; error raised in strict mode).

#### Scenario: Chat call with prompt id
- **WHEN** `chat()` is called with a prompt id and call id
- **THEN** the instruction part of the messages is supplied from the prompt catalog and the call is recorded in the call debug log with full prompt and result

#### Scenario: Chat call without ids flagged
- **WHEN** `chat()` is used for a prompt-bearing call without prompt id or call id
- **THEN** the omission is logged as an error (and the call is refused in strict mode)

### Requirement: Decision endpoint calls record identification
Calls to the SystemOne decision endpoint SHALL carry prompt id and call id identification and SHALL be recorded in the same per-call debug log with the full question payload and the returned answers.

#### Scenario: Decision call logged
- **WHEN** a decision-endpoint call is issued with prompt id and call id
- **THEN** the call debug log contains an entry with the ids, the full state/questions payload, and the returned answers

## MODIFIED Requirements

### Requirement: Chat completion
The client SHALL send chat messages to a chat endpoint configured by environment variables (base URL and model, with local-first defaults) and return the parsed response dictionary. It SHALL optionally request a thinking/reasoning mode of the endpoint. The response dictionary SHALL identify the prompt id and call id of the originating call when provided.

#### Scenario: Successful chat call
- **WHEN** `chat()` is called with a list of messages against a running endpoint
- **THEN** a dictionary containing the model's reply is returned

#### Scenario: Thinking mode requested
- **WHEN** `chat()` is called with thinking mode enabled against an endpoint that supports it
- **THEN** the request includes the thinking option and the response dictionary is still returned

#### Scenario: Response echoes call identification
- **WHEN** `chat()` is called with prompt id and call id
- **THEN** the returned dictionary contains those identifiers for downstream correlation
