# Spec Delta

## Purpose

Shared client for remote model services (chat, embeddings, OCR) against OpenAI-compatible endpoints, replacing the bespoke per-script HTTP calls of the legacy scripts with one configurable, retry-correct client.

## ADDED Requirements

### Requirement: Chat completion
The client SHALL send chat messages to a chat endpoint configured by environment variables (base URL and model, with local-first defaults) and return the parsed response dictionary. It SHALL optionally request a thinking/reasoning mode of the endpoint.

#### Scenario: Successful chat call
- **WHEN** `chat()` is called with a list of messages against a running endpoint
- **THEN** a dictionary containing the model's reply is returned

#### Scenario: Thinking mode requested
- **WHEN** `chat()` is called with thinking mode enabled against an endpoint that supports it
- **THEN** the request includes the thinking option and the response dictionary is still returned

### Requirement: Embedding
The client SHALL embed text via the configured embedding endpoint and return the embedding vector as a list of finite floats of the configured dimension. Invalid endpoint responses SHALL raise a descriptive error rather than returning dummy data.

#### Scenario: Embed returns normalized vector
- **WHEN** `embed()` is called with a non-empty string against a running embedding endpoint
- **THEN** the result is a list of finite numbers with the expected dimension and (for a normalized model) unit length

#### Scenario: Endpoint error propagates
- **WHEN** the embedding endpoint returns an HTTP error status after retries are exhausted
- **THEN** an exception is raised and no dummy/fabricated vector is returned

### Requirement: Retry semantics
The client SHALL retry failed requests up to a configurable number of attempts with a delay between attempts. Retries SHALL only end in a dummy fallback where the caller contract permits it (chat), and never for embeddings.

#### Scenario: Transient failure is retried
- **WHEN** the endpoint fails once and succeeds on the next attempt within the retry budget
- **THEN** the successful response is returned

### Requirement: OCR client
The client SHALL expose OCR for PDF documents, sending base64-encoded document content to the configured OCR endpoint and returning the parsed OCR result, with retry on rate-limit responses.

#### Scenario: OCR of a PDF
- **WHEN** the OCR function is called with the bytes of a PDF and valid endpoint configuration
- **THEN** a parsed OCR result (markdown text and pages) is returned

#### Scenario: Rate limit is retried
- **WHEN** the OCR endpoint responds with HTTP 429
- **THEN** the request is retried after waiting instead of failing immediately
