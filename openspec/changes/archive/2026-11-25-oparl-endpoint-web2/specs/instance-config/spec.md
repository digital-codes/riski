# instance-config Delta

## MODIFIED Requirements

### Requirement: Instance configuration file and resolution order
The Karlsruhe DEFAULTS in `src/instanceConfig.py` and `config/instance.yaml`
point `oparl.system_url` and `frontend.oparl_link` at the CURRENT OParl
endpoint (`https://web2.karlsruhe.de/ris/oparl`, change
`oparl-endpoint-web2`; previously `web1.karlsruhe.de`). The default
`oparl.url_rewrites` list is EMPTY: the web2 endpoint serves proper
`/ris/oparl` paths, so the legacy "/ris prefix restore" rule is not needed.
The rewrites MECHANISM stays — other instances or endpoint regressions
SHALL re-add rules via the instance config (env override
`RISKI_OPARL__URL_REWRITES` / config file) without code changes.

#### Scenario: Karlsruhe defaults point at web2

- **WHEN** no instance config overrides are set
- **THEN** the crawler, file proxies and frontend oparl links use
  `https://web2.karlsruhe.de/ris/oparl` and no `/ris`-prefix rewrite runs

#### Scenario: Legacy endpoint via override

- **WHEN** an instance override points the system URL back at web1
- **THEN** the crawler honours the override and an instance-config
  `url_rewrites` entry can restore the `/ris` prefix without code changes
