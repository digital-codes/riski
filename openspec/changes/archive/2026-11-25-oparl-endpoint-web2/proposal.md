# Proposal: oparl-endpoint-web2

## Why

Karlsruhe changed its main OParl endpoint from web1.karlsruhe.de/… to web2.karlsruhe.de/… ("nothing else changes"). With web2, the `/ris/oparl` path is served correctly, which previously had to be fixed programmatically (the `url_rewrites` rule restored the missing `/ris` prefix on web1 URLs).

## What Changes

- Default `system_url` / `oparl_link` move to `https://web2.karlsruhe.de/ris/oparl` (instanceConfig DEFAULTS, config/instance.yaml, oparlUpdate DEFAULT_SYSTEM_URL).
- The web1 `/ris`-prefix `url_rewrites` rule is REMOVED (web2 serves proper `/ris/oparl` paths). The rewrite MECHANISM stays (ordered regex list in the instance config) for other instances/needs.
- All hardcoded `web1.karlsruhe.de` mentions in code, tests, comments and file-proxy docs move to web2.
- No API/UI contract changes; env overrides (`RISKI_OPARL__SYSTEM_URL`) keep working for rollback.

## Capabilities

- **Modified Capabilities**: `instance-config` — OParl endpoint defaults & url-rewrite notes; the second-instance story is unaffected (config file/env still win).

## Impact

- Code: `src/instanceConfig.py` (DEFAULTS), `config/instance.yaml`, `src/oparlUpdate.py` (`DEFAULT_SYSTEM_URL`, doc/comment references), `src/apiServer.py` (file-proxy comment), tests asserting the default or the web1 fix (`test_unit_instanceConfig.py`, `test_unit_oparlUpdate.py` — the web1 `/ris` fix test becomes a legacy-rewrite case of the mechanism).
- DB/data: fetched URLs already hold absolute OParl IDs; no migration (the crawler rewrites both hosts' URLs if fed old links).
- Rollback: `RISKI_OPARL__SYSTEM_URL=https://web1.karlsruhe.de/ris/oparl` + re-adding the stuck rewrite rule via instance config — no code revert needed.
