"""Author and seed the ris-ki file-tag schema.

The schema identifier ``https://ris-ki.de/ris/file-tags`` is an opaque
namespace (no content served — verified 2026-11-17: 404/403 on all
paths), so the tag descriptions are authored here from
docs/kg_building.md's tag list plus domain knowledge, in German. The
seed does two things on one run:

1. writes/updates ``config/kg_vocabulary.yaml`` section ``file_tags``
   (single source of truth for the later stages)
2. seeds the SQLite ``tags`` table

When the ris-ki schema becomes reachable, replace the ``TAGS`` dict —
the pipeline (kgTags) picks the table up unchanged.

Usage::

    python -m src.kg.kgTagSchema              # seed yaml + sqlite
    python -m src.kg.kgTagSchema --list       # print tag descriptions
"""

from __future__ import annotations

try:  # script-mode import bootstrap
    import _bootstrap  # noqa: F401
except ImportError:
    pass

import argparse
import textwrap

from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker
from src.kg.kgVocab import DEFAULT_PATH

# tag → German description used as the classification anchor (spec:
# tag-table-first). Qualifier hints describe sub-distinctions the tag
# supports (careful: "Sanierung" means reconstruction, NOT maintenance).
TAGS: dict[str, dict[str, str | None]] = {
    "Mobility": {
        "description": (
            "Verkehr und Mobilität: ÖPNV, Straßenbahn, Buslinien, "
            "Fahrradverkehr, Fußverkehr, Verkehrsberuhigung, "
            "Verkehrsmanagement und neue Mobilitätsangebote."
        ),
        "qualifier_hint": None,
    },
    "Economy": {
        "description": (
            "Wirtschaftsförderung, lokale Unternehmen, Handel, "
            "Gewerbe, Handwerk, Tourismus und Standortentwicklung."
        ),
        "qualifier_hint": None,
    },
    "Climate": {
        "description": (
            "Klimaschutz und Klimaanpassung: CO2-Minderung, "
            "Klimawandelfolgen, Hitzevorsorge, kommunale "
            "Klimakonzepte."
        ),
        "qualifier_hint": None,
    },
    "Population": {
        "description": (
            "Bevölkerung und Einwohnerentwicklung: Zuzug, "
            "Demografie und Einwohnerstatistik der Stadtgesellschaft."
        ),
        "qualifier_hint": None,
    },
    "Science": {
        "description": (
            "Wissenschaft und Forschung: Hochschulen, "
            "Forschungseinrichtungen, Studienplätze und "
            "Technologietransfer."
        ),
        "qualifier_hint": None,
    },
    "Education": {
        "description": (
            "Allgemeine Bildungs- und Schulthemen: Schulen, Schulbau "
            "oder -sanierung, schulische Angebote, "
            "Erwachsenenbildung (ohne Kita - siehe Childcare)."
        ),
        "qualifier_hint": None,
    },
    "Culture": {
        "description": (
            "Kultur und Kulturveranstaltungen: Museen, Theater, "
            "Denkmalschutz und -pflege, Kulturförderung "
            "(zugehörige Bauvorhaben auch unter Building "
            "Construction)."
        ),
        "qualifier_hint": None,
    },
    "Politics": {
        "description": (
            "Politische Verfahren des Gemeinderats: Anträge, "
            "Wahlen von Beigeordneten, Sitzungen, Gremien- und "
            "Organisationsfragen, Beschlussverfahren."
        ),
        "qualifier_hint": None,
    },
    "Energy": {
        "description": (
            "Energie: Wärme- und Stromversorgung, Fernwärme, "
            "erneuerbare Energien (Solar- und Windkraft), "
            "Effizienzkonzepte und kommunale Energiekonzepte."
        ),
        "qualifier_hint": None,
    },
    "Health": {
        "description": (
            "Gesundheit: Krankenhäuser, ärztliche Versorgung, "
            "Sucht- und Drogenhilfe, psychische Gesundheit, "
            "Gesundheitsschutz und Hygiene."
        ),
        "qualifier_hint": None,
    },
    "Building Construction": {
        "description": (
            "Hochbau und bauliche Anlagen: Neubau, Sanierung, "
            "Erweiterung und Rückbau von Gebäuden und kommunalen "
            "Einrichtungen. Achtung: 'Sanierung' heißt im Deutschen "
            "reconstruction, nicht maintenance."
        ),
        "qualifier_hint": "Neubau | Sanierung (reconstruction) | Erweiterung | Rückbau",
    },
    "Housing": {
        "description": (
            "Wohnen: Wohnungsbau, Wohnungswirtschaft, "
            "Mietspiegel- und Mietthemen, Wohnungslosenhilfe."
        ),
        "qualifier_hint": None,
    },
    "Road construction": {
        "description": (
            "Straßenbau und Straßenraum: Neubau, Sanierung, "
            "Erweiterung, Rückbau und Instandsetzung von Straßen, "
            "Plätzen, Wegen und Radwegen."
        ),
        "qualifier_hint": "Neubau | Sanierung (reconstruction) | Erweiterung | Ausbau | Rückbau",
    },
    "city development": {
        "description": (
            "Stadtentwicklung: Bebauungspläne, Planverfahren, "
            "Quartiersentwicklung, Städtebauförderung und "
            "Stadtteilmanagement."
        ),
        "qualifier_hint": None,
    },
    "smart city": {
        "description": (
            "Smart City: Digitale Infrastruktur, "
            "Digitalisierungsprojekte, Datenplattformen und "
            "digitale Teilhabe (daneben oft Politics)."
        ),
        "qualifier_hint": None,
    },
    "Social": {
        "description": (
            "Soziales: Sozialarbeit, Sozialleistungen, "
            "Wohnungslosenhilfe, Migrations- und Fluchtservices, "
            "Jugendhilfe (ohne Kita - eigener Tag Childcare)."
        ),
        "qualifier_hint": None,
    },
    "Childcare": {
        "description": (
            "Kindertagesbetreuung: Kita-Plätze, Kita-Bau und "
            "-sanierung sowie Betreuungsqualität."
        ),
        "qualifier_hint": None,
    },
    "Seniors": {
        "description": (
            "Senioren: Altenhilfe, Pflege, Seniorenangebote, "
            "Seniorenvertretung und Angebote für Ältere."
        ),
        "qualifier_hint": None,
    },
    "Sport": {
        "description": (
            "Sport: Sportstätten, Sportangebote, Vereins- und "
            "Breitensportförderung (Bauvorhaben zusätzlich "
            "Building Construction)."
        ),
        "qualifier_hint": None,
    },
    "Funding": {
        "description": (
            "Förderung und Zuwendungen: Förderprogramme, Mittel "
            "von Bund, Land, EU oder privaten Drittmittelgebern, "
            "Zuschüsse."
        ),
        "qualifier_hint": None,
    },
    "Volunteering": {
        "description": (
            "Ehrenamt: Vereine, bürgerschaftliches Engagement, "
            "Projektförderung aus Bürgerinitiativen."
        ),
        "qualifier_hint": None,
    },
    "Elections": {
        "description": (
            "Wahlen: Kommunal-, Bundestags- oder Landtagswahlen, "
            "Wahlorgane und Wahlgänge, Wahllokale und Wahlrecht."
        ),
        "qualifier_hint": None,
    },
    "Work/Labour": {
        "description": (
            "Arbeit: Arbeitsförderung, Jobcenter, Stellen der "
            "Stadtverwaltung, Aus- und Weiterbildung, Arbeitsrecht."
        ),
        "qualifier_hint": None,
    },
}


def seed(store: KgStore | None = None, yaml_path: str | None = None) -> int:
    """Write the TAGS table into the vocabulary YAML and the SQLite store."""
    import yaml

    with open(yaml_path or DEFAULT_PATH, encoding="utf-8") as fh:
        vocab = yaml.safe_load(fh) or {}
    vocab["file_tags"] = {
        tag: {"description": spec["description"], "qualifier_hint": spec["qualifier_hint"]}
        for tag, spec in TAGS.items()
    }
    with open(yaml_path or DEFAULT_PATH, "w", encoding="utf-8") as fh:
        yaml.safe_dump(vocab, fh, allow_unicode=True, sort_keys=True)
    if store is None:
        return len(TAGS)
    for tag, spec in TAGS.items():
        store.upsert_tag(tag, spec["description"])
    store.commit()
    return len(TAGS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", default="results/kg_statements.sqlite")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        for tag, spec in TAGS.items():
            print(tag)
            print(textwrap.indent(str(spec["description"]), "    "))
            if spec["qualifier_hint"]:
                print(textwrap.indent(f"qualifiers: {spec['qualifier_hint']}", "    "))
        return 0

    store = KgStore(args.store)
    n = seed(store=store)
    ticker = StatusTicker()
    ticker.tick(f"seeded {n} tags", force=True)
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
