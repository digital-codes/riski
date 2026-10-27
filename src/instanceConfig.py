"""Deployment-instance configuration (change: instance-agnostic-config).

One config file (`config/instance.yaml` by default; path overridable via
``RISKI_INSTANCE_CONFIG``) plus an environment overlay
(``RISKI_<SECTION>__<KEY>``, double underscore splits nesting) makes the
pipeline runnable against a second OParl backend (new database, new
download folders, another city) without touching source code.

Resolution order per value: environment variable → instance config file →
code-level defaults (``DEFAULTS`` — the current Karlsruhe deployment). When
neither env override nor config file is present, every value equals
today's behavior, so existing deployments and tests need no config file.

Known second-instance target (verification, see design D6/open questions):
Dresden — https://oparl.dresden.de/system (public OParl 1.1, single body
"0001", SOMACOS Session); requires its own database name and download
folders, never shared with the Karlsruhe instance.
"""

# Dual-mode import support.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import copy
import functools
import os
from pathlib import Path
from typing import Any, Dict

import yaml

DEFAULT_CONFIG_PATH = "config/instance.yaml"
ENV_PREFIX = "RISKI_"
ENV_NESTING_SEP = "__"

# Code-level defaults == today's Karlsruhe deployment (single source of
# truth; an absent instance config reproduces current behavior exactly).
DEFAULTS: Dict[str, Dict[str, Any]] = {
    "oparl": {
        # OParl 1.1 system URL and crawl scope
        "system_url": "https://web1.karlsruhe.de/ris/oparl",
        "bodies": [],  # empty = crawl every body the system reports
        "page_limit": 1000,
        "request_delay": 0.25,
        # ordered regex rewrites applied to fetched URLs (Karlsruhe serves
        # download links that need the /ris prefix restored — same effect
        # as the former fix_karlsruhe_url)
        "url_rewrites": [
            {"pattern": r"(https?://web1\.karlsruhe\.de)(?!/ris(/|$))",
             "replacement": r"\1/ris"},
        ],
    },
    "paths": {
        "json_dir": "/mnt_ai/data/odd26/ris/ko",
        "pdf_dir": "/mnt_ai/data/odd26/ris/ko_pdf",
        "extracted_dir": "/mnt_ai/data/odd26/ris/ko_extracted",
        "sums_dir": "/mnt_ai/data/odd26/ris/ko_sums",
        "log_filename": "ko_update_crawl.log",
        # per-deployment feature-config files (referenced, not duplicated)
        "intents_file": "config/intents.yaml",
        "lexical_stop_terms_file": "config/lexical_stop_terms.txt",
        "meeting_web_url_file": "config/meeting_web_url.txt",
    },
    "geo": {
        # street/district source data (see pgAddStreets/pgAddDistricts)
        "streets_file": "docs/streetNames.json",
        "districts_file": "references/geo/stadtteile.geojson",
        "district_columns": {"name": "NAME", "number": "NUMMER"},
        # city name for the map view and the address-block boilerplate
        # heuristic (house number + postal code + city)
        "city": "Karlsruhe",
        "map_center": [49.0069, 8.4037],
        "map_zoom": 12,
    },
    "rules": {
        # deterministic geo-gate address-block regex city (geoGate)
        "address_regex_city": "Karlsruhe",
        # venue-boilerplate patterns stripped before file geo matching
        # (pgAddFileGeoRefs); Karlsruhe's town-hall venue line
        "venue_noise": [
            r"(Bürgerssa?al\s*[,\s]+\s*)?Rath(aus|auses)(\s+(?:am|auf dem))?\s+Marktplatz\b",
        ],
        # Karlsruhe product-code convention in Haushalt document types
        "haushalt_codes": True,
        # organization classification: ordered (regex → label) rules
        "org_classification": [
            {"pattern": r"^ortschaftsrat\b", "label": "Ortschaftsrat"},
            {"pattern": r"ausschuss", "label": "Ausschuss"},
            {"pattern": r"beirat", "label": "Beirat und Stiftung"},
            {"pattern": r"^gemeinderat\b", "label": "Gemeinderat"},
            {"pattern": r"^ortsverwaltung\b", "label": "Ortsverwaltung"},
            {"pattern": r"^dezernat\b", "label": "Dezernat"},
            {"pattern": r"\beamt\b|amt für|amt$", "label": "Amt"},
            {"pattern": r"^eigenbetrieb\b", "label": "Eigenbetrieb"},
            {"pattern": r"fraktion", "label": "Fraktion"},
            {"pattern": r"gmbh|ggmbh|gmbh \(| ag\b|verbund|stadtwerke|volkswohnung|betriebe",
             "label": "Beteiligungsgesellschaft"},
            {"pattern": r"^stabsstelle\b", "label": "Stabsstelle"},
            {"pattern": r"^personalrat\b", "label": "Personalrat"},
        ],
        "org_classification_fallback": "Sonstiges",
    },
    "web": {
        "cors_origins": [
            "http://localhost:5173", "http://localhost:4173",
            "http://localhost:5199",
        ],
        # Karlsruhe calendar convention: base URL + "termin-<nr>" + TOP anchor
        "meeting_url_template": "{base}termin-{number}",
    },
    "frontend": {
        "title": "RISKI Karlsruhe",
        "heading": "Das Karlsruher Ratsinformationssystem — erklärt.",
        "footer": ("riski — das Karlsruher Ratsinformationssystem erklären "
                   "… offene OParl-Daten der Stadt Karlsruhe"),
        "default_query": ("wo liegt die Governance für Digitalisierung "
                          "bei der Stadt Karlsruhe"),
        "oparl_link": "https://web1.karlsruhe.de/ris/oparl",
        "imprint_url": "/#/impressum",
        "privacy_url": "/#/datenschutz",
        "data_sources": [
            {"name": "Sitzungskalender der Stadt Karlsruhe",
             "url": "https://sitzungskalender.karlsruhe.de/db/ratsinformation/start"},
        ],
    },
}


def config_path() -> str:
    """Path of the instance config file (env ``RISKI_INSTANCE_CONFIG``)."""
    return os.getenv("RISKI_INSTANCE_CONFIG") or DEFAULT_CONFIG_PATH


def _env_overrides() -> Dict[str, Any]:
    """Nested dict from ``RISKI_<SECTION>__<KEY>`` environment variables
    (values parsed as YAML scalars so numbers/bools/lists work; a parse
    failure keeps the raw string)."""
    out: Dict[str, Any] = {}
    for key, value in os.environ.items():
        if not key.startswith(ENV_PREFIX) or ENV_NESTING_SEP not in key:
            continue
        path = key[len(ENV_PREFIX):].lower().split(ENV_NESTING_SEP)
        node = out
        for part in path[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                break  # conflicting nesting; ignore this variable
        else:
            try:
                import yaml as _y

                parsed = _y.safe_load(value)
            except Exception:  # noqa: BLE001 - keep raw text on parse errors
                parsed = value
            node[path[-1]] = parsed
    return out


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay wins per leaf key; nested dicts merge recursively."""
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _load_config_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(
            f"instance config {path!r} must be a mapping of sections")
    return data


def _build_config() -> Dict[str, Any]:
    cfg = copy.deepcopy(DEFAULTS)
    path = config_path()
    if os.path.exists(path):
        cfg = _deep_merge(cfg, _load_config_file(path))
    cfg = _deep_merge(cfg, _env_overrides())
    return cfg


@functools.lru_cache(maxsize=1)
def get_instance_config() -> Dict[str, Any]:
    """The merged instance configuration (cached per process).

    Tests can call ``get_instance_config.cache_clear()`` after mutating the
    environment or writing a config file."""
    return _build_config()


def section(name: str) -> Dict[str, Any]:
    """A single config section, merged over its defaults."""
    return get_instance_config().get(name) or {}


def clear_cache() -> None:
    """Drop the cached config (config file / env changed under us)."""
    get_instance_config.cache_clear()
