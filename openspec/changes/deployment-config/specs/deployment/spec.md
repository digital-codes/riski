# Spec Delta

## ADDED Requirements

### Requirement: Versioned deployment configuration

The operational configuration for the API process, the proxy and the
scheduled pipeline SHALL be kept as versioned files in a dedicated
deployment directory, each stating its rationale, with a document mapping
repository files to host paths and a rollout/verification procedure.

#### Scenario: Host configuration is traceable
- **WHEN** an operator consults the deployment directory
- **THEN** each deployed artifact's origin, host location and rationale is
  documented, and a diff step verifies repo/host agreement

### Requirement: Proxy contract

The proxy SHALL terminate TLS and forward to the loopback-bound API with a
request timeout exceeding the API's longest legitimate request (LLM-bound),
preserving host and forwarded headers as the app's proxy-trust logic
expects, and SHALL apply security headers (HSTS, content-type sniffing
protection, referrer policy, frame policy) and coarse connection-level
throttling as the outer layer of a two-layer rate-control design.

#### Scenario: Long LLM requests survive the proxy
- **WHEN** a request takes longer than the default proxy timeout (e.g. a
  90 s summary)
- **THEN** the proxy waits up to its configured longer timeout instead of
  returning 502

#### Scenario: Security headers present
- **WHEN** a response is served through the proxy
- **THEN** HSTS, `X-Content-Type-Options`, `Referrer-Policy` and a
  frame-ancestors policy are present

### Requirement: Scheduled pipeline execution

The nightly pipeline SHALL be scheduled via a documented cron entry that
takes an exclusive non-blocking run lock, captures output to a log, and
notifies the operator (mail) on critical failure or partial success,
including the run report path.

#### Scenario: Overlapping runs are prevented at the scheduler level
- **WHEN** a previous run is still holding the lock at trigger time
- **THEN** the cron invocation exits immediately without starting work

#### Scenario: Operator notified on failure
- **WHEN** the run exits with the critical-failure or partial-success code
- **THEN** mail is sent containing the exit code and the report path
