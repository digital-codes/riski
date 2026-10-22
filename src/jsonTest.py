#!/usr/bin/env python3
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Table,
    Text,
    Boolean,
    Float,
    create_engine,
    inspect
)
from sqlalchemy.dialects.postgresql import JSONB as PGJSON, insert
#from sqlalchemy.dialects.postgresql import excluded
from sqlalchemy.orm import sessionmaker

# Read JSON files whose filename starts with an uppercase letter AND ends with .json
READ_FILENAME_FILTER = lambda fn: fn.endswith('.json') and fn[0].isupper()

# Do not drop existing tables by default – keep custom tables (e.g. vector tables) safe
DROP_ALL = False  # set True only for a clean rebuild

# Print insert progress every N entities
PROGRESS_EVERY = 500

STRING_SIZE = 256

# ----------------------------
# HELPERS
# ----------------------------
def parse_datetime_maybe(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    # ISO 8601 like: 2016-10-12T09:08:40+02:00  / 2016-10-12T09:08:40Z
    m = re.match(r'^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?$', s)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)}T{m.group(2)}", "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            pass
    # YYYY-MM-DD
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        pass
    # DD.MM.YYYY
    try:
        return datetime.strptime(s, "%d.%m.%Y")
    except ValueError:
        pass
    return None


def table_name_from_type(type_url: str) -> str:
    # "https://schema.oparl.org/1.1/Meeting" -> "Meeting"
    return type_url.rstrip('/').split('/')[-1]


def trailing_id_from_oparl_id(oparl_id: str) -> str:
    # ".../meetings/961" -> "961", ".../system" -> "system"
    return oparl_id.rstrip('/').split('/')[-1]


def to_int_if_possible(s: str) -> Optional[int]:
    return int(s) if s.isdigit() else None


def is_entity_dict(x: Any) -> bool:
    return (
        isinstance(x, dict)
        and 'id' in x
        and 'type' in x
        and isinstance(x['id'], str)
        and isinstance(x['type'], str)
    )


def iter_json_files(directory: str) -> Iterable[str]:
    for fn in os.listdir(directory):
        if READ_FILENAME_FILTER(fn):
            yield os.path.join(directory, fn)

# --- NEW: column name sanitizing (keeps original keys where possible) ---
_RESERVED = {
    'order', 'group', 'user', 'select', 'from', 'where', 'table', 'key', 'index', 'constraint', 'start', 'end'
}

_RENAME_MAP = {
    'start': 'start_date',
    'end': 'end_date',
    'order': 'order_col',
}

def safe_col_name(key: str) -> Tuple[str, bool]:
    """Return (column_name, quote_flag). Quote if reserved or altered."""
    name = _RENAME_MAP.get(key, key).lower()
    name = re.sub(r'[^A-Za-z0-9_]', '_', name)
    if not name:
        name = 'k'
    if name[0].isdigit():
        name = 'k_' + name
    quote = (name.lower() in _RESERVED) or (name != key)
    return name, quote


def is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def infer_scalar_type(values: List[Any]):
    non_null = [v for v in values if v is not None]
    if not non_null:
        return String(STRING_SIZE)
    if all(isinstance(v, int) and not isinstance(v, bool) for v in non_null):
        return BigInteger
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null):
        return Float
    if all(isinstance(v, bool) for v in non_null):
        return Boolean
    if all(parse_datetime_maybe(v) is not None for v in non_null if isinstance(v, str)):
        return DateTime
    return String(STRING_SIZE)


# ----------------------------
# IN-MEMORY MODEL
# ----------------------------
@dataclass(frozen=True)
class EntityKey:
    table: str
    oparl_id: str  # full URL, unique globally
    oparl_key: str  # trailing segment, may be numeric or not


@dataclass
class Entity:
    key: EntityKey
    raw: Dict[str, Any]
    sources: Set[str]      # filenames where it appeared
    first_path: str        # json-path-like pointer where first seen


# ----------------------------
# PASS 1: COLLECT ENTITIES (including embedded)
# ----------------------------
def collect_entities_from_obj(
    obj: Any,
    entities: Dict[EntityKey, Entity],
    url_to_key: Dict[str, EntityKey],
    source_file: str,
    path: str = '$',
) -> None:
    if is_entity_dict(obj):
        table = table_name_from_type(obj['type'])
        oparl_id = obj['id']
        oparl_key = trailing_id_from_oparl_id(oparl_id)
        key = EntityKey(table=table, oparl_id=oparl_id, oparl_key=oparl_key)
        if key not in entities:
            entities[key] = Entity(key=key, raw=obj, sources={source_file}, first_path=path)
            url_to_key[oparl_id] = key
        else:
            entities[key].sources.add(source_file)
        for k, v in obj.items():
            collect_entities_from_obj(v, entities, url_to_key, source_file, f"{path}.{k}")
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            collect_entities_from_obj(v, entities, url_to_key, source_file, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, it in enumerate(obj):
            collect_entities_from_obj(it, entities, url_to_key, source_file, f"{path}[{i}]")


def pass1_collect(directory: str) -> Tuple[Dict[EntityKey, Entity], Dict[str, EntityKey], Set[str]]:
    entities: Dict[EntityKey, Entity] = {}
    url_to_key: Dict[str, EntityKey] = {}
    tables: Set[str] = set()
    files = list(iter_json_files(directory))
    print(f"Found {len(files)} JSON files to process in '{directory}'")
    for i, path in enumerate(files, 1):
        # print(f"  Reading file {i}/{len(files)}: {os.path.basename(path)}")
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        collect_entities_from_obj(data, entities, url_to_key, source_file=os.path.basename(path), path='$')
    for k in entities.keys():
        tables.add(k.table)
    return entities, url_to_key, tables


# ----------------------------
# PASS 2: DETECT RELATIONSHIPS
# ----------------------------
"""
Meeting field: id -> https://web1.karlsruhe.de/ris/oparl/bodies/0001/meetings/9066
Meeting field: type -> https://schema.oparl.org/1.1/Meeting
Meeting field: name -> Hauptausschuss (öffentlich/nicht öffentlich)
Meeting field: start -> 2023-11-14T16:30:00+01:00
Meeting field: end -> 2023-11-14T18:30:00+01:00
Meeting field: location -> {'id': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/locations/si/9066', 'type': 'https://schema.oparl.org/1.1/Location', 'description': 'Bürgersaal, Rathaus am Marktplatz', 'created': '2022-09-21T13:37:10+02:00', 'modified': '2025-03-03T13:33:55+01:00'}
Meeting field: organization -> ['https://web1.karlsruhe.de/ris/oparl/bodies/0001/organizations/gr/28964']
Meeting field: invitation -> {'id': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/files/653114', 'type': 'https://schema.oparl.org/1.1/File', 'name': 'Tagesordnung (öffentlich) Ausschuss/Ortschaftsrat', 'fileName': '00653114.pdf', 'mimeType': 'application/pdf', 'date': '2023-11-02', 'accessUrl': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/downloadfiles/a/00653114.pdf', 'downloadUrl': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/downloadfiles/00653114.pdf', 'created': '2023-11-02T10:44:51+01:00', 'modified': '2025-03-03T14:30:18+01:00'}
Meeting field: resultsProtocol -> {'id': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/files/654212', 'type': 'https://schema.oparl.org/1.1/File', 'name': 'Anwesenheit (Protokoll)', 'fileName': '00654212.pdf', 'mimeType': 'application/pdf', 'date': '2023-11-29', 'accessUrl': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/downloadfiles/a/00654212.pdf', 'downloadUrl': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/downloadfiles/00654212.pdf', 'created': '2023-11-29T13:15:04+01:00', 'modified': '2025-03-03T14:30:18+01:00'}
Meeting field: agendaItem -> [{'id': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/agendaitems/80895', 'type': 'https://schema.oparl.org/1.1/AgendaItem', 'meeting': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/meetings/9066', 'number': '1', 'order': 1, 'name': 'Vergabe von Postdienstleistungen, Beförderung und Zustellung von Internationalen Briefen, Postkarten, Einschreiben, PZA und E-PZA sowie Paketen für die Stadt Karlsruhe', 'public': True, 'consultation': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/consultations/30603', 'result': 'einstimmig zugestimmt', 'created': '2023-10-16T11:14:26+02:00', 'modified': '2025-03-03T13:33:42+01:00'}, {'id': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/agendaitems/83085', 'type': 'https://schema.oparl.org/1.1/AgendaItem', 'meeting': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/meetings/9066', 'number': '2', 'order': 2, 'name': 'Unabweisbare Stellenschaffungen für 2024', 'public': True, 'consultation': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/consultations/30924', 'result': 'Kenntnisnahme', 'created': '2023-10-23T12:18:30+02:00', 'modified': '2025-03-03T13:33:42+01:00'}, {'id': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/agendaitems/80896', 'type': 'https://schema.oparl.org/1.1/AgendaItem', 'meeting': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/meetings/9066', 'number': '3', 'order': 3, 'name': 'Änderung des Gesellschaftsvertrags der Baden Airpark Beteiligungsgesellschaft mbH', 'public': True, 'consultation': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/consultations/30610', 'result': 'einstimmig zugestimmt', 'created': '2023-10-16T11:14:26+02:00', 'modified': '2025-03-03T13:33:42+01:00'}, {'id': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/agendaitems/83070', 'type': 'https://schema.oparl.org/1.1/AgendaItem', 'meeting': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/meetings/9066', 'number': '4', 'order': 4, 'name': 'Annahme des Angebots von Zuwendungen', 'public': True, 'consultation': 'https://web1.karlsruhe.de/ris/oparl/bodies/0001/consultations/30883', 'result': 'einstimmig zugestimmt', 'created': '2023-10-20T12:52:08+02:00', 'modified': '2025-03-03T13:33:42+01:00'}]
Meeting field: created -> 2022-09-21T13:37:10+02:00
Meeting field: modified -> 2025-03-03T13:33:55+01:00
"""


def detect_relationships(
    entities: Dict[EntityKey, Entity],
    url_to_key: Dict[str, EntityKey],
) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    single_fk_fields: Dict[str, Dict[str, str]] = {}
    many_fields: Dict[str, Dict[str, str]] = {}
    def ensure(d: Dict[str, Dict[str, str]], table: str) -> None:
        if table not in d:
            d[table] = {}
    for ent in entities.values():
        src_table = ent.key.table
        ensure(single_fk_fields, src_table)
        ensure(many_fields, src_table)
        for field, value in ent.raw.items():
            if field in ('id', 'type'):
                continue
            # single reference: URL string
            if isinstance(value, str):
                if value in url_to_key:
                    tgt_table = url_to_key[value].table
                    single_fk_fields[src_table][field] = tgt_table
                continue
            # many references: list of URLs or embedded entities
            if isinstance(value, dict):
                if 'id' in value:
                    if isinstance(value['id'], str):
                        tgt_table = table_name_from_type(value['type'])
                        single_fk_fields[src_table][field] = tgt_table
                        #print(f"  Detected single FK from dict: {src_table}.{field} -> {tgt_table}")
                        continue
            if isinstance(value, list) and value:
                if all(isinstance(x, str) for x in value):
                    resolved = [url_to_key[x] for x in value if x in url_to_key]
                    # print(f"  Checking list of URLs for {src_table}.{field}: {len(resolved)} resolved out of {len(value)}")
                    if resolved:
                        tgt_tables = {rk.table for rk in resolved}
                        if len(tgt_tables) == 1:
                            many_fields[src_table][field] = next(iter(tgt_tables))
                    continue
                if all(is_entity_dict(x) for x in value):
                    tgt_tables = {table_name_from_type(x['type']) for x in value}
                    if len(tgt_tables) == 1:
                        many_fields[src_table][field] = next(iter(tgt_tables))
                    continue
    return single_fk_fields, many_fields


def detect_scalar_columns(
    entities: Dict[EntityKey, Entity],
    single_fk_fields: Dict[str, Dict[str, str]],
    many_fields: Dict[str, Dict[str, str]],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, str]], Dict[str, Dict[str, bool]]]:
    observed: Dict[str, Dict[str, List[Any]]] = {}
    def ensure(table: str, key: str):
        observed.setdefault(table, {}).setdefault(key, [])
    for ent in entities.values():
        t = ent.key.table
        for k, v in ent.raw.items():
            if k in ('id', 'type'):
                continue
            if k in ('created', 'modified'):
                continue
            if k in single_fk_fields.get(t, {}):
                continue
            if k in many_fields.get(t, {}):
                continue
            if is_scalar(v):
                ensure(t, k)
                observed[t][k].append(v)
    scalar_types: Dict[str, Dict[str, Any]] = {}
    scalar_colnames: Dict[str, Dict[str, str]] = {}
    scalar_quote: Dict[str, Dict[str, bool]] = {}
    for t, keys in observed.items():
        scalar_types[t] = {}
        scalar_colnames[t] = {}
        scalar_quote[t] = {}
        for orig_key, vals in keys.items():
            colname, quote = safe_col_name(orig_key)
            scalar_colnames[t][orig_key] = colname
            scalar_quote[t][orig_key] = quote
            scalar_types[t][orig_key] = infer_scalar_type(vals)
    return scalar_types, scalar_colnames, scalar_quote

# ----------------------------
# SCHEMA BUILD
# ----------------------------

def assoc_table_name(src: str, field: str, tgt: str) -> str:
    return f"{src}__{field}__{tgt}"


def make_main_tables(
    metadata: MetaData,
    all_tables: Set[str],
    single_fk_fields: Dict[str, Dict[str, str]],
    scalar_types: Dict[str, Dict[str, Any]],
    scalar_colnames: Dict[str, Dict[str, str]],
    scalar_quote: Dict[str, Dict[str, bool]],
) -> Dict[str, Table]:
    tables: Dict[str, Table] = {}
    for t in sorted(all_tables):
        cols = [
            Column('sid', BigInteger, primary_key=True, autoincrement=True),
            Column('id', BigInteger, nullable=True, index=True),
            Column('oparlKey', String(255), nullable=False, index=True),
            Column('oparlId', String(512), nullable=False, unique=True, index=True),
            Column('type', String(255), nullable=False),
            Column('created', DateTime, nullable=True),
            Column('modified', DateTime, nullable=True),
            Column('data', PGJSON, nullable=False),
        ]
        # scalar columns
        for orig_key, sa_type in sorted(scalar_types.get(t, {}).items()):
            colname = scalar_colnames[t][orig_key]
            quote = scalar_quote[t][orig_key]
            cols.append(Column(colname, sa_type, nullable=True, quote=quote))
        # special content column for File
        if t == 'File':
            cols.append(Column('content', Text, nullable=True))
        for field, tgt_table in sorted(single_fk_fields.get(t, {}).items()):
            fk_col = f"{field}Sid"
            cols.append(Column(fk_col, BigInteger, ForeignKey(f"{tgt_table}.sid"), nullable=True, index=True))
        tables[t] = Table(t, metadata, *cols)
    return tables


def make_assoc_tables(
    metadata: MetaData,
    many_fields: Dict[str, Dict[str, str]],
) -> Dict[str, Table]:
    assoc: Dict[str, Table] = {}
    for src_table, fields in many_fields.items():
        for field, tgt_table in fields.items():
            name = assoc_table_name(src_table, field, tgt_table)
            assoc[name] = Table(
                name,
                metadata,
                Column('srcSid', BigInteger, ForeignKey(f"{src_table}.sid"), primary_key=True),
                Column('tgtSid', BigInteger, ForeignKey(f"{tgt_table}.sid"), primary_key=True),
            )
    return assoc

# ----------------------------
# INSERT LOGIC
# ----------------------------
def build_base_row(
    ent: Entity,
    scalar_types: Dict[str, Dict[str, Any]],
    scalar_colnames: Dict[str, Dict[str, str]],
) -> Dict[str, Any]:
    raw = ent.raw
    oparl_key = ent.key.oparl_key
    numeric_id = to_int_if_possible(oparl_key)
    row = {
        'id': numeric_id,
        'oparlKey': oparl_key,
        'oparlId': ent.key.oparl_id,
        'type': raw.get('type', ''),
        'created': parse_datetime_maybe(raw.get('created')),
        'modified': parse_datetime_maybe(raw.get('modified')),
        'data': raw,
    }
    t = ent.key.table
    for orig_key, sa_type in scalar_types.get(t, {}).items():
        colname = scalar_colnames[t][orig_key]
        v = ent.raw.get(orig_key)
        if v is None:
            row[colname] = None
        elif sa_type is DateTime and isinstance(v, str):
            row[colname] = parse_datetime_maybe(v)
        else:
            row[colname] = v
    return row



# ----------------------------
# MAIN
# ----------------------------
def main(directory: str) -> None:
    print('PASS 1: Collecting entities ...')
    entities, url_to_key, all_tables = pass1_collect(directory)
    print(f'  -> Found {len(entities)} entities in {len(all_tables)} tables')
    print('PASS 2: Detecting relationships ... with len(url_to_keys):', len(url_to_key))
    single_fk_fields, many_fields = detect_relationships(entities, url_to_key)
    print('  -> Relationships detected for single',single_fk_fields)
    print('  -> Relationships detected for many',many_fields)
    
    scalar_types, scalar_colnames, scalar_quote = detect_scalar_columns(entities, single_fk_fields, many_fields)
    print('  -> Scalar columns detected',scalar_colnames)
    
    # Write all tables to JSON files
    out_dir = 'out'
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    
    for table in all_tables:
        table_data = []
        for ent_key, ent in entities.items():
            if ent_key.table == table:
                row = build_base_row(ent, scalar_types, scalar_colnames)
                table_data.append(row)
        
        out_file = os.path.join(out_dir, f'{table}.json')
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(table_data, f, indent=2, default=str)
        print(f'  -> Wrote {len(table_data)} records to {out_file}')
    
    print('Done.')

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        print('Usage: python jsonTest.py <path_to_directory_with_json_files>')
        raise SystemExit(2)
    main(sys.argv[1])
