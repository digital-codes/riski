# Tasks: oparl-endpoint-web2

## 1. Endpoint defaults

- [x] 1.1 instanceConfig DEFAULTS: `oparl.system_url` + `frontend.oparl_link` → web2; default `url_rewrites: []` (mechanism kept)
- [x] 1.2 `config/instance.yaml` mirror (system_url, oparl_link, `url_rewrites: []`)
- [x] 1.3 `oparlUpdate.DEFAULT_SYSTEM_URL` → web2; `rewrite_url`/`fix_urls_in_data` docs + explicit `rules` param for legacy web1 cases
- [x] 1.4 Tests: instanceConfig default web2; oparlUpdate: web2 URLs pass through with default rules + legacy web1 rule as explicit config rules; recursive fix via rules

## 2. Frontend + docs

- [x] 2.1 Frontend defaults: `instanceStore.js` oparlLink, `RelatedDocsList.vue` fallback URL, bundled snapshot `sampleData.json` (328 links) → web2
- [x] 2.2 README + code comments updated (web1 references only as legacy/rollback notes)

- [x] 2.3 DB data migration: `scripts/upgrade_oparl_urls.py` (all URL columns are `oparlId` + data JSONB) — dry-run report + --apply executed live: 111,763 rows rewritten (File 53150, Consultation 15217, AgendaItem 18983, Paper 13839, Meeting 2745, Membership 4050, Location 2928, Person/Org/Body/System/LegislativeTerm); keys/FKs untouched (structural, idempotent; re-run → 0)

## 3. Verification

- [x] 3.1 Post-migration checks: re-run reports "nothing to do"; File total unchanged (53150, zero web1 remnants, 53150 now web2); unit suite green (445 pass, 1 pre-existing unrelated failure); API gremium/health/stage-1 pass
 green (608 passed; 3 known pre-existing unrelated failures unchanged); API integration health/stage-1 pass
- [x] 3.2 Rollback path documented: `RISKI_OPARL__SYSTEM_URL` back to web1 + config `url_rewrites` entry (no code change)
