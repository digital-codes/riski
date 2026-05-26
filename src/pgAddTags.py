"""Command‑line interface for Riski utilities.

Currently supports the `analyze-db` subcommand which runs the OParl
analysis pipeline.
"""

import argparse
import sys
from pathlib import Path
import os
from sqlalchemy import create_engine
from sqlalchemy import MetaData, Table
from sqlalchemy import select
import json


# Import the DB configuration constants
def openDb():
    """Create and return a SQLAlchemy engine based on `private` settings.
    The `private` module defines the variables `DB_USER`, `DB_PWD`,
    `DB_HOST`, and `DB_NAME`. This function builds the PostgreSQL URL and
    returns an engine with `future=True` and connection pooling enabled.
    """
    try:
        import private as pr
        db_url = f"postgresql+psycopg2://{pr.RO_USER}:{pr.RO_PWD}@localhost/{pr.DB_NAME}"
    except ImportError as exc:
        raise ImportError("Could not import private for DB connection settings") from exc

    return create_engine(db_url, future=True, pool_pre_ping=True)



def load_tables(engine):
    """Reflect the required OParl tables and return ORM Table objects.

    Returns a dict with keys 'consultation', 'agenda_items', 'file'.
    """
    metadata = MetaData()
    consultation = Table('Consultation', metadata, autoload_with=engine)
    agenda_items = Table('AgendaItem', metadata, autoload_with=engine)
    file_tbl = Table('File', metadata, autoload_with=engine)
    return {
        'consultation': consultation,
        'agenda_items': agenda_items,
        'file': file_tbl,
    }


# grouping
import re
from collections import defaultdict
from typing import List, Dict

# Define simple keyword patterns for each group (case‑insensitive)
AGENDA_GROUP_PATTERNS = {
    "Protokolle": re.compile(r"\bprotokoll(e|en)?\b", re.IGNORECASE),
    "Anfragen": re.compile(r"\banfrage(n)?\b", re.IGNORECASE),
    "Anträge": re.compile(r"\bantr[äa]g(e|en)?\b", re.IGNORECASE),
    "Änderungsanträge": re.compile(r"\b(änderungs)?antr[äa]g(e|en)?\b", re.IGNORECASE),
    "Bekanntgaben": re.compile(r"\bbekanntgab(e|en)\b", re.IGNORECASE),
    "Beschlüsse": re.compile(r"\bbeschl[üu]ss(e|en)?\b", re.IGNORECASE),
    "Mitteilungen": re.compile(r"\bmitteilung(en)?\b", re.IGNORECASE),
    "Bürgerfragestunden": re.compile(r"\bbürgerfrage(stunde)?\b", re.IGNORECASE),
    "Bauanträge": re.compile(r"\bbauantr[äa]g(e|en)?\b", re.IGNORECASE),
    "Bebauungspläne": re.compile(r"\bbebauungsplan(e)?\b", re.IGNORECASE),
    "Haushalt": re.compile(r"\bhaushalt\b", re.IGNORECASE),
    "Finanzen": re.compile(r"\bfinanz(en)?\b", re.IGNORECASE),
    "Jahresabschluss": re.compile(r"\bjahresabschluss\b", re.IGNORECASE),
    "Prüfung": re.compile(r"\bprüfung(en)?\b", re.IGNORECASE)
}

# Define simple keyword patterns for each group (case‑insensitive)
FILE_GROUP_PATTERNS = {
    "Abstimmungen": re.compile(r"\Abstimmung?\b", re.IGNORECASE),
    "Protokolle": re.compile(r"\bprotokoll(e|en)?\b", re.IGNORECASE),
    "Vorlagen": re.compile(r"vorlage|\bvorl_nr\.?\b|\bvorl_nr_?\b|\bvorl\.nr\.?|\bvorlagenr\s+[0-9]?\b", re.IGNORECASE),
    "Tagesordnung": re.compile(r"\btagesordnung\b", re.IGNORECASE),
    "TOP": re.compile(r"\bTOP\s*(?:\d+)?\b", re.IGNORECASE),
    "Anlagen": re.compile(r"\banlage(n)?\b", re.IGNORECASE),
    "Anfragen": re.compile(r"\banfrage(n)?\b", re.IGNORECASE),
    "Anträge": re.compile(r"\bantr[äa]g(e|en)?\b", re.IGNORECASE),
    "Änderungsanträge": re.compile(r"\b(änderungs)?antr[äa]g(e|en)?\b", re.IGNORECASE),
    "Bekanntgaben": re.compile(r"\bbekanntgab(e|en)\b", re.IGNORECASE),
    "Beschlüsse": re.compile(r"\bbeschl[üu]ss(e|en)?\b", re.IGNORECASE),
    "Mitteilungen": re.compile(r"\bmitteilung(en)?\b", re.IGNORECASE),
    "Bürgerfragestunden": re.compile(r"\bbürgerfrage(stunde)?\b", re.IGNORECASE),
    "Bauanträge": re.compile(r"\bbauantr[äa]g(e|en)?\b", re.IGNORECASE),
    "Bebauungspläne": re.compile(r"\bbebauungsplan(e)?\b", re.IGNORECASE),
    "Haushalt": re.compile(r"\bhaushalt\b", re.IGNORECASE),
    "Finanzen": re.compile(r"\bfinanz(en)?\b", re.IGNORECASE),
    "Jahresabschluss": re.compile(r"\bjahresabschluss\b", re.IGNORECASE)
}


def categorize_name(name: str, patterns: Dict[str, re.Pattern]) -> str:
    """Return the group name for a given agenda item name.

    If none of the GROUP_PATTERNS match, returns "Other".
    """
    for group, pattern in patterns.items():
        #print(f"Checking if '{name}' matches group '{group}' with pattern '{pattern.pattern}'")
        if pattern.search(name):
            return group
    return "Other"



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Riski utilities command‑line interface")
    parser.add_argument("--json-dir", required=True, help="Directory to write JSON and markdown outputs")
    args = parser.parse_args(argv)

    json_dir = Path(args.json_dir or ".")
    json_dir.mkdir(parents=True, exist_ok=True)

    try:
        engine = openDb()
        tables = load_tables(engine)
    except Exception as exc:
        print(f"Error connecting to database: {exc}", file=sys.stderr)
        return 1

    # distinct roles
    consultation = tables["consultation"]
    stmt = select(consultation.c.role).distinct()
    with engine.connect() as conn:
        result = conn.execute(stmt)
        roles = [row[0] for row in result if row[0] is not None]
    with open(json_dir / "roles.json", "w", encoding="utf-8") as jf:
        json.dump(roles, jf, ensure_ascii=False, indent=2)
        
    # distinct results
    agenda = tables["agenda_items"]
    stmt = select(agenda.c.result).distinct()
    with engine.connect() as conn:
        result = conn.execute(stmt)
        results = [row[0] for row in result if row[0] is not None]
    with open(json_dir / "results.json", "w", encoding="utf-8") as jf:
        json.dump(results, jf, ensure_ascii=False, indent=2)

    # agenda item grouping
    agenda = tables["agenda_items"]
    with engine.connect() as conn:
        agenda_names = [(row.sid, row.oparlKey, row.name) for row in conn.execute(agenda.select()).fetchall() if row.name is not None]

    agendaGroups: Dict[str, List[str]] = defaultdict(list)
    for i, k, n in agenda_names:
        # print(f"Processing AgendaItem id={i} name='{n}'"    )
        grp = categorize_name(n, AGENDA_GROUP_PATTERNS)
        # ignore n start start with "-" like "- abgesetzt"
        if n.startswith("-"):
            continue
        agendaGroups[grp].append({"id": i, "key": k, "name": n})

    # move all groups with less than 10 items to "Other"
    for group in list(agendaGroups.keys()):
        if len(agendaGroups[group]) < 10:
            agendaGroups["Other"].extend(agendaGroups.pop(group))

    with open(json_dir / "agenda_groups.json", "w", encoding="utf-8") as jf:
        json.dump(dict(agendaGroups), jf, ensure_ascii=False, indent=2)
    
    # print summary
    print("Summary of agenda item groups:")
    for group, items in agendaGroups.items():
        print(f"  {group}: {len(items)} items")
        
    # file name grouping
    files = tables["file"]
    with engine.connect() as conn:
        file_names = [(row.sid, row.oparlKey, row.name) for row in conn.execute(files.select()).fetchall() if row.name is not None]

    fileGroups: Dict[str, List[str]] = defaultdict(list)
    for i, k, n in file_names:
        # print(f"Processing File id={i} name='{n}'"    )
        grp = categorize_name(n, FILE_GROUP_PATTERNS)
        # ignore n start start with "-" like "- abgesetzt"
        if n.startswith("-"):
            continue
        fileGroups[grp].append({"id": i, "key": k, "name": n})

    # move all groups with less than 10 items to "Other"
    for group in list(fileGroups.keys()):
        if len(fileGroups[group]) < 10:
            fileGroups["Other"].extend(fileGroups.pop(group))

    with open(json_dir / "file_groups.json", "w", encoding="utf-8") as jf:
        json.dump(dict(fileGroups), jf, ensure_ascii=False, indent=2)
    
    # print summary
    print("Summary of file groups:")
    for group, items in fileGroups.items():
        print(f"  {group}: {len(items)} items")
        

    return 0


if __name__ == "__main__":
    sys.exit(main())
