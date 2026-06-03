"""Utility to retrieve agenda item IDs and related meeting information for a given file.

The function `get_related_ids` returns a list of tuples:
    (agenda_item_id, meeting_id or None, meeting_start_date or None)

It follows the schema where `File` links to `AgendaItem` via the many‑to‑many
association table `AgendaItem__auxiliaryFile__File`. The `AgendaItem` may have a
foreign key `meetingSid` to `Meeting`, which can be NULL.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import Table, MetaData, select

# Import helper to create DB engine
from sqlalchemy import create_engine  # needed for openDb


# Copied from refs
def openDb():
    """Create and return a SQLAlchemy engine based on `private` settings.
    The `private` module defines the variables `RO_USER`, `RO_PWD`,
    `DB_HOST`, and `DB_NAME`. This function builds the PostgreSQL URL and
    returns an engine with `future=True` and connection pooling enabled.
    """
    try:
        import private as pr
        db_url = f"postgresql+psycopg2://{pr.RO_USER}:{pr.RO_PWD}@{pr.DB_HOST}/{pr.DB_NAME}"
    except ImportError as exc:
        raise ImportError("Could not import private for DB connection settings") from exc

    return create_engine(db_url, future=True, pool_pre_ping=True)



def get_related_ids(oparl_key: str) -> List[Tuple[int, Optional[int], Optional[datetime]]]:
    """Return agenda item IDs and related meeting info for a file.

    Args:
        oparl_key: The `oparlKey` value of the target `File` record.

    Returns:
        A list of tuples ``(agenda_item_id, meeting_id, meeting_start_date)``.
        ``meeting_id`` and ``meeting_start_date`` are ``None`` when the agenda
        item is not linked to a meeting.
    """
    engine = openDb()
    metadata = MetaData()

    # Core tables
    file_tbl = Table("File", metadata, autoload_with=engine)
    paper_tbl = Table("Paper", metadata, autoload_with=engine)
    agenda_tbl = Table("AgendaItem", metadata, autoload_with=engine)
    meeting_tbl = Table("Meeting", metadata, autoload_with=engine)
    consultation_tbl = Table("Consultation", metadata, autoload_with=engine)
    # Association table linking File <-> Meeting
    fm_assoc_tbl = Table("File__meeting__Meeting", metadata, autoload_with=engine)
    # Association table linking File <-> Paper
    fp_assoc_tbl = Table("File__paper__Paper", metadata, autoload_with=engine)
    # Association table linking Paper <-> File (reverse direction, should be the same as above but included for clarity)
    pf_assoc_tbl = Table("Paper__auxiliaryFile__File", metadata, autoload_with=engine)
    # Association table linking AgendaItem <-> File
    af_assoc_tbl = Table("AgendaItem__auxiliaryFile__File", metadata, autoload_with=engine)
    # Assiocation paper -> consultation (used in some cases instead of paper -> meeting)
    pc_assoc_tbl = Table("Paper__consultation__Consultation", metadata, autoload_with=engine)

    # Resolve the file's internal SID
    stmt_file = select(file_tbl.c.sid,file_tbl.c.name).where(file_tbl.c.oparlKey == oparl_key)
    with engine.connect() as conn:
        file_row = conn.execute(stmt_file).first()
    if not file_row:
        return []
    file_sid = file_row[0]
    file_name = file_row[1]

    result = [{"file": {"file_sid": file_sid, "file_name": file_name}, "agenda_items": [], "meetings": [], "papers": []}]


    # First find meetings via fm_assoc_tbl
    stmt_meetings = (
        select(
            meeting_tbl.c.sid.label("meeting_id"),
            meeting_tbl.c.start_date.label("meeting_start"),
        )
        .select_from(
            fm_assoc_tbl
            .join(meeting_tbl, fm_assoc_tbl.c.tgtSid == meeting_tbl.c.sid)
        )
        .where(fm_assoc_tbl.c.srcSid == file_sid)
    )
    with engine.connect() as conn:
        meeting_rows = conn.execute(stmt_meetings).fetchall()
    result[0]["meetings"] = [{"meeting_id": row.meeting_id, "meeting_start": row.meeting_start} for row in meeting_rows]        
    
    # Find papers via file => paper association, which may be linked to agenda items and meetings
    stmt_papers = (
        select(paper_tbl.c.sid.label("paper_id"))
        .select_from(
            fp_assoc_tbl
            .join(paper_tbl, fp_assoc_tbl.c.tgtSid == paper_tbl.c.sid)
        )
        .where(fp_assoc_tbl.c.srcSid == file_sid)
    )
    with engine.connect() as conn:
        paper_rows = conn.execute(stmt_papers).fetchall()
    result[0]["papers"] = [{"paper_id": row.paper_id} for row in paper_rows]    
    
    # Find papers via reverse search from paper => file association, which may be linked to agenda items and meetings
    stmt_papers = (
        select(paper_tbl.c.sid.label("paper_id"))
        .select_from(
            pf_assoc_tbl
            .join(paper_tbl, pf_assoc_tbl.c.srcSid == paper_tbl.c.sid)
        )
        .where(pf_assoc_tbl.c.tgtSid == file_sid)
    )
    with engine.connect() as conn:
        paper_rows = conn.execute(stmt_papers).fetchall()
    existing_paper_ids = {p["paper_id"] for p in result[0]["papers"]}
    for row in paper_rows:
        if row.paper_id not in existing_paper_ids:
            result[0]["papers"].append({"paper_id": row.paper_id})
            existing_paper_ids.add(row.paper_id)    

    # we might need to look up consultations from papers and get meetingSid form the consultation. 
    # add meetings this way, if possible, to capture meetings linked via consultations instead of directly from agenda items
    for paper in result[0]["papers"]:
        stmt_consultations = (
            select(consultation_tbl.c.sid.label("consultation_id"), consultation_tbl.c.meetingSid.label("meeting_id"),
                   meeting_tbl.c.name.label("meeting_name"), meeting_tbl.c.start_date.label("meeting_start"))
            .select_from(
                pc_assoc_tbl
                .join(consultation_tbl, pc_assoc_tbl.c.tgtSid == consultation_tbl.c.sid)
                .join(meeting_tbl, consultation_tbl.c.meetingSid == meeting_tbl.c.sid)
            )
            .where(pc_assoc_tbl.c.srcSid == paper["paper_id"])
        )
        with engine.connect() as conn:
            consultation_rows = conn.execute(stmt_consultations).fetchall()
        for row in consultation_rows:
            if row.meeting_id is not None and all(m["meeting_id"] != row.meeting_id for m in result[0]["meetings"]):
                # Add meeting from consultation if not already in the list
                result[0]["meetings"].append({"consultation_id": row.consultation_id, "meeting_id": row.meeting_id, "meeting_name": row.meeting_name, "meeting_start": row.meeting_start})

    
    # Join through the association to agenda items and optionally to meetings
    stmt = (
        select(
            agenda_tbl.c.sid.label("agenda_id"),
            agenda_tbl.c.name.label("agenda_name"),
            agenda_tbl.c.result.label("agenda_result"),
            meeting_tbl.c.sid.label("meeting_id"),
            meeting_tbl.c.name.label("meeting_name"),
            meeting_tbl.c.start_date.label("meeting_start"),
        )
        .select_from(
            af_assoc_tbl
            .join(agenda_tbl, af_assoc_tbl.c.srcSid == agenda_tbl.c.sid)
            .join(meeting_tbl, agenda_tbl.c.meetingSid == meeting_tbl.c.sid)
        )
        .where(af_assoc_tbl.c.tgtSid == file_sid)
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).fetchall()

    result[0]["agenda_items"] = [{"agenda_id": row.agenda_id, "agenda_name": row.agenda_name, "agenda_result": row.agenda_result, "meeting_id": row.meeting_id, "meeting_name": row.meeting_name, "meeting_start": row.meeting_start} for row in rows if row.agenda_id is not None]

    # Add meetings from agenda items if not already in the list
    existing_meeting_ids = {m["meeting_id"] for m in result[0]["meetings"]}
    for row in rows:
        if row.meeting_id is not None and row.meeting_id not in existing_meeting_ids:
            result[0]["meetings"].append({"meeting_id": row.meeting_id, "meeting_name": row.meeting_name, "meeting_start": row.meeting_start})
            existing_meeting_ids.add(row.meeting_id)

    return result


if __name__ == "__main__":
    import random
    import json
    testing = 100 # number of random keys to test
    items_seen = set()
    engine = openDb()
    with engine.connect() as conn:
        file_keys = conn.execute(select(Table("File", MetaData(), autoload_with=engine).c.oparlKey)).fetchall()
    file_keys = [row[0] for row in file_keys]

    random_keys = random.sample(file_keys, min(testing, len(file_keys)))
    random_keys[0] = "602806"
    print(f"Testing {len(random_keys)} random file keys...")
    for test_key in random_keys:
        output = get_related_ids(test_key)
        for item in output:
            for agenda in item["agenda_items"]:
                items_seen.add("agenda")
                if agenda["agenda_result"] is not None:
                    items_seen.add("agenda_result")
            for meeting in item["meetings"]:
                items_seen.add("meeting")
            for paper in item["papers"]:
                items_seen.add("paper")
        print(f"Results for file key: {test_key}")
        print(json.dumps(output, default=str, indent=2))
        if len(items_seen) >= 4:
            print("All items have been seen at least once.")
            break
        print(f"Total unique agenda items, meetings, and papers seen: {len(items_seen)}")
