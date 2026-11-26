# Design: oparl-endpoint-web2

## Context

Karlsruhe moved the OParl endpoint: web1.karlsruhe.de/… → web2.karlsruhe.de/… ("nothing else changes"). With web2 the `/ris/oparl` path is served correctly, so the legacy programmatic "/ris prefix restore" rewrite rule becomes unnecessary.

## Goals / Non-Goals

- Goals: endpoint defaults (config, crawler, frontend, snapshot) on web2; empty default rewrite list; rollback via env/config only.
- Non-Goals: no import-data migration (absolute OParl IDs in the DB stay valid; both host spellings fetch fine); no rewrite-mechanism removal.

## Decisions

1. DEFAULTS + `config/instance.yaml` → `https://web2.karlsruhe.de/ris/oparl`; `url_rewrites: []` (mechanism retained for other instances / rollback via `RISKI_OPARL__*`).
2. `oparlUpdate`: `DEFAULT_SYSTEM_URL` → web2; `fix_urls_in_data` keeps a `rules` parameter so the legacy web1 rule can be exercised per-instance; legacy web1 test coverage kept as explicit-rule cases.
3. Frontend static fallbacks (`instanceStore.js` oparlLink, `RelatedDocsList.vue` fallback URL) and the bundled snapshot (`sampleData.json`, 328 URLs) to web2.
4. Snapshot first: tag `snapshot-pre-web2-migration` (full tree incl. uncommitted search work) before any code change — user-requested rollback point.

## Migration Plan

Deploy code; optionally re-point running CRAWlers manually. Rollback without code: set `RISKI_OPARL__SYSTEM_URL=https://web1.karlsruhe.de/ris/oparl` + add the stuck web1 rewrite rule via instance config/env (`RISKI_OPARL__URL_REWRITES`).

## Risks / Trade-offs

- [Fetched DB entities still carry web1 oparlIds] → harmless: the URLs are used for identification/download balancing; file-proxy paths relative oparl keys; a full re-crawl later replaces them.
- [Karlsruhe reveals further behavioural differences] → snapshot tag for the exact revert point.

## Open Questions

None.
