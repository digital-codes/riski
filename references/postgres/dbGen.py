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
    inspect,
)
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from sqlalchemy.orm import sessionmaker


# Read JSON files whose filename starts with an uppercase letter AND ends with .json
READ_FILENAME_FILTER = lambda fn: fn.endswith(".json") and fn[0].isupper()

DROP_ALL = True  # drop and recreate all tables each run

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
    m = re.match(
        r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?$",
        s,
    )
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
    return type_url.rstrip("/").split("/")[-1]


def trailing_id_from_oparl_id(oparl_id: str) -> str:
    # ".../meetings/961" -> "961", ".../system" -> "system"
    return oparl_id.rstrip("/").split("/")[-1]


def to_int_if_possible(s: str) -> Optional[int]:
    return int(s) if s.isdigit() else None


def is_entity_dict(x: Any) -> bool:
    return (
        isinstance(x, dict)
        and "id" in x
        and "type" in x
        and isinstance(x["id"], str)
        and isinstance(x["type"], str)
    )


def iter_json_files(directory: str) -> Iterable[str]:
    for fn in os.listdir(directory):
        if READ_FILENAME_FILTER(fn):
            yield os.path.join(directory, fn)

# --- NEW: column name sanitizing (keeps original keys where possible) ---
_RESERVED = {
    "order", "group", "user", "select", "from", "where", "table", "key", "index", "constraint"
}

def safe_col_name(key: str) -> Tuple[str, bool]:
    """
    Returns (column_name, quote_flag)
    - quote_flag=True for reserved words or names needing quoting.
    """
    name = re.sub(r"[^A-Za-z0-9_]", "_", key)
    if not name:
        name = "k"
    if name[0].isdigit():
        name = "k_" + name
    quote = (name.lower() in _RESERVED) or (name != key)
    return name, quote


def is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def infer_scalar_type(values: List[Any]):
    """
    Infer SQLAlchemy column type from observed values.
    Priority: DateTime > Boolean > Integer > Float > String
    """
    # ignore None for inference
    non_null = [v for v in values if v is not None]
    if not non_null:
        return String(STRING_SIZE)

    # datetime-like strings?
    if all((parse_datetime_maybe(v) is not None) for v in non_null if isinstance(v, str)):
        return DateTime

    # booleans
    if all(isinstance(v, bool) for v in non_null):
        return Boolean

    # ints
    if all(isinstance(v, int) and not isinstance(v, bool) for v in non_null):
        return BigInteger

    # floats (or mixed int/float)
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null):
        return Float

    # default string (make room for long text keys like "name"/"role"/etc.)
    return String(STRING_SIZE)



# ----------------------------
# IN-MEMORY MODEL
# ----------------------------
@dataclass(frozen=True)
class EntityKey:
    table: str
    oparl_id: str  # full URL, unique globally
    oparl_key: str  # trailing segment, may be numeric or not (e.g. "system")


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
    path: str = "$",
) -> None:
    if is_entity_dict(obj):
        table = table_name_from_type(obj["type"])
        oparl_id = obj["id"]
        oparl_key = trailing_id_from_oparl_id(oparl_id)
        key = EntityKey(table=table, oparl_id=oparl_id, oparl_key=oparl_key)

        if key not in entities:
            entities[key] = Entity(key=key, raw=obj, sources={source_file}, first_path=path)
            url_to_key[oparl_id] = key
        else:
            entities[key].sources.add(source_file)

        # recurse to capture nested entities
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
    for i, path in enumerate(files, 1):
        print(f"  Reading file {i}/{len(files)}: {os.path.basename(path)}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        collect_entities_from_obj(
            data,
            entities,
            url_to_key,
            source_file=os.path.basename(path),
            path="$",
        )

    for k in entities.keys():
        tables.add(k.table)

    return entities, url_to_key, tables


# ----------------------------
# PASS 2: DETECT RELATIONSHIPS
# ----------------------------
def detect_relationships(
    entities: Dict[EntityKey, Entity],
    url_to_key: Dict[str, EntityKey],
) -> Tuple[
    Dict[str, Dict[str, str]],  # single_fk_fields[table][field] = target_table
    Dict[str, Dict[str, str]],  # many_fields[table][field] = target_table
]:
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
            if field in ("id", "type"):
                continue

            # single reference: URL string
            if isinstance(value, str) and value in url_to_key:
                tgt_table = url_to_key[value].table
                single_fk_fields[src_table][field] = tgt_table
                continue

            # many references: list of URLs or list of embedded entities
            if isinstance(value, list) and value:
                if all(isinstance(x, str) for x in value):
                    resolved = [url_to_key[x] for x in value if x in url_to_key]
                    if resolved:
                        tgt_tables = {rk.table for rk in resolved}
                        if len(tgt_tables) == 1:
                            many_fields[src_table][field] = next(iter(tgt_tables))
                    continue

                if all(is_entity_dict(x) for x in value):
                    tgt_tables = {table_name_from_type(x["type"]) for x in value}
                    if len(tgt_tables) == 1:
                        many_fields[src_table][field] = next(iter(tgt_tables))
                    continue

    return single_fk_fields, many_fields

def detect_scalar_columns(
    entities: Dict[EntityKey, Entity],
    single_fk_fields: Dict[str, Dict[str, str]],
    many_fields: Dict[str, Dict[str, str]],
) -> Tuple[
    Dict[str, Dict[str, Any]],          # scalar_types[table][orig_key] = SA type (class or instance)
    Dict[str, Dict[str, str]],          # scalar_colnames[table][orig_key] = column_name
    Dict[str, Dict[str, bool]],         # scalar_quote[table][orig_key] = quote flag
]:
    # collect observed values per table/key
    observed: Dict[str, Dict[str, List[Any]]] = {}

    def ensure(table: str, key: str):
        observed.setdefault(table, {}).setdefault(key, [])

    for ent in entities.values():
        t = ent.key.table
        for k, v in ent.raw.items():
            if k in ("id", "type"):  # handled separately
                continue
            if k in ("created", "modified"):  # already explicit
                continue
            # skip relationship-like top-level keys:
            if k in single_fk_fields.get(t, {}):
                continue
            if k in many_fields.get(t, {}):
                continue
            # only top-level scalar keys
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
def drop_all_tables(engine) -> None:
    md = MetaData()
    md.reflect(bind=engine)
    md.drop_all(bind=engine)


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
    """
    Main tables use:
      sid: BIGINT AUTO_INCREMENT PK (always numeric, used for all FKs)
      id:  BIGINT nullable (numeric oparlKey when possible)
      oparlKey: string trailing segment (e.g. "961" or "system")
      oparlId: full URL unique
      type, created, modified, data(JSON)
      plus <field>Sid columns for detected single references
    """
    tables: Dict[str, Table] = {}

    for t in sorted(all_tables):
        cols = [
            Column("sid", BigInteger, primary_key=True, autoincrement=True),
            Column("id", BigInteger, nullable=True, index=True),
            Column("oparlKey", String(255), nullable=False, index=True),
            Column("oparlId", String(512), nullable=False, unique=True, index=True),
            Column("type", String(255), nullable=False),
            Column("created", DateTime, nullable=True),
            Column("modified", DateTime, nullable=True),
            Column("data", MySQLJSON, nullable=False),
        ]

        # --- NEW: add scalar explicit columns detected from top-level keys ---
        for orig_key, sa_type in sorted(scalar_types.get(t, {}).items()):
            colname = scalar_colnames[t][orig_key]
            quote = scalar_quote[t][orig_key]

            # Use Text for very long strings if you want; otherwise String(4k) from infer is fine.
            cols.append(Column(colname, sa_type, nullable=True, quote=quote))

        # add column content for table File only, type text, nullable (for now, we only have content for some files and want to keep the option open to add more later)
        if t == "File":
            cols.append(Column("content", Text, nullable=True))

        for field, tgt_table in sorted(single_fk_fields.get(t, {}).items()):
            fk_col = f"{field}Sid"
            cols.append(
                Column(fk_col, BigInteger, ForeignKey(f"{tgt_table}.sid"), nullable=True, index=True)
            )

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
                Column("srcSid", BigInteger, ForeignKey(f"{src_table}.sid"), primary_key=True),
                Column("tgtSid", BigInteger, ForeignKey(f"{tgt_table}.sid"), primary_key=True),
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
        # sid auto
        "id": numeric_id,                    # numeric tail if possible else NULL
        "oparlKey": oparl_key,               # always present (string)
        "oparlId": ent.key.oparl_id,         # full URL unique
        "type": raw.get("type", ""),
        "created": parse_datetime_maybe(raw.get("created")),
        "modified": parse_datetime_maybe(raw.get("modified")),
        "data": raw,
    }

    # --- NEW: fill detected scalar columns from top-level keys ---
    t = ent.key.table
    for orig_key, sa_type in scalar_types.get(t, {}).items():
        colname = scalar_colnames[t][orig_key]
        v = ent.raw.get(orig_key)

        if v is None:
            row[colname] = None
        elif sa_type is DateTime and isinstance(v, str):
            row[colname] = parse_datetime_maybe(v)
        else:
            # bool/int/float/str
            row[colname] = v

    return row


def insert_all(
    engine,
    main_tables: Dict[str, Table],
    assoc_tables: Dict[str, Table],
    entities: Dict[EntityKey, Entity],
    url_to_key: Dict[str, EntityKey],
    single_fk_fields: Dict[str, Dict[str, str]],
    many_fields: Dict[str, Dict[str, str]],
    scalar_types: Dict[str, Dict[str, Any]],
    scalar_colnames: Dict[str, Dict[str, str]],
) -> None:
    Session = sessionmaker(bind=engine)
    session = Session()

    # 1) Insert base rows (no FK columns set yet; sid is auto)
    total = len(entities)
    for idx, ent in enumerate(entities.values(), 1):
        if idx % PROGRESS_EVERY == 0 or idx == total:
            print(f"  Base insert {idx}/{total} ...")

        t = main_tables[ent.key.table]
        try:
            row = build_base_row(ent, scalar_types, scalar_colnames)
            session.execute(t.insert().prefix_with("IGNORE"), row)  # ignore duplicates by oparlId unique
        except Exception as e:
            raise RuntimeError(
                f"Base insert failed for table={ent.key.table} oparlId={ent.key.oparl_id} "
                f"source_file(s)={sorted(ent.sources)} json_path={ent.first_path}"
            ) from e

    session.commit()

    # 2) Build oparlId -> sid map (needed for FKs and association tables)
    print("  Building oparlId->sid map ...")
    oparlid_to_sid: Dict[str, int] = {}
    for table_name, t in main_tables.items():
        try:
            rows = session.execute(t.select().with_only_columns(t.c.oparlId, t.c.sid)).all()
            for oparlId, sid in rows:
                if oparlId is not None and sid is not None:
                    oparlid_to_sid[oparlId] = int(sid)
        except Exception as e:
            raise RuntimeError(f"Failed building sid map for table={table_name}") from e

    # 3) Second pass: UPDATE FK columns (<field>Sid) using sid map
    print("  Populating FK columns ...")
    total = len(entities)
    for idx, ent in enumerate(entities.values(), 1):
        if idx % PROGRESS_EVERY == 0 or idx == total:
            print(f"  FK update {idx}/{total} ...")

        src_sid = oparlid_to_sid.get(ent.key.oparl_id)
        if not src_sid:
            continue

        t = main_tables[ent.key.table]
        updates: Dict[str, Any] = {}

        for field, _tgt_table in single_fk_fields.get(ent.key.table, {}).items():
            v = ent.raw.get(field)
            fk_col = f"{field}Sid"
            if isinstance(v, str):
                updates[fk_col] = oparlid_to_sid.get(v)
            else:
                updates[fk_col] = None

        if updates:
            try:
                session.execute(t.update().where(t.c.sid == src_sid).values(**updates))
            except Exception as e:
                raise RuntimeError(
                    f"FK update failed for table={ent.key.table} oparlId={ent.key.oparl_id} "
                    f"source_file(s)={sorted(ent.sources)} json_path={ent.first_path}"
                ) from e

    session.commit()

    # 4) Insert association rows (M:N) using sid map
    print("  Inserting association rows ...")
    for ent in entities.values():
        src_sid = oparlid_to_sid.get(ent.key.oparl_id)
        if not src_sid:
            continue

        src_table = ent.key.table
        for field, tgt_table in many_fields.get(src_table, {}).items():
            value = ent.raw.get(field)
            if value is None:
                continue

            assoc_name = assoc_table_name(src_table, field, tgt_table)
            at = assoc_tables.get(assoc_name)
            if at is None:
                continue

            pairs: List[Tuple[int, int]] = []

            if isinstance(value, list) and all(isinstance(x, str) for x in value):
                for url in value:
                    tgt_sid = oparlid_to_sid.get(url)
                    if tgt_sid:
                        pairs.append((src_sid, tgt_sid))

            elif isinstance(value, list) and all(is_entity_dict(x) for x in value):
                for obj in value:
                    url = obj.get("id")
                    if isinstance(url, str):
                        tgt_sid = oparlid_to_sid.get(url)
                        if tgt_sid:
                            pairs.append((src_sid, tgt_sid))

            if pairs:
                try:
                    for s, tg in pairs:
                        session.execute(
                            at.insert().prefix_with("IGNORE"),
                            {"srcSid": s, "tgtSid": tg},
                        )
                except Exception as e:
                    raise RuntimeError(
                        f"Assoc insert failed for {assoc_name} from table={src_table} oparlId={ent.key.oparl_id} "
                        f"source_file(s)={sorted(ent.sources)} json_path={ent.first_path}"
                    ) from e

    session.commit()


# ----------------------------
# MAIN
# ----------------------------
def main(directory: str) -> None:
    import private as pr
    db_url = f"mariadb+pymysql://{pr.DB_USER}:{pr.DB_PWD}@localhost/{pr.DB_NAME}"
    engine = create_engine(db_url, future=True)
    metadata = MetaData()

    if DROP_ALL:
        print("Dropping existing tables ...")
        drop_all_tables(engine)

    print("PASS 1: Collecting entities ...")
    entities, url_to_key, all_tables = pass1_collect(directory)
    print(f"  -> Found {len(entities)} entities in {len(all_tables)} tables")


    print("PASS 2: Detecting relationships ...")
    single_fk_fields, many_fields = detect_relationships(entities, url_to_key)
    print("  -> Relationships detected")
    scalar_types, scalar_colnames, scalar_quote = detect_scalar_columns(
        entities, single_fk_fields, many_fields
    )
    print("  -> Scalar columns detected")

    print("Building schema ...")
    main_tables = make_main_tables(
        metadata, all_tables, single_fk_fields,
        scalar_types, scalar_colnames, scalar_quote
    )    
    assoc_tables = make_assoc_tables(metadata, many_fields)

    metadata.create_all(engine)
    print("  -> Tables created")

    print("Inserting data ...")
    insert_all(
        engine,
        main_tables,
        assoc_tables,
        entities,
        url_to_key,
        single_fk_fields,
        many_fields,
        scalar_types,
        scalar_colnames,
    )
    insp = inspect(engine)
    print("Created tables:")
    for t in insp.get_table_names():
        print(" -", t)

    print("Done.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python dbGen.py <path_to_directory_with_json_files>")
        raise SystemExit(2)

    main(sys.argv[1])
    