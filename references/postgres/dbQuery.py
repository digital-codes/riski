"""
Query helpers for your generated OParl MariaDB schema.

Assumptions (based on your generator):
- Each entity table has: sid (PK), id (numeric tail, nullable), oparlKey (string tail), oparlId (full URL unique),
  plus created/modified/data JSON.
- Single refs became columns named <field>Sid (FK to target.sid), e.g. AgendaItem.meetingSid -> Meeting.sid
- Multi refs became association tables named: <SrcTable>__<field>__<TgtTable>
  with columns: srcSid, tgtSid
- File rows: oparlKey is the trailing segment (the "oparlkey" you mention)

Adjust DB URL as needed.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, Union, Set

from sqlalchemy import create_engine, MetaData, Table, select, and_, or_, func
from sqlalchemy.engine import Engine

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



# ----------------------------
# DB / reflection utilities
# ----------------------------
def make_engine(db_url: str) -> Engine:
    return create_engine(db_url, future=True)


def reflect_tables(engine: Engine) -> Dict[str, Table]:
    md = MetaData()
    md.reflect(bind=engine)
    # md.sorted_tables tries to topologically sort by FKs; cycles trigger SAWarning.
    return dict(md.tables)
    # return {t.name: t for t in md.sorted_tables}


def _get_one_sid_by_any_id(
    tables: Dict[str, Table],
    table_name: str,
    *,
    sid: Optional[int] = None,
    id: Optional[int] = None,
    oparlId: Optional[str] = None,
    oparlKey: Optional[str] = None,
) -> Optional[int]:
    t = tables[table_name]
    conds = []
    if sid is not None:
        conds.append(t.c.sid == sid)
    if id is not None and "id" in t.c:
        conds.append(t.c.id == id)
    if oparlId is not None and "oparlId" in t.c:
        conds.append(t.c.oparlId == oparlId)
    if oparlKey is not None and "oparlKey" in t.c:
        conds.append(t.c.oparlKey == oparlKey)
    if not conds:
        raise ValueError("Provide at least one identifier (sid, id, oparlId, oparlKey).")

    q = select(t.c.sid).where(or_(*conds)).limit(1)
    return q


def get_entity_by_sid(engine: Engine, tables: Dict[str, Table], table_name: str, sid: int) -> Dict[str, Any]:
    t = tables[table_name]
    q = select(t).where(t.c.sid == sid).limit(1)
    with engine.connect() as cx:
        row = cx.execute(q).mappings().first()
    return dict(row) if row else {}


def _meeting_sid_by_date(engine: Engine, tables: Dict[str, Table], meeting_date: Union[date, datetime, str]) -> List[int]:
    """
    Resolve meeting(s) by a date. Uses Meeting.start (explicit scalar col if you enabled it),
    otherwise falls back to JSON extraction of data['start'].

    Best practice: ensure Meeting.start is an explicit DateTime column as you implemented scalar extraction.
    """
    t = tables["Meeting"]

    # normalize
    if isinstance(meeting_date, str):
        # accept YYYY-MM-DD
        meeting_date = datetime.strptime(meeting_date, "%Y-%m-%d").date()
    elif isinstance(meeting_date, datetime):
        meeting_date = meeting_date.date()

    # prefer explicit 'start' column if present
    if "start" in t.c:
        # compare by date range [00:00, 24:00)
        start_dt = datetime.combine(meeting_date, datetime.min.time())
        end_dt = datetime.combine(meeting_date, datetime.max.time())
        q = select(t.c.sid).where(and_(t.c.start >= start_dt, t.c.start <= end_dt))
    else:
        # fallback: JSON_EXTRACT (MariaDB supports JSON_EXTRACT). Uses SQLAlchemy textless approach:
        # t.c.data["start"].as_string() isn't portable for MariaDB reflection, so keep it simple:
        from sqlalchemy import text
        q = text(
            "SELECT sid FROM Meeting "
            "WHERE DATE(JSON_UNQUOTE(JSON_EXTRACT(data, '$.start'))) = :d"
        ).bindparams(d=str(meeting_date))
        with engine.connect() as cx:
            return [int(r[0]) for r in cx.execute(q).all()]

    with engine.connect() as cx:
        return [int(r[0]) for r in cx.execute(q).all()]


# ----------------------------
# 1) Given File oparlKey => find all Papers, Consultations, Meetings, AgendaItems referencing it
# ----------------------------
def find_references_to_file(
    engine: Engine,
    tables: Dict[str, Table],
    file_oparlkey: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Finds all entities referencing a File by:
    - single FK columns pointing to File (rare, but supported)
    - association tables that target File: <Src>__<field>__File
    Returns rows as dicts for Paper/Consultation/Meeting/AgendaItem.
    """
    # resolve file sid
    file_t = tables["File"]
    q_file_sid = select(file_t.c.sid).where(file_t.c.oparlKey == file_oparlkey).limit(1)
    with engine.connect() as cx:
        file_sid_row = cx.execute(q_file_sid).first()
    if not file_sid_row:
        return {"Paper": [], "Consultation": [], "Meeting": [], "AgendaItem": []}
    file_sid = int(file_sid_row[0])

    results: Dict[str, List[Dict[str, Any]]] = {"Paper": [], "Consultation": [], "Meeting": [], "AgendaItem": []}

    # helper: fetch by sids
    def fetch_by_sids(table_name: str, sids: List[int]) -> List[Dict[str, Any]]:
        if not sids:
            return []
        t = tables[table_name]
        q = select(t).where(t.c.sid.in_(sids))
        with engine.connect() as cx:
            return [dict(r) for r in cx.execute(q).mappings().all()]

    # --- association tables that point to File
    for src in ["Paper", "Consultation", "Meeting", "AgendaItem"]:
        # any assoc table whose name ends with "__File" and starts with f"{src}__"
        assoc_names = [n for n in tables.keys() if n.startswith(f"{src}__") and n.endswith("__File")]
        src_sids: List[int] = []
        for an in assoc_names:
            at = tables[an]
            q = select(at.c.srcSid).where(at.c.tgtSid == file_sid)
            with engine.connect() as cx:
                src_sids.extend([int(r[0]) for r in cx.execute(q).all()])
        # dedupe
        src_sids = sorted(set(src_sids))
        results[src] = fetch_by_sids(src, src_sids)

    # --- also catch single-fk columns that target File (if any exist)
    # e.g. SomeTable.someFileSid -> File.sid
    for src in ["Paper", "Consultation", "Meeting", "AgendaItem"]:
        t = tables[src]
        fk_cols = [c for c in t.c.keys() if c.lower().endswith("filesid")]  # heuristic
        for c in fk_cols:
            q = select(t).where(getattr(t.c, c) == file_sid)
            with engine.connect() as cx:
                more = [dict(r) for r in cx.execute(q).mappings().all()]
            # merge without duplicates
            existing = {r["sid"] for r in results[src]}
            for r in more:
                if r.get("sid") not in existing:
                    results[src].append(r)

    return results


# ----------------------------
# 2) Find start/end date of Meeting or Consultation given by id or oparlId
# ----------------------------
def get_start_end_for_entity(
    engine: Engine,
    tables: Dict[str, Table],
    entity_type: str,  # "Meeting" or "Consultation"
    *,
    sid: Optional[int] = None,
    id: Optional[int] = None,
    oparlId: Optional[str] = None,
) -> Optional[Tuple[Optional[datetime], Optional[datetime]]]:
    """
    Returns (start, end) as datetimes if the columns exist, otherwise tries JSON.
    """
    if entity_type not in ("Meeting", "Consultation"):
        raise ValueError("entity_type must be 'Meeting' or 'Consultation'")

    t = tables[entity_type]
    conds = []
    if sid is not None:
        conds.append(t.c.sid == sid)
    if id is not None and "id" in t.c:
        conds.append(t.c.id == id)
    if oparlId is not None and "oparlId" in t.c:
        conds.append(t.c.oparlId == oparlId)
    if not conds:
        raise ValueError("Provide sid or id or oparlId")

    # Prefer explicit columns if present
    has_start = "start" in t.c
    has_end = "end" in t.c

    if has_start or has_end:
        cols = []
        if has_start:
            cols.append(t.c.start)
        else:
            cols.append(None)
        if has_end:
            cols.append(t.c.end)
        else:
            cols.append(None)

        # build query selecting present cols
        sel_cols = [c for c in [t.c.start if has_start else None, t.c.end if has_end else None] if c is not None]
        q = select(*sel_cols).where(or_(*conds)).limit(1)
        with engine.connect() as cx:
            row = cx.execute(q).first()
        if not row:
            return None
        # map back
        if has_start and has_end:
            return row[0], row[1]
        if has_start and not has_end:
            return row[0], None
        if not has_start and has_end:
            return None, row[0]

    # Fallback to JSON
    from sqlalchemy import text
    sql = f"""
        SELECT
          JSON_UNQUOTE(JSON_EXTRACT(data, '$.start')) AS start,
          JSON_UNQUOTE(JSON_EXTRACT(data, '$.end'))   AS end
        FROM {entity_type}
        WHERE {"sid = :sid" if sid is not None else ("id = :id" if id is not None else "oparlId = :oparlId")}
        LIMIT 1
    """
    params = {}
    if sid is not None:
        params["sid"] = sid
    elif id is not None:
        params["id"] = id
    else:
        params["oparlId"] = oparlId

    with engine.connect() as cx:
        row = cx.execute(text(sql), params).first()
    if not row:
        return None
    start_s, end_s = row[0], row[1]
    return (parse_datetime_maybe(start_s), parse_datetime_maybe(end_s))


# ----------------------------
# 3) Find all AgendaItems for a Meeting given by date or by id/oparlId
# ----------------------------
def get_agendaitems_for_meeting(
    engine: Engine,
    tables: Dict[str, Table],
    *,
    meeting_sid: Optional[int] = None,
    meeting_id: Optional[int] = None,
    meeting_oparlId: Optional[str] = None,
    meeting_date: Optional[Union[date, datetime, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Uses AgendaItem.meetingSid FK.
    If you pass meeting_date, returns agenda items for all meetings on that date.
    """
    ai = tables["AgendaItem"]
    m = tables["Meeting"]

    meeting_sids: List[int] = []

    if meeting_date is not None:
        meeting_sids = _meeting_sid_by_date(engine, tables, meeting_date)
    else:
        q = _get_one_sid_by_any_id(
            tables,
            "Meeting",
            sid=meeting_sid,
            id=meeting_id,
            oparlId=meeting_oparlId,
        )
        with engine.connect() as cx:
            row = cx.execute(q).first()
        if row:
            meeting_sids = [int(row[0])]

    if not meeting_sids:
        return []

    if "meetingSid" not in ai.c:
        raise RuntimeError("AgendaItem table has no meetingSid column (FK not created).")

    q_ai = select(ai).where(ai.c.meetingSid.in_(meeting_sids)).order_by(ai.c.sid)
    with engine.connect() as cx:
        return [dict(r) for r in cx.execute(q_ai).mappings().all()]


# ----------------------------
# 4) Find all Consultations for a Meeting given by date or by id/oparlId
# ----------------------------
def get_consultations_for_meeting(
    engine: Engine,
    tables: Dict[str, Table],
    *,
    meeting_sid: Optional[int] = None,
    meeting_id: Optional[int] = None,
    meeting_oparlId: Optional[str] = None,
    meeting_date: Optional[Union[date, datetime, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Uses Consultation.meetingSid FK (if present in your JSON; many OParl exports have it).
    If not present, you can alternatively join via Meeting.consultation association table
    (this function also checks for that).
    """
    cons = tables["Consultation"]

    meeting_sids: List[int] = []
    if meeting_date is not None:
        meeting_sids = _meeting_sid_by_date(engine, tables, meeting_date)
    else:
        q = _get_one_sid_by_any_id(
            tables,
            "Meeting",
            sid=meeting_sid,
            id=meeting_id,
            oparlId=meeting_oparlId,
        )
        with engine.connect() as cx:
            row = cx.execute(q).first()
        if row:
            meeting_sids = [int(row[0])]

    if not meeting_sids:
        return []

    # Preferred: Consultation.meetingSid
    if "meetingSid" in cons.c:
        q = select(cons).where(cons.c.meetingSid.in_(meeting_sids)).order_by(cons.c.sid)
        with engine.connect() as cx:
            return [dict(r) for r in cx.execute(q).mappings().all()]

    # Fallback: association table from Meeting -> Consultation if it exists
    assoc_name_candidates = [n for n in tables.keys() if n.startswith("Meeting__") and n.endswith("__Consultation")]
    if assoc_name_candidates:
        assoc = tables[assoc_name_candidates[0]]
        # find consultations linked to those meeting sids
        q = select(assoc.c.tgtSid).where(assoc.c.srcSid.in_(meeting_sids))
        with engine.connect() as cx:
            cons_sids = sorted({int(r[0]) for r in cx.execute(q).all()})
        if not cons_sids:
            return []
        q2 = select(cons).where(cons.c.sid.in_(cons_sids)).order_by(cons.c.sid)
        with engine.connect() as cx:
            return [dict(r) for r in cx.execute(q2).mappings().all()]

    raise RuntimeError("No way to link Consultation to Meeting (missing meetingSid and no Meeting__*__Consultation table).")

# ----------------------------
# 5) Given an AgendaItem (by sid), find all referenced File.oparlId values via any association table named AgendaItem__<field>__File
# ----------------------------

def get_file_oparlids_for_agendaitem(
    engine: Engine,
    tables: Dict[str, Table],
    agendaitem_sid: int,
) -> List[str]:
    """
    Return File.oparlId values referenced by a given AgendaItem (by sid),
    via any association table named: AgendaItem__<field>__File.

    De-duplicates while preserving order.
    """
    # find all assoc tables like AgendaItem__<field>__File
    assoc_names = sorted(
        [n for n in tables.keys() if n.startswith("AgendaItem__") and n.endswith("__File")]
    )
    if not assoc_names:
        return []

    file_t = tables.get("File")
    if file_t is None:
        return []

    file_sids: List[int] = []
    for an in assoc_names:
        at = tables[an]
        q = select(at.c.tgtSid).where(at.c.srcSid == agendaitem_sid)
        with engine.connect() as cx:
            file_sids.extend([int(r[0]) for r in cx.execute(q).all() if r[0] is not None])

    if not file_sids:
        return []

    # fetch File.oparlId for those sids
    qf = select(file_t.c.sid, file_t.c.oparlId).where(file_t.c.sid.in_(sorted(set(file_sids))))
    with engine.connect() as cx:
        sid_to_oid = {int(sid): oid for sid, oid in cx.execute(qf).all()}

    # de-dup in original order
    seen: Set[str] = set()
    out: List[str] = []
    for fsid in file_sids:
        oid = sid_to_oid.get(fsid)
        if oid and oid not in seen:
            seen.add(oid)
            out.append(oid)

    return out



def search_agendaitems_by_name(
    engine: Engine,
    tables: Dict[str, Table],
    query_text: str,
    *,
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    Query AgendaItems where AgendaItem.name LIKE %query_text% and return rows enriched with:
      - meetingDate (date)
      - fileOparlIds (list[str]) via get_file_oparlids_for_agendaitem()

    Requires:
      - AgendaItem.name (explicit scalar column)
      - AgendaItem.meetingSid
      - Meeting.start (explicit) preferred; falls back to JSON start if missing
    """
    ai = tables["AgendaItem"]
    m = tables["Meeting"]

    if "meetingSid" not in ai.c:
        raise RuntimeError("AgendaItem.meetingSid column missing (FK not created).")
    if "name" not in ai.c:
        raise RuntimeError("AgendaItem.name column missing (run generator with scalar columns enabled).")

    like_pat = f"%{query_text}%"

    q_ai = (
        select(ai)  # return full row
        .where(ai.c.name.like(like_pat))
        .limit(limit)
    )

    with engine.connect() as cx:
        ai_rows = [dict(r) for r in cx.execute(q_ai).mappings().all()]

    if not ai_rows:
        return []

    # meetingSid list
    meeting_sids = sorted({int(r["meetingSid"]) for r in ai_rows if r.get("meetingSid") is not None})

    # map meetingSid -> meetingDate
    meeting_date_map: Dict[int, Any] = {}

    if "start" in m.c:
        q_m = select(m.c.sid, func.date(m.c.start).label("meetingDate")).where(m.c.sid.in_(meeting_sids))
        with engine.connect() as cx:
            for sid, mdate in cx.execute(q_m).all():
                if sid is not None:
                    meeting_date_map[int(sid)] = mdate
    else:
        # JSON fallback
        from sqlalchemy import text
        q_m = text(
            "SELECT sid, DATE(JSON_UNQUOTE(JSON_EXTRACT(data,'$.start'))) AS meetingDate "
            "FROM Meeting WHERE sid IN :sids"
        ).bindparams(sids=tuple(meeting_sids))
        with engine.connect() as cx:
            for sid, mdate in cx.execute(q_m).all():
                if sid is not None:
                    meeting_date_map[int(sid)] = mdate

    out: List[Dict[str, Any]] = []
    for r in ai_rows:
        msid = r.get("meetingSid")
        msid_i = int(msid) if msid is not None else None
        mdate = meeting_date_map.get(msid_i)

        # year filtering (if we have a date)
        if mdate is not None and (year_start is not None or year_end is not None):
            y = mdate.year
            if year_start is not None and y < year_start:
                continue
            if year_end is not None and y > year_end:
                continue

        ai_sid = r.get("sid")
        ai_sid_i = int(ai_sid) if ai_sid is not None else None

        r2 = dict(r)
        r2["meetingDate"] = mdate
        r2["fileOparlIds"] = (
            get_file_oparlids_for_agendaitem(engine, tables, ai_sid_i) if ai_sid_i is not None else []
        )

        out.append(r2)

    # optional: stable ordering by meetingDate then sid
    out.sort(key=lambda x: (x["meetingDate"] is None, x["meetingDate"], x.get("sid")))
    return out

# ----------------------------
# Example usage
# ----------------------------
if __name__ == "__main__":
    import private as pr
    db_url = f"mariadb+pymysql://{pr.DB_USER}:{pr.DB_PWD}@localhost/{pr.DB_NAME}"
    engine = make_engine(db_url)
    tables = reflect_tables(engine)

    # 1) file references
    refs = find_references_to_file(engine, tables, file_oparlkey="502742")
    print({k: len(v) for k, v in refs.items()})

    # 2) start/end for meeting by numeric id
    se = get_start_end_for_entity(engine, tables, "Meeting", id=961)
    print("Meeting 961 start/end:", se)

    # 3) agenda items for meeting by date
    ais = get_agendaitems_for_meeting(engine, tables, meeting_date="2004-10-26")
    print("AgendaItems on 2004-10-26:", len(ais))
    if len(ais) > 0:
        print("AgendaItems:", ais)

    # 4) consultations for meeting by oparlId
    cons = get_consultations_for_meeting(engine, tables, meeting_oparlId="https://web1.karlsruhe.de/ris/oparl/bodies/0001/meetings/1455")
    print("Consultations:", len(cons))
    if len(cons) > 0:
        print("Consultations:", cons)
    
    
    # --- TEST SECTION (add/replace in your existing if __name__ == "__main__": block) ---

    # 5) search AgendaItems by name (returns values), print in main
    print("\n--- AgendaItem name search ---")
    user_input = input("Enter search text for AgendaItem name: ").strip()

    year_start_s = input("Start year (optional): ").strip()
    year_end_s = input("End year (optional): ").strip()
    year_start = int(year_start_s) if year_start_s else None
    year_end = int(year_end_s) if year_end_s else None

    if user_input:
        rows = search_agendaitems_by_name(
            engine,
            tables,
            user_input,
            year_start=year_start,
            year_end=year_end,
            limit=200,
        )

        if not rows:
            print("No AgendaItems found.")
        else:
            print(f"Found {len(rows)} AgendaItems:")
            for r in rows:
                ai_sid = r.get("sid")
                name = r.get("name")
                mdate = r.get("meetingDate")
                files = r.get("fileOparlIds", [])

                print(f"[{ai_sid}] {name}  -> meeting date: {mdate}  | files: {len(files)}")
                for oid in files:
                    print(f"    - {oid}")