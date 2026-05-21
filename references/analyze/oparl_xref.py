"""
    Below is an example Python script that demonstrates how you might:

    Load all OParl JSON files from a previous crawl (e.g., the karlsruhe_oparl_crawl folder).

    Index them in memory by their id.

    Build a simple “cross-reference” so we can see which File belongs to which Paper, which Paper belongs to which Meeting, which Meeting belongs to which Body, etc.

    Generate a table (CSV) showing one row per file with the following columns:
        Body: Name of the council or committee.
        Meeting Date: e.g. startDate of the meeting (YYYY-MM-DD).
        Agenda Item: If we find a linked agenda item name (not always present).
        Paper Title: The “name” field of the Paper resource.
        File Name: The actual PDF/DOC file name, e.g. 00647355.pdf.
        File Type: e.g. “pdf” or “docx” (based on extension or mimeType).
        Date Created: e.g. from the File’s created or Paper’s created.
        File Download URL: The actual URL to retrieve the file (e.g. downloadUrl).

Because OParl can be quite flexible, there’s no single guaranteed path from Body → Meeting → Paper → File. Some systems link them differently, or use Consultation objects. This script does a best-effort approach:

    For Paper objects, we look at paper.file, paper.mainFile, or paper.auxiliaryFile.
    For Meeting objects, we see if there’s a meeting.agendaItem array referencing Papers.
    For Body objects, we see if they have body.meeting or body.paper references.
    We then build simple “reverse indexes” so we know which Paper references which File, which Meeting references which AgendaItem, etc.

Finally, we walk through each File resource to produce one row in a table, including any found links up to Paper, Meeting, and Body.

    Disclaimer: Real OParl data may have multiple references or none at all. The code below tries to find at most one connected Meeting and Body for each file, just to build a concise table. Adapt as needed if you want all references or if your data structure differs.
""" 

import os
import json
import csv
import re
from typing import Dict, List, Any

CRAWL_FOLDER = "ko"
OUTPUT_CSV   = "ko_document_table.csv"

def load_all_resources(crawl_folder: str) -> Dict[str, Any]:
    """
    Reads all JSON files in 'crawl_folder'. For each resource found (dict),
    store it in a global index keyed by resource 'id'.
    Some files may contain a list of resources.
    Returns: { id_string: resource_dict, ... }
    """
    resources_by_id = {}

    # Walk the entire folder for .json files
    for root, dirs, files in os.walk(crawl_folder):
        for filename in files:
            if not filename.lower().endswith(".json"):
                continue
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            if isinstance(data, dict):
                # Single resource or something else
                res_id = data.get("id")
                if res_id:
                    resources_by_id[res_id] = data
            elif isinstance(data, list):
                # Possibly multiple resources in a list
                for item in data:
                    if isinstance(item, dict):
                        res_id = item.get("id")
                        if res_id:
                            resources_by_id[res_id] = item
            # else: ignore other formats
    return resources_by_id

def get_type(resource: dict) -> str:
    """
    Extract the OParl resource type, e.g. 'File', 'Paper', 'Meeting'.
    e.g. type = 'https://schema.oparl.org/1.1/File' -> 'File'
    """
    t = resource.get("type", "")
    if t.startswith("http"):
        return t.rstrip("/").split("/")[-1]
    return "Unknown"

def extract_extension_from_filename(filename: str) -> str:
    """
    Return 'pdf' or 'docx' etc. from the file name or path.
    """
    filename_lower = filename.lower().split("?", 1)[0]  # strip query
    if "." in filename_lower:
        return filename_lower.rsplit(".", 1)[-1]  # e.g. 'pdf'
    return ""

def parse_date_yyyy_mm_dd(date_str: str) -> str:
    """
    For an ISO date/time like '2024-07-23T18:00:00+02:00',
    return '2024-07-23'.
    If not parseable, return empty string.
    """
    # Simple approach: match "YYYY-MM-DD"
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", date_str)
    if match:
        return match.group(1)
    return ""

def build_reverse_indexes(resources_by_id: Dict[str, dict]):
    """
    Build a few helpful 'reverse indexes':
      - file -> paper(s)
      - paper -> meeting(s)
      - meeting -> body
      - agendaItem -> meeting
      So we can trace from a File up to a Paper, then up to a Meeting, then a Body.
    Returns a tuple: (files_to_papers, papers_to_meetings, meeting_to_body, agendaitem_to_meeting)
    """
    files_to_papers = {}      # file_id -> list of paper_id
    papers_to_meetings = {}   # paper_id -> list of meeting_id
    meeting_to_body = {}      # meeting_id -> body_id
    agendaitem_to_meeting = {}# agendaitem_id -> meeting_id

    # 1) For each Paper, see if 'file' or 'auxiliaryFile' or 'mainFile' references a File ID
    for r_id, r_data in resources_by_id.items():
        r_type = get_type(r_data)

        if r_type == "Paper":
            # paper.file can be a string or list of strings
            all_file_refs = []
            for field in ["file", "auxiliaryFile", "mainFile"]:
                val = r_data.get(field)
                if not val:
                    continue
                if isinstance(val, str):
                    all_file_refs.append(val)
                elif isinstance(val, list):
                    for x in val:
                        if isinstance(x, str):
                            all_file_refs.append(x)
            # Add them to the reverse index
            for f_id in all_file_refs:
                files_to_papers.setdefault(f_id, []).append(r_id)

        elif r_type == "Meeting":
            # meeting belongs to some body, or maybe the meeting array is in the body
            # Usually, the Body references "meeting", not the other way around, so let's see if there's a 'body' field
            # If none, we'll rely on the Body's references to 'meeting' below.
            # Also, 'agendaItem' might be a list of IDs
            agenda_list = r_data.get("agendaItem")
            if isinstance(agenda_list, str):
                agenda_list = [agenda_list]
            if isinstance(agenda_list, list):
                for ag_id in agenda_list:
                    if isinstance(ag_id, str):
                        agendaitem_to_meeting[ag_id] = r_id
                    elif isinstance(ag_id, dict):
                        # Possibly { "id": "https://...", ... }
                        item_id = ag_id.get("id")
                        if isinstance(item_id, str):
                            agendaitem_to_meeting[item_id] = r_id
                    # else skip if no valid ID

        elif r_type == "Body":
            # body.meeting might be a string or list, let's see if it references some meetings
            meet = r_data.get("meeting")
            if isinstance(meet, str):
                meet = [meet]
            if isinstance(meet, list):
                for m_id in meet:
                    if isinstance(m_id, str):
                        meeting_to_body[m_id] = r_id
                    elif isinstance(m_id, dict):
                        # Possibly { "id": "https://...", ... }
                        item_id = m_id.get("id")
                        if isinstance(item_id, str):
                            meeting_to_body[m_id] = r_id
                    # else skip if no valid ID

            # body.paper might also exist
            pap = r_data.get("paper")
            if isinstance(pap, str):
                pap = [pap]
            if isinstance(pap, list):
                # so we know these papers belong to this body
                for p_id in pap:
                    # We'll do a second pass below (or we can build a separate index: paper -> body)
                    # But let's keep it simple.
                    pass

        elif r_type == "AgendaItem":
            # Some OParl variants store a direct reference to 'meeting' or 'paper'
            # We'll handle that if we see it
            pass

    # 2) For each AgendaItem, check if it references a Paper (and we know which Meeting it belongs to).
    #    Then we can update papers_to_meetings
    for r_id, r_data in resources_by_id.items():
        r_type = get_type(r_data)
        if r_type == "AgendaItem":
            # see if we can find which meeting this belongs to:
            this_meeting = agendaitem_to_meeting.get(r_id)
            if not this_meeting:
                # some OParl implementations store agendaItem.meeting = meetingID
                possible_meeting = r_data.get("meeting")
                if isinstance(possible_meeting, str):
                    this_meeting = possible_meeting
                    agendaitem_to_meeting[r_id] = this_meeting

            # If there's a 'paper' field, link those papers to that meeting
            pap = r_data.get("paper")
            if isinstance(pap, str):
                pap = [pap]
            if isinstance(pap, list) and this_meeting:
                for p_id in pap:
                    # add p_id -> this_meeting in papers_to_meetings
                    papers_to_meetings.setdefault(p_id, []).append(this_meeting)

        elif r_type == "Consultation":
            # Some systems use Consultation objects linking Paper + AgendaItem + Meeting
            # e.g. consultation["paper"], consultation["agendaItem"], consultation["meeting"]
            pap = r_data.get("paper")
            ag = r_data.get("agendaItem")
            mt = r_data.get("meeting")
            if isinstance(pap, str) and isinstance(mt, str):
                papers_to_meetings.setdefault(pap, []).append(mt)
            # If 'agendaItem' references a distinct item, that item might also link to a meeting
            # It's quite flexible, we do a best-effort approach

            # If there's only Paper + AgendaItem, we might combine with the agendaitem_to_meeting approach
            # We'll skip the details for brevity.

            pass

    # 3) For each Paper, see if we can find which meeting it belongs to from 'papers_to_meetings' or from 'paper.meeting'
    for r_id, r_data in resources_by_id.items():
        if get_type(r_data) == "Paper":
            # Some OParl data might store paper.meeting = ID or list of IDs
            pap_meet = r_data.get("meeting")
            if isinstance(pap_meet, str):
                papers_to_meetings.setdefault(r_id, []).append(pap_meet)
            elif isinstance(pap_meet, list):
                for mm in pap_meet:
                    papers_to_meetings.setdefault(r_id, []).append(mm)

    return files_to_papers, papers_to_meetings, meeting_to_body, agendaitem_to_meeting

def main():
    print("[INFO] Loading all resources from folder:", CRAWL_FOLDER)
    resources_by_id = load_all_resources(CRAWL_FOLDER)
    print(f"[INFO] Loaded {len(resources_by_id)} resources.")

    print("[INFO] Building reverse indexes (file->paper, paper->meeting, meeting->body, etc.)")
    files_to_papers, papers_to_meetings, meeting_to_body, _ = build_reverse_indexes(resources_by_id)

    # We will create a CSV with columns:
    fieldnames = [
        "Body",
        "Meeting Date",
        "Agenda Item",
        "Paper Title",
        "File Name",
        "File Type",
        "Date Created",
        "File Download URL",
    ]

    rows = []

    # Let's iterate over all resources that are type=File
    for f_id, f_data in resources_by_id.items():
        if get_type(f_data) != "File":
            continue

        # Basic info from the file resource
        file_name = f_data.get("fileName", "")                    # e.g. '00647355.pdf'
        download_url = f_data.get("downloadUrl", "")             # e.g. 'https://.../somefile.pdf'
        file_created = f_data.get("created", "")                 # e.g. '2023-05-17T00:00:00+02:00'
        file_created_short = parse_date_yyyy_mm_dd(file_created)  # '2023-05-17'
        mime_type = f_data.get("mimeType", "")

        # If we don't have an extension from fileName, guess from downloadUrl or mimeType
        if file_name:
            ext_guess = extract_extension_from_filename(file_name)
        else:
            ext_guess = extract_extension_from_filename(download_url)

        if not ext_guess and mime_type:
            # e.g. 'application/pdf' -> 'pdf'
            if mime_type.startswith("application/"):
                ext_guess = mime_type.split("/", 1)[1]  # 'pdf'
        
        # Now let's see if any Paper references this File
        # We do a best effort; it's possible multiple Papers reference the same File
        referencing_papers = files_to_papers.get(f_id, [])
        if not referencing_papers:
            # no Paper found, we still create a row
            rows.append({
                "Body": "",
                "Meeting Date": "",
                "Agenda Item": "",
                "Paper Title": "",
                "File Name": file_name,
                "File Type": ext_guess,
                "Date Created": file_created_short,
                "File Download URL": download_url
            })
            continue

        # For each referencing paper, we might also find referencing meetings
        for paper_id in referencing_papers:
            paper_data = resources_by_id.get(paper_id, {})
            paper_title = paper_data.get("name", "")
            paper_created = parse_date_yyyy_mm_dd(paper_data.get("created", ""))

            # Agenda item name is tricky; it’s not always in the Paper directly
            # We'll skip for brevity or do a quick check if there's a single associated AgendaItem
            # For now, let's just store paper_title. 
            # If you want to see which AgendaItem references this Paper, see the build_reverse_indexes code.

            # Next: find meeting(s) for this Paper
            referencing_meetings = []
            if paper_id in papers_to_meetings:
                referencing_meetings = papers_to_meetings[paper_id]

            if not referencing_meetings:
                # No known meeting, so body + date unknown
                rows.append({
                    "Body": "",
                    "Meeting Date": paper_created,  # fallback to paper's create date
                    "Agenda Item": "",
                    "Paper Title": paper_title,
                    "File Name": file_name,
                    "File Type": ext_guess,
                    "Date Created": file_created_short,
                    "File Download URL": download_url
                })
            else:
                # For each referencing meeting
                for m_id in referencing_meetings:
                    m_data = resources_by_id.get(m_id, {})
                    meeting_date = parse_date_yyyy_mm_dd(m_data.get("startDate", ""))
                    # see if there's a body
                    b_id = None
                    if m_id in meeting_to_body:
                        b_id = meeting_to_body[m_id]
                    if not b_id and "body" in m_data:
                        # some OParl data has meeting.body
                        val = m_data["body"]
                        if isinstance(val, str):
                            b_id = val

                    body_name = ""
                    if b_id and b_id in resources_by_id:
                        body_data = resources_by_id[b_id]
                        body_name = body_data.get("name", "")

                    # For agenda item name, we can do more lookups, but let's skip for brevity
                    # If you want to do it thoroughly, you’d find all AgendaItems for the meeting,
                    # see which references the paper, etc.
                    # We'll just store an empty string for Agenda Item.

                    rows.append({
                        "Body": body_name,
                        "Meeting Date": meeting_date,
                        "Agenda Item": "",  # advanced cross-linking is possible
                        "Paper Title": paper_title,
                        "File Name": file_name,
                        "File Type": ext_guess,
                        "Date Created": file_created_short,
                        "File Download URL": download_url
                    })

    # Write the table to a CSV
    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"[INFO] Wrote {len(rows)} rows to {OUTPUT_CSV}")
    print("[INFO] Done.")


if __name__ == "__main__":
    main()

