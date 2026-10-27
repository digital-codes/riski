# Spec Delta

## ADDED Requirements

### Requirement: Instance-configured crawl targets and transport

The incremental updater SHALL take the crawl root (OParl system URL), the
bodies to crawl, page size, request delay and URL-rewrite rules from the
instance configuration (see the `instance-config` capability) instead of
module constants; the CLI flags SHALL override the config, and absent both,
today's Karlsruhe defaults apply. The bodies SHALL be enumerated from the
OParl system object (optionally filtered by configured body IDs) rather
than a hardcoded body ID.

#### Scenario: Crawl against another backend
- **WHEN** the updater runs with an instance config naming a different
  OParl system URL and data directories
- **THEN** all 9+ collections of every discovered body are crawled with the
  same incremental mechanics (modified_since-first, page validation,
  fallback ladder) into the configured directories

#### Scenario: Karlsruhe default unchanged
- **WHEN** no instance config and no CLI flags are given
- **THEN** the crawl targets today's Karlsruhe system, folders and
  transport parameters exactly
