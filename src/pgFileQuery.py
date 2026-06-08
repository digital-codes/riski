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

        db_url = (
            f"postgresql+psycopg2://{pr.RO_USER}:{pr.RO_PWD}@{pr.DB_HOST}/{pr.DB_NAME}"
        )
    except ImportError as exc:
        raise ImportError(
            "Could not import private for DB connection settings"
        ) from exc

    return create_engine(db_url, future=True, pool_pre_ping=True)

def find_unreferenced_files() -> List[Tuple[int, str, str]]:
    """Find files that are not linked to any agenda items or meetings or papers.
    Files can reference Meetings, or Papers.
    Files can be referenced by AgendaItems, Papers, or Meetings.
    Check all possible associations to find files that are not linked to any of these entities.

    Returns:
        A list of tuples (file_sid, file_name, file_oparlId) for unreferenced files.
    """
    engine = openDb()
    metadata = MetaData()

    file_tbl = Table("File", metadata, autoload_with=engine)
    fm_assoc_tbl = Table("File__meeting__Meeting", metadata, autoload_with=engine)
    fp_assoc_tbl = Table("File__paper__Paper", metadata, autoload_with=engine)
    af_assoc_tbl = Table(
        "AgendaItem__auxiliaryFile__File", metadata, autoload_with=engine
    )
    mf_assoc_tbl = Table(
        "Meeting__auxiliaryFile__File", metadata, autoload_with=engine
    )
    pf_assoc_tbl = Table(
        "Paper__auxiliaryFile__File", metadata, autoload_with=engine
    )

    stmt = (
        select(file_tbl.c.sid, file_tbl.c.name, file_tbl.c.oparlId)
        .select_from(file_tbl.outerjoin(fm_assoc_tbl, file_tbl.c.sid == fm_assoc_tbl.c.srcSid)
                     .outerjoin(fp_assoc_tbl, file_tbl.c.sid == fp_assoc_tbl.c.srcSid)
                     .outerjoin(af_assoc_tbl, file_tbl.c.sid == af_assoc_tbl.c.tgtSid)
                     .outerjoin(mf_assoc_tbl, file_tbl.c.sid == mf_assoc_tbl.c.tgtSid)
                     .outerjoin(pf_assoc_tbl, file_tbl.c.sid == pf_assoc_tbl.c.tgtSid))
        .where(fm_assoc_tbl.c.srcSid.is_(None), fp_assoc_tbl.c.srcSid.is_(None), af_assoc_tbl.c.tgtSid.is_(None),
               mf_assoc_tbl.c.tgtSid.is_(None), pf_assoc_tbl.c.tgtSid.is_(None))
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).fetchall()

    return [(row.sid, row.name, row.oparlId) for row in rows]


def get_related_ids_for_file(
    oparl_key: str,
) -> List[Tuple[int, Optional[int], Optional[datetime]]]:
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
    af_assoc_tbl = Table(
        "AgendaItem__auxiliaryFile__File", metadata, autoload_with=engine
    )
    # Assiocation paper -> consultation (used in some cases instead of paper -> meeting)
    pc_assoc_tbl = Table(
        "Paper__consultation__Consultation", metadata, autoload_with=engine
    )

    # Resolve the file's internal SID
    stmt_file = select(file_tbl.c.sid, file_tbl.c.name, file_tbl.c.oparlId).where(
        file_tbl.c.oparlKey == oparl_key
    )
    with engine.connect() as conn:
        file_row = conn.execute(stmt_file).first()
    if not file_row:
        return []
    file_sid = file_row[0]
    file_name = file_row[1]
    file_oparl_id = file_row[2]

    result = [
        {
            "file": {"file_sid": file_sid, "file_name": file_name, "file_oparlId": file_oparl_id},
            "agenda_items": [],
            "meetings": [],
            "papers": [],
        }
    ]

    # First find meetings via fm_assoc_tbl
    stmt_meetings = (
        select(
            meeting_tbl.c.sid.label("meeting_id"),
            meeting_tbl.c.start_date.label("meeting_start"),
            meeting_tbl.c.oparlId.label("meeting_oparlId"),
        )
        .select_from(
            fm_assoc_tbl.join(meeting_tbl, fm_assoc_tbl.c.tgtSid == meeting_tbl.c.sid)
        )
        .where(fm_assoc_tbl.c.srcSid == file_sid)
    )
    with engine.connect() as conn:
        meeting_rows = conn.execute(stmt_meetings).fetchall()
    result[0]["meetings"] = [
        {"meeting_id": row.meeting_id, "meeting_start": row.meeting_start, "meeting_oparlId": row.meeting_oparlId}
        for row in meeting_rows
    ]

    # Find papers via file => paper association, which may be linked to agenda items and meetings
    stmt_papers = (
        select(paper_tbl.c.sid.label("paper_id"), paper_tbl.c.oparlId.label("paper_oparlId"))
        .select_from(
            fp_assoc_tbl.join(paper_tbl, fp_assoc_tbl.c.tgtSid == paper_tbl.c.sid)
        )
        .where(fp_assoc_tbl.c.srcSid == file_sid)
    )
    with engine.connect() as conn:
        paper_rows = conn.execute(stmt_papers).fetchall()
    result[0]["papers"] = [{"paper_id": row.paper_id, "paper_oparlId": row.paper_oparlId} for row in paper_rows]

    # Find papers via reverse search from paper => file association, which may be linked to agenda items and meetings
    stmt_papers = (
        select(paper_tbl.c.sid.label("paper_id"), paper_tbl.c.oparlId.label("paper_oparlId"))
        .select_from(
            pf_assoc_tbl.join(paper_tbl, pf_assoc_tbl.c.srcSid == paper_tbl.c.sid)
        )
        .where(pf_assoc_tbl.c.tgtSid == file_sid)
    )
    with engine.connect() as conn:
        paper_rows = conn.execute(stmt_papers).fetchall()
    existing_paper_ids = {p["paper_id"] for p in result[0]["papers"]}
    for row in paper_rows:
        if row.paper_id not in existing_paper_ids:
            result[0]["papers"].append({"paper_id": row.paper_id, "paper_oparlId": row.paper_oparlId})
            existing_paper_ids.add(row.paper_id)

    # we might need to look up consultations from papers and get meetingSid form the consultation.
    # add meetings this way, if possible, to capture meetings linked via consultations instead of directly from agenda items
    for paper in result[0]["papers"]:
        stmt_consultations = (
            select(
                consultation_tbl.c.sid.label("consultation_id"),
                consultation_tbl.c.oparlId.label("consultation_oparlId"),
                consultation_tbl.c.meetingSid.label("meeting_id"),
                consultation_tbl.c.agendaItemSid.label("agenda_item_id"),
                meeting_tbl.c.name.label("meeting_name"),
                meeting_tbl.c.start_date.label("meeting_start"),
                meeting_tbl.c.oparlId.label("meeting_oparlId"),
                agenda_tbl.c.name.label("agenda_item_name"),
                agenda_tbl.c.result.label("agenda_item_result"),
                agenda_tbl.c.oparlId.label("agenda_item_oparlId"),
            )
            .select_from(
                pc_assoc_tbl.join(
                    consultation_tbl, pc_assoc_tbl.c.tgtSid == consultation_tbl.c.sid
                ).join(meeting_tbl, consultation_tbl.c.meetingSid == meeting_tbl.c.sid)
                .join(agenda_tbl, consultation_tbl.c.agendaItemSid == agenda_tbl.c.sid)
            )
            .where(pc_assoc_tbl.c.srcSid == paper["paper_id"])
        )
        with engine.connect() as conn:
            consultation_rows = conn.execute(stmt_consultations).fetchall()
        for row in consultation_rows:
            if row.meeting_id is not None and all(
                m["meeting_id"] != row.meeting_id for m in result[0]["meetings"]
            ):
                # Add meeting from consultation if not already in the list
                result[0]["meetings"].append(
                    {
                        "consultation_id": row.consultation_id,
                        "consultation_oparlId": row.consultation_oparlId,
                        "meeting_id": row.meeting_id,
                        "meeting_name": row.meeting_name,
                        "meeting_start": row.meeting_start,
                        "meeting_oparlId": row.meeting_oparlId,
                        "agenda_item_id": row.agenda_item_id,
                        "agenda_item_name": row.agenda_item_name,
                        "agenda_item_result": row.agenda_item_result,
                        "agenda_item_oparlId": row.agenda_item_oparlId,
                    }
                )

    # Join through the association to agenda items and optionally to meetings
    stmt = (
        select(
            agenda_tbl.c.sid.label("agenda_id"),
            agenda_tbl.c.name.label("agenda_name"),
            agenda_tbl.c.result.label("agenda_result"),
            agenda_tbl.c.oparlId.label("agenda_oparlId"),
            meeting_tbl.c.sid.label("meeting_id"),
            meeting_tbl.c.name.label("meeting_name"),
            meeting_tbl.c.start_date.label("meeting_start"),
            meeting_tbl.c.oparlId.label("meeting_oparlId"),
        )
        .select_from(
            af_assoc_tbl.join(
                agenda_tbl, af_assoc_tbl.c.srcSid == agenda_tbl.c.sid
            ).join(meeting_tbl, agenda_tbl.c.meetingSid == meeting_tbl.c.sid)
        )
        .where(af_assoc_tbl.c.tgtSid == file_sid)
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).fetchall()

    result[0]["agenda_items"] = [
        {
            "agenda_id": row.agenda_id,
            "agenda_name": row.agenda_name,
            "agenda_result": row.agenda_result,
            "agenda_oparlId": row.agenda_oparlId,
            "meeting_id": row.meeting_id,
            "meeting_name": row.meeting_name,
            "meeting_start": row.meeting_start,
            "meeting_oparlId": row.meeting_oparlId,
        }
        for row in rows
        if row.agenda_id is not None
    ]

    # Add meetings from agenda items if not already in the list
    existing_meeting_ids = {m["meeting_id"] for m in result[0]["meetings"]}
    for row in rows:
        if row.meeting_id is not None and row.meeting_id not in existing_meeting_ids:
            result[0]["meetings"].append(
                {
                    "meeting_id": row.meeting_id,
                    "meeting_name": row.meeting_name,
                    "meeting_start": row.meeting_start,
                    "meeting_oparlId": row.meeting_oparlId,
                }
            )
            existing_meeting_ids.add(row.meeting_id)

    return result


def get_related_ids_for_agenda_item(
    oparl_key: str,
) -> List:
    """Return files and related meeting info for an agenda item.

    Args:
        oparl_key: The `oparlKey` value of the target `AgendaItem` record.

    Returns:
        A list containing a dictionary with agenda item details, related files,
        meetings, papers, and consultations.
    """
    engine = openDb()
    metadata = MetaData()

    # Core tables
    agenda_tbl = Table("AgendaItem", metadata, autoload_with=engine)
    file_tbl = Table("File", metadata, autoload_with=engine)
    paper_tbl = Table("Paper", metadata, autoload_with=engine)
    meeting_tbl = Table("Meeting", metadata, autoload_with=engine)
    consultation_tbl = Table("Consultation", metadata, autoload_with=engine)
    # Association table linking AgendaItem <-> File
    af_assoc_tbl = Table(
        "AgendaItem__auxiliaryFile__File", metadata, autoload_with=engine
    )
    # Association table linking Paper <-> Consultation
    pc_assoc_tbl = Table(
        "Paper__consultation__Consultation", metadata, autoload_with=engine
    )
    # Association table linking File <-> Paper
    fp_assoc_tbl = Table("File__paper__Paper", metadata, autoload_with=engine)
    # Association table linking Paper <-> File (reverse direction)
    pf_assoc_tbl = Table("Paper__auxiliaryFile__File", metadata, autoload_with=engine)

    # Resolve the agenda item's internal SID
    stmt_agenda = select(agenda_tbl.c.sid, agenda_tbl.c.name, agenda_tbl.c.result, agenda_tbl.c.meetingSid, agenda_tbl.c.consultationSid, agenda_tbl.c.oparlId).where(
        agenda_tbl.c.oparlKey == oparl_key
    )
    with engine.connect() as conn:
        agenda_row = conn.execute(stmt_agenda).first()
    if not agenda_row:
        return []
    agenda_sid = agenda_row[0]
    agenda_name = agenda_row[1]
    agenda_result = agenda_row[2]
    meeting_sid = agenda_row[3]
    consultation_sid = agenda_row[4]
    agenda_oparl_id = agenda_row[5]

    result = [
        {
            "agenda_item": {
                "agenda_sid": agenda_sid,
                "agenda_name": agenda_name,
                "agenda_result": agenda_result,
                "agenda_oparlId": agenda_oparl_id,
            },
            "files": [],
            "meetings": [],
            "papers": [],
            "consultations": [],
        }
    ]

    # Get the meeting directly linked to this agenda item, if it exists
    if meeting_sid is not None:
        stmt_meeting = select(
            meeting_tbl.c.sid.label("meeting_id"),
            meeting_tbl.c.name.label("meeting_name"),
            meeting_tbl.c.start_date.label("meeting_start"),
            meeting_tbl.c.oparlId.label("meeting_oparlId"),
        ).where(meeting_tbl.c.sid == meeting_sid)
        with engine.connect() as conn:
            meeting_row = conn.execute(stmt_meeting).first()
        if meeting_row:
            result[0]["meetings"] = [
                {
                    "meeting_id": meeting_row.meeting_id,
                    "meeting_name": meeting_row.meeting_name,
                    "meeting_start": meeting_row.meeting_start,
                    "meeting_oparlId": meeting_row.meeting_oparlId,
                }
            ]

    # Get the consultation directly linked to this agenda item, if it exists
    if consultation_sid is not None:
        stmt_consultation = select(
            consultation_tbl.c.sid.label("consultation_id"),
            consultation_tbl.c.oparlId.label("consultation_oparlId"),
            consultation_tbl.c.meetingSid.label("consultation_meeting_id"),
            consultation_tbl.c.role.label("consultation_role"),
        ).where(consultation_tbl.c.sid == consultation_sid)
        with engine.connect() as conn:
            consultation_row = conn.execute(stmt_consultation).first()
        if consultation_row:
            result[0]["consultations"] = [
                {
                    "consultation_id": consultation_row.consultation_id,
                    "consultation_oparlId": consultation_row.consultation_oparlId,
                    "consultation_meeting_id": consultation_row.consultation_meeting_id,
                    "consultation_role": consultation_row.consultation_role,
                }
            ]

    # Find files via agenda item <-> file association
    stmt_files = (
        select(file_tbl.c.sid.label("file_id"), file_tbl.c.name.label("file_name"), file_tbl.c.oparlId.label("file_oparlId"))
        .select_from(
            af_assoc_tbl.join(file_tbl, af_assoc_tbl.c.tgtSid == file_tbl.c.sid)
        )
        .where(af_assoc_tbl.c.srcSid == agenda_sid)
    )
    with engine.connect() as conn:
        file_rows = conn.execute(stmt_files).fetchall()
    result[0]["files"] = [
        {"file_id": row.file_id, "file_name": row.file_name, "file_oparlId": row.file_oparlId} for row in file_rows
    ]

    # Find consultations linked to this agenda item
    # Get the meeting directly linked to this agenda item, if it exists
    if consultation_sid is None:
        stmt_consultations = (
            select(
                consultation_tbl.c.sid.label("consultation_id"),
                consultation_tbl.c.oparlId.label("consultation_oparlId"),
                consultation_tbl.c.meetingSid.label("consultation_meeting_id"),
            )
            .select_from(consultation_tbl)
            .where(consultation_tbl.c.agendaItemSid == agenda_sid)
        )
        with engine.connect() as conn:
            consultation_rows = conn.execute(stmt_consultations).fetchall()
        result[0]["consultations"] = [
            {"consultation_id": row.consultation_id, "consultation_oparlId": row.consultation_oparlId, "consultation_meeting_id": row.consultation_meeting_id}
            for row in consultation_rows
        ]

    # Find papers via consultations
    for consultation in result[0]["consultations"]:
        stmt_papers = (
            select(paper_tbl.c.sid.label("paper_id"), paper_tbl.c.name.label("paper_name"), paper_tbl.c.oparlId.label("paper_oparlId"))
            .select_from(
                pc_assoc_tbl.join(paper_tbl, pc_assoc_tbl.c.srcSid == paper_tbl.c.sid)
            )
            .where(pc_assoc_tbl.c.tgtSid == consultation["consultation_id"])
        )
        with engine.connect() as conn:
            paper_rows = conn.execute(stmt_papers).fetchall()
        for row in paper_rows:
            if not any(p["paper_id"] == row.paper_id for p in result[0]["papers"]):
                result[0]["papers"].append(
                    {"paper_id": row.paper_id, "paper_name": row.paper_name, "paper_oparlId": row.paper_oparlId}
                )

    # Find files via papers (forward and reverse associations)
    for paper in result[0]["papers"]:
        print(f"Finding files for paper {paper['paper_id']} linked to agenda item {agenda_sid}...")
        # Forward: paper -> file (pf_assoc: srcSid=Paper, tgtSid=File)
        stmt_files_via_paper = (
            select(file_tbl.c.sid.label("file_id"), file_tbl.c.name.label("file_name"), file_tbl.c.oparlId.label("file_oparlId"))
            .select_from(
                pf_assoc_tbl.join(file_tbl, pf_assoc_tbl.c.tgtSid == file_tbl.c.sid)
            )
            .where(pf_assoc_tbl.c.srcSid == paper["paper_id"])
        )
        with engine.connect() as conn:
            file_rows = conn.execute(stmt_files_via_paper).fetchall()
        for row in file_rows:
            if not any(f["file_id"] == row.file_id for f in result[0]["files"]):
                result[0]["files"].append(
                    {"file_id": row.file_id, "file_name": row.file_name, "file_oparlId": row.file_oparlId}
                )

        # Reverse: file -> paper (fp_assoc: srcSid=File, tgtSid=Paper)
        stmt_files_via_paper_rev = (
            select(file_tbl.c.sid.label("file_id"), file_tbl.c.name.label("file_name"), file_tbl.c.oparlId.label("file_oparlId"))
            .select_from(
                fp_assoc_tbl.join(file_tbl, fp_assoc_tbl.c.srcSid == file_tbl.c.sid)
            )
            .where(fp_assoc_tbl.c.tgtSid == paper["paper_id"])
        )
        with engine.connect() as conn:
            file_rows = conn.execute(stmt_files_via_paper_rev).fetchall()
        for row in file_rows:
            if not any(f["file_id"] == row.file_id for f in result[0]["files"]):
                result[0]["files"].append(
                    {"file_id": row.file_id, "file_name": row.file_name, "file_oparlId": row.file_oparlId}
                )

    return result


if __name__ == "__main__":
    import random
    import json

    testing = 100  # number of random keys to test
    items_seen = set()
    engine = openDb()
    with engine.connect() as conn:
        file_keys = conn.execute(
            select(Table("File", MetaData(), autoload_with=engine).c.oparlKey)
        ).fetchall()
    file_keys = [row[0] for row in file_keys]

    random_keys = random.sample(file_keys, min(testing, len(file_keys)))
    random_keys[0] = "602806"
    print(f"Testing {len(random_keys)} random file keys...")
    for test_key in random_keys:
        output = get_related_ids_for_file(test_key)
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
        print(
            f"Total unique agenda items, meetings, and papers seen: {len(items_seen)}"
        )

    # Test for agenda items
    print("\n" + "="*80)
    print("Testing agenda items...")
    print("="*80 + "\n")
    
    items_seen_agenda = set()
    engine = openDb()
    with engine.connect() as conn:
        agenda_keys = conn.execute(
            select(Table("AgendaItem", MetaData(), autoload_with=engine).c.oparlKey)
        ).fetchall()
    agenda_keys = [row[0] for row in agenda_keys]
    
    random_agenda_keys = random.sample(agenda_keys, min(testing, len(agenda_keys)))
    random_agenda_keys[0] = "18953"
    print(f"Testing {len(random_agenda_keys)} random agenda item keys...")
    for test_key in random_agenda_keys:
        output = get_related_ids_for_agenda_item(test_key)
        for item in output:
            for file in item["files"]:
                items_seen_agenda.add("file")
            for paper in item["papers"]:
                items_seen_agenda.add("paper")
            for consultation in item["consultations"]:
                items_seen_agenda.add("consultation")
            for meeting in item["meetings"]:
                items_seen_agenda.add("meeting")
            if item["agenda_item"]["agenda_result"] is not None:
                items_seen_agenda.add("result")
        print(f"Results for agenda item key: {test_key}")
        print(json.dumps(output, default=str, indent=2))
        if len(items_seen_agenda) >= 5:
            print("All items have been seen at least once.")
            break
        print(
            f"Total unique files, papers, consultations, results, and meetings seen: {len(items_seen_agenda)}"
        )
    
    
    unrefed_files = find_unreferenced_files()
    print(f"\nFound {len(unrefed_files)} unreferenced files:")
    for file_sid, file_name, file_oparlId in unrefed_files:
        print(f"File SID: {file_sid}, Name: {file_name}, OParl ID: {file_oparlId}")
        
