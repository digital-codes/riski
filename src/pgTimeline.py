import os
import json
import requests
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np
from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine, MetaData, Table, select, and_, or_, func, Column, Integer, String
from sqlalchemy.orm import sessionmaker

import numpy as np
from pgvector.sqlalchemy import Vector

# Import helper to create DB engine
from sqlalchemy import create_engine  # needed for openDb

import requests
import private as pr


# Configuration
EMBEDDING_API_URL = None
EMBEDDING_MODEL = None
EMBEDDING_API_KEY = None
TOP_K = 100
TIMELINE_WINDOW_DAYS = 30



Base = declarative_base()

# Vector Model
class Embeddings(Base):
    """Embeddings table with vector column (requires pgvector extension)"""
    __tablename__ = 'contentEmbeddings'
    
    id = Column(Integer, primary_key=True)
    oparlKey = Column(String)
    value = Column(Vector(1024))  # 1024-dimensional vector
    # Assuming you have a vector column named 'embedding'
    # Adjust column name/type based on your schema

# File Model
class File(Base):
    """File table for metadata and content"""
    __tablename__ = 'File'
    
    id = Column(Integer, primary_key=True)
    date = Column(String)
    oparlKey = Column(String)
    name = Column(String)
    downloadurl = Column(String)
    content = Column(String)



def call_embedding_model(text: str, api_url: str, api_key: str, model: str) -> tuple[list[float], float]:
    """
    Call remote embedding model and return (vector, score)
    Adjust based on your actual API endpoint
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    
    response = requests.post(
        api_url,
        json={"input": text, "model": model},
        headers=headers
    )
    response.raise_for_status()
    
    result = response.json()
    # print(f"API response: {result}")  # Debug print to check response structure
    # Adjust based on actual API response structure
    if isinstance(result, dict) and result.get("data") and isinstance(result["data"], list) and len(result["data"]) > 0:
        vector = result["data"][0].get('embedding', [])
        print(f"Raw vector from API: {vector[:5]}...")  # Debug print to check raw vector
        vector = np.array(vector)
        vector = vector / np.linalg.norm(vector)  # Normalize the vector to unit length
        vector = vector.tolist()
    elif isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict) and 'embedding' in result[0]:
        vector = result[0]['embedding'][0]
        vector = np.array(vector)
        vector = vector / np.linalg.norm(vector)  # Normalize the vector to unit length
        vector = vector.tolist()
    else:
        vector = []
    print(f"Received vector of length {len(vector)}")  # Debug print to check vector length
    return vector

# here, threshold is a distance threshold, so we want to keep vectors with distance <= threshold (i.e. similarity above a certain level)
def filter_by_threshold(vectors_with_scores: list[tuple], threshold: float) -> list[tuple]:
    """Filter vectors above threshold"""
    return [(vec, score) for vec, score in vectors_with_scores if score <= threshold]

def query_vector_similarity(session, query_vector: list[float], top_k: int = 10) -> list[int]:
    """
    Query PostgreSQL for vector similarity using pgvector
    Requires pgvector extension installed
    """
    # Using cosine similarity (<=> operator in pgvector)
    # Adjust column name based on your schema
    query = session.query(
        Embeddings.oparlKey,
        (Embeddings.value.cosine_distance(query_vector)).label("distance")
    ).order_by("distance").limit(top_k)
    return query.all()



def get_db_session(db_url: str):
    """Create and return a new database session."""
    engine = create_engine(db_url, future=True)
    Session = sessionmaker(bind=engine)
    return Session()



def find_related_objects(session, file_sids: List[str]) -> Dict[str, List[Dict]]:
    """
    Find all OParl objects related to the given file sids through junction tables.

    Args:
        session: SQLAlchemy session
        file_sids: List of File sids to find related objects for

    Returns:
        Dictionary with object types as keys and lists of related objects as values
    """
    engine = session.get_bind()
    metadata = MetaData()
    
    
    # Load tables
    agenda_tbl = Table('AgendaItem', metadata, autoload_with=engine)
    paper_tbl = Table('Paper', metadata, autoload_with=engine)
    meeting_tbl = Table('Meeting', metadata, autoload_with=engine)
    consultation_tbl = Table('Consultation', metadata, autoload_with=engine)
    organization_tbl = Table('Organization', metadata, autoload_with=engine)
    
    # Load association tables
    af_assoc_tbl = Table('AgendaItem__auxiliaryFile__File', metadata, autoload_with=engine)
    pf_assoc_tbl = Table('Paper__auxiliaryFile__File', metadata, autoload_with=engine)
    mf_assoc_tbl = Table('Meeting__auxiliaryFile__File', metadata, autoload_with=engine)
    pc_assoc_tbl = Table('Paper__consultation__Consultation', metadata, autoload_with=engine)
    ma_assoc_tbl = Table('Meeting__agendaItem__AgendaItem', metadata, autoload_with=engine)
    co_assoc_tbl = Table('Consultation__organization__Organization', metadata, autoload_with=engine)
    po_assoc_tbl = Table('Paper__underDirectionOf__Organization', metadata, autoload_with=engine)
    
    related_objects = {
        "AgendaItem": [],
        "Paper": [],
        "Meeting": [],
        "Consultation": [],
        "Organization": [],
        "Person": [],
        "Body": [],
        "Location": []
    }

    # 1. Find AgendaItems connected to Files
    stmt = (
        select(
            agenda_tbl.c.sid,
            agenda_tbl.c.id,
            agenda_tbl.c.oparlKey,
            agenda_tbl.c.oparlId,
            agenda_tbl.c.name,
            agenda_tbl.c.start_date,
            agenda_tbl.c.end_date,
            agenda_tbl.c.meetingSid,
            agenda_tbl.c.number,
            agenda_tbl.c.result
        )
        .select_from(
            af_assoc_tbl.join(
                agenda_tbl, af_assoc_tbl.c.srcSid == agenda_tbl.c.sid
            )
        )
        .where(af_assoc_tbl.c.tgtSid.in_(file_sids.values()))
    )
    with engine.connect() as conn:
        agenda_items = conn.execute(stmt).fetchall()
    
    for row in agenda_items:
        related_objects["AgendaItem"].append({
            "sid": row.sid,
            "id": row.id,
            "oparlKey": row.oparlKey,
            "oparlId": row.oparlId,
            "name": row.name,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "meetingSid": row.meetingSid,
            "number": row.number,
            "result": row.result
        })

    print(f"Found {len(related_objects['AgendaItem'])} agenda items related to files")  # Debugging line

    # 2. Find Papers connected to Files
    stmt = (
        select(
            paper_tbl.c.sid,
            paper_tbl.c.id,
            paper_tbl.c.oparlKey,
            paper_tbl.c.oparlId,
            paper_tbl.c.name,
            paper_tbl.c.date,
            paper_tbl.c.reference,
            paper_tbl.c.papertype,
            paper_tbl.c.bodySid
        )
        .select_from(
            pf_assoc_tbl.join(
                paper_tbl, pf_assoc_tbl.c.srcSid == paper_tbl.c.sid
            )
        )
        .where(pf_assoc_tbl.c.tgtSid.in_(file_sids.values()))
    )
    with engine.connect() as conn:
        papers = conn.execute(stmt).fetchall()
    
    for row in papers:
        related_objects["Paper"].append({
            "sid": row.sid,
            "id": row.id,
            "oparlKey": row.oparlKey,
            "oparlId": row.oparlId,
            "name": row.name,
            "date": row.date,
            "reference": row.reference,
            "paperType": row.papertype,
            "bodySid": row.bodySid
        })
    print(f"Found {len(related_objects['Paper'])} papers related to files")  # Debugging line
    
    # 3. Find Meetings connected to Files
    stmt = (
        select(
            meeting_tbl.c.sid,
            meeting_tbl.c.id,
            meeting_tbl.c.oparlKey,
            meeting_tbl.c.oparlId,
            meeting_tbl.c.name,
            meeting_tbl.c.start_date,
            meeting_tbl.c.end_date
        )
        .select_from(
            mf_assoc_tbl.join(
                meeting_tbl, mf_assoc_tbl.c.srcSid == meeting_tbl.c.sid
            )
        )
        .where(mf_assoc_tbl.c.tgtSid.in_(file_sids.values()))
    )
    with engine.connect() as conn:
        meetings = conn.execute(stmt).fetchall()
    
    for row in meetings:
        related_objects["Meeting"].append({
            "sid": row.sid,
            "id": row.id,
            "oparlKey": row.oparlKey,
            "oparlId": row.oparlId,
            "name": row.name,
            "start_date": row.start_date,
            "end_date": row.end_date
        })

    # 4. For Papers, find related Consultations
    paper_sids = [p["sid"] for p in related_objects["Paper"]]
    if paper_sids:
        stmt = (
            select(
                consultation_tbl.c.sid,
                consultation_tbl.c.id,
                consultation_tbl.c.oparlKey,
                consultation_tbl.c.oparlId,
                consultation_tbl.c.role,
                consultation_tbl.c.authoritative,
                consultation_tbl.c.agendaItemSid,
                consultation_tbl.c.meetingSid,
                consultation_tbl.c.paperSid
            )
            .select_from(
                pc_assoc_tbl.join(
                    consultation_tbl, pc_assoc_tbl.c.tgtSid == consultation_tbl.c.sid
                )
            )
            .where(pc_assoc_tbl.c.srcSid.in_(paper_sids))
        )
        with engine.connect() as conn:
            consultations = conn.execute(stmt).fetchall()
        
        for row in consultations:
            related_objects["Consultation"].append({
                "sid": row.sid,
                "id": row.id,
                "oparlKey": row.oparlKey,
                "oparlId": row.oparlId,
                "role": row.role,
                "authoritative": row.authoritative,
                "agendaItemSid": row.agendaItemSid,
                "meetingSid": row.meetingSid,
                "paperSid": row.paperSid
            })
    print(f"Found {len(related_objects['Consultation'])} consultations related to papers")  # Debugging line

    # 5. For Meetings, find related AgendaItems
    meeting_sids = [m["sid"] for m in related_objects["Meeting"]]
    if meeting_sids:
        stmt = (
            select(
                agenda_tbl.c.sid,
                agenda_tbl.c.id,
                agenda_tbl.c.oparlKey,
                agenda_tbl.c.oparlId,
                agenda_tbl.c.name,
                agenda_tbl.c.start_date,
                agenda_tbl.c.end_date,
                agenda_tbl.c.meetingSid,
                agenda_tbl.c.number,
                agenda_tbl.c.result
            )
            .select_from(
                ma_assoc_tbl.join(
                    agenda_tbl, ma_assoc_tbl.c.tgtSid == agenda_tbl.c.sid
                )
            )
            .where(ma_assoc_tbl.c.srcSid.in_(meeting_sids))
        )
        with engine.connect() as conn:
            meeting_agenda_items = conn.execute(stmt).fetchall()
        
        for row in meeting_agenda_items:
            if not any(ai["sid"] == row.sid for ai in related_objects["AgendaItem"]):
                related_objects["AgendaItem"].append({
                    "sid": row.sid,
                    "id": row.id,
                    "oparlKey": row.oparlKey,
                    "oparlId": row.oparlId,
                    "name": row.name,
                    "start_date": row.start_date,
                    "end_date": row.end_date,
                    "meetingSid": row.meetingSid,
                    "number": row.number,
                    "result": row.result
                })
    print(f"Found {len(related_objects['AgendaItem'])} agenda items related to meetings")  # Debugging line

    # 6. For AgendaItems, find related Consultations
    agenda_item_sids = [ai["sid"] for ai in related_objects["AgendaItem"]]
    if agenda_item_sids:
        stmt = select(
            consultation_tbl.c.sid,
            consultation_tbl.c.id,
            consultation_tbl.c.oparlKey,
            consultation_tbl.c.oparlId,
            consultation_tbl.c.role,
            consultation_tbl.c.authoritative,
            consultation_tbl.c.agendaItemSid,
            consultation_tbl.c.meetingSid,
            consultation_tbl.c.paperSid
        ).where(consultation_tbl.c.agendaItemSid.in_(agenda_item_sids))
        
        with engine.connect() as conn:
            agenda_consultations = conn.execute(stmt).fetchall()
        
        for row in agenda_consultations:
            if not any(c["sid"] == row.sid for c in related_objects["Consultation"]):
                related_objects["Consultation"].append({
                    "sid": row.sid,
                    "id": row.id,
                    "oparlKey": row.oparlKey,
                    "oparlId": row.oparlId,
                    "role": row.role,
                    "authoritative": row.authoritative,
                    "agendaItemSid": row.agendaItemSid,
                    "meetingSid": row.meetingSid,
                    "paperSid": row.paperSid
                })

    # 7. For Consultations, find related Organizations
    consultation_sids = [c["sid"] for c in related_objects["Consultation"]]
    if consultation_sids:
        stmt = (
            select(
                organization_tbl.c.sid,
                organization_tbl.c.id,
                organization_tbl.c.oparlKey,
                organization_tbl.c.oparlId,
                organization_tbl.c.name,
                organization_tbl.c.classification,
                organization_tbl.c.shortname
            )
            .select_from(
                co_assoc_tbl.join(
                    organization_tbl, co_assoc_tbl.c.tgtSid == organization_tbl.c.sid
                )
            )
            .where(co_assoc_tbl.c.srcSid.in_(consultation_sids))
        )
        with engine.connect() as conn:
            consultation_orgs = conn.execute(stmt).fetchall()
        
        for row in consultation_orgs:
            related_objects["Organization"].append({
                "sid": row.sid,
                "id": row.id,
                "oparlKey": row.oparlKey,
                "oparlId": row.oparlId,
                "name": row.name,
                "classification": row.classification,
                "shortName": row.shortname
            })

    print(f"Found {len(related_objects['Organization'])} organizations related to consultations")  # Debugging line

    # 8. For Papers, find related Organizations (underDirectionOf)
    if paper_sids:
        stmt = (
            select(
                organization_tbl.c.sid,
                organization_tbl.c.id,
                organization_tbl.c.oparlKey,
                organization_tbl.c.oparlId,
                organization_tbl.c.name,
                organization_tbl.c.classification,
                organization_tbl.c.shortname
            )
            .select_from(
                po_assoc_tbl.join(
                    organization_tbl, po_assoc_tbl.c.tgtSid == organization_tbl.c.sid
                )
            )
            .where(po_assoc_tbl.c.srcSid.in_(paper_sids))
        )
        with engine.connect() as conn:
            paper_orgs = conn.execute(stmt).fetchall()
        
        for row in paper_orgs:
            if not any(o["sid"] == row.sid for o in related_objects["Organization"]):
                related_objects["Organization"].append({
                    "sid": row.sid,
                    "id": row.id,
                    "oparlKey": row.oparlKey,
                    "oparlId": row.oparlId,
                    "name": row.name,
                    "classification": row.classification,
                    "shortName": row.shortname
                })

        print(f"Found {len(related_objects['Organization'])} organizations related to papers")  # Debugging line

    return related_objects

def build_timeline(related_objects: Dict[str, List[Dict]]) -> List[Dict]:
    """
    Build a timeline from related OParl objects, sorted by date.
    """
    timeline_events = []
    for obj_type, objects in related_objects.items():
        print(f"Processing {len(objects)} objects of type {obj_type} for timeline")  # Debugging line
        for obj in objects:
            # Determine the best date field for this object type
            date_field = None
            if obj_type == "Meeting":
                date_field = obj.get("start_date") or obj.get("end_date")
            elif obj_type == "AgendaItem":
                date_field = obj.get("start_date") or obj.get("end_date")
            elif obj_type == "Paper":
                date_field = obj.get("date")
            elif obj_type == "File":
                date_field = obj.get("date")
            elif obj_type == "Consultation":
                # Consultations don't have direct dates, use related object dates
                continue
            else:
                date_field = obj.get("created") or obj.get("modified")

            if date_field is None:
                continue

            event = {
                "type": obj_type,
                "id": obj.get("id"),
                "oparlKey": obj.get("oparlKey"),
                "oparlId": obj.get("oparlId"),
                "name": obj.get("name") or obj.get("fileName") or f"{obj_type} {obj.get('id')}",
                "date": date_field,
                "details": {k: v for k, v in obj.items()
                          if k not in ["start_date", "end_date", "date", "created", "modified"]}
            }
            timeline_events.append(event)

    # Sort by date
    timeline_events.sort(key=lambda x: x["date"] if x["date"] else datetime.max)
    print(f"Built timeline with {len(timeline_events)} events after sorting")  # Debugging line

    return timeline_events

def group_timeline_events(timeline_events: List[Dict], window_days: int = TIMELINE_WINDOW_DAYS) -> List[Dict]:
    """
    Group timeline events that are close together in time.
    """
    if not timeline_events:
        return []

    # Convert to list of tuples (date, event) for easier processing
    events_with_dates = [(e["date"], e) for e in timeline_events if e["date"]]
    if not events_with_dates:
        return []

    print(f"Grouping {len(events_with_dates)} timeline events with window of {window_days} days")  # Debugging line

    grouped = []
    current_group = [events_with_dates[0][1]]

    for i in range(1, len(events_with_dates)):
        prev_date = current_group[-1]["date"]
        curr_date = events_with_dates[i][1]["date"]

        if prev_date and curr_date:
            delta = abs((curr_date - prev_date).days)
            if delta <= window_days:
                current_group.append(events_with_dates[i][1])
                continue

        # Finalize current group
        grouped.append({
            "start_date": current_group[0]["date"],
            "end_date": current_group[-1]["date"],
            "events": current_group.copy()
        })
        current_group = [events_with_dates[i][1]]

    # Add the last group
    if current_group:
        grouped.append({
            "start_date": current_group[0]["date"],
            "end_date": current_group[-1]["date"],
            "events": current_group.copy()
        })

    print(f"Grouped into {len(grouped)} event groups")  # Debugging line
    return grouped

def search_and_build_timeline(session, query: str, top_k: int = TOP_K) -> Dict[str, Any]:
    """
    Main function to search files by embeddings and build a timeline of related OParl events.

    Args:
        session: SQLAlchemy session
        query: User search query
        top_k: Number of top results to return

    Returns:
        Dictionary containing search results and timeline
    """
    # Generate embedding for the query
    query_embedding = call_embedding_model(query, EMBEDDING_API_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL)
    print(f"Generated embedding for query: {query_embedding[:5]}...")  # Debugging line


    # find similarities and get top-k files
    file_scores = query_vector_similarity(session, query_embedding, top_k)
    print(f"Top files (before thresholding): {file_scores}")  # Debugging line
    if not file_scores:
        return {"query": query, "results": [], "timeline": [], "message": "No files with embeddings found"}

    # filter by threshold
    top_scores = filter_by_threshold(file_scores, threshold = .4)
    print(f"Top files (after thresholding): {top_scores}")  # Debugging line
    if not top_scores:
        return {"query": query, "results": [], "timeline": [], "message": "No files above similarity threshold"}

    # Get Keys of top files
    top_file_keys = [f[0] for f in top_scores]
    print(f"Top file Keys: {top_file_keys}")  # Debugging line

    # first, we need to get the sid for each file key, since the associations are based on sids, not keys
    engine = session.get_bind()
    metadata = MetaData()
    file_tbl = Table('File', metadata, autoload_with=engine)
    stmt = select(file_tbl.c.sid, file_tbl.c.oparlKey, file_tbl.c.name, file_tbl.c.filename,
                  file_tbl.c.oparlId, file_tbl.c.downloadurl, file_tbl.c.date).where(file_tbl.c.oparlKey.in_(top_file_keys))
    with engine.connect() as conn:
        result = conn.execute(stmt).fetchall()
    top_files = [{
        "sid": row.sid,
        "oparlKey": row.oparlKey,
        "name": row.name,
        "fileName": row.filename,
        "downloadurl": row.downloadurl,
        "oparlId": row.oparlId,
        "date": row.date,
        "distance": next((score for key, score in top_scores if key == row.oparlKey), None)
    } for row in result]    
    print(f"Top files details: {top_files}")  # Debugging line
    
    file_sids = {item["oparlKey"]: item["sid"] for item in top_files}
    print(f"Resolved file keys to sids: {file_sids}")  # Debugging line

    
    # Find all related OParl objects
    related_objects = find_related_objects(session, file_sids)
    print(f"Related objects found: { {k: len(v) for k, v in related_objects.items()} }")  # Debugging line

    # Build timeline from all related objects
    timeline_events = build_timeline(related_objects)
    print(f"Timeline events built: {len(timeline_events)}")  # Debugging line

    # Group timeline events
    grouped_timeline = group_timeline_events(timeline_events)
    print(f"Grouped timeline events: {len(grouped_timeline)}")  # Debugging line
    #print(f"Timeline groups: {[{'start_date': g['start_date'], 'end_date': g['end_date'], 'event_count': len(g['events'])} for g in grouped_timeline]}")  # Debugging line
    #print(grouped_timeline)

    return {
        "query": query,
        "top_files": [{
            "sid": f["sid"],
            "oparlKey": f["oparlKey"],
            "name": f["name"],
            "fileName": f["fileName"],
            "downloadurl": f["downloadurl"],
            "oparlId": f["oparlId"],
            "date": f["date"],
            "distance": f["distance"]
        } for f in top_files],
        "timeline": grouped_timeline,
        "stats": {
            "total_files": len(top_files),
            "total_events": len(timeline_events),
            "event_types": {k: len(v) for k, v in related_objects.items() if v}
        }
    }

def main(directory: str) -> None:
    """Main entry point for the script."""
    global EMBEDDING_API_KEY, EMBEDDING_API_URL, EMBEDDING_MODEL
    EMBEDDING_API_KEY = pr.EMB_KEY
    EMBEDDING_API_URL = pr.EMB_URL
    EMBEDDING_MODEL = pr.EMB_MDL

    db_url = f"postgresql+psycopg2://{pr.RO_USER}:{pr.RO_PWD}@localhost/{pr.DB_NAME}"

    # Create database session
    session = get_db_session(db_url)

    try:
        while True:
            query = input("\nEnter your search query (or 'exit' to quit): ").strip()
            if query.lower() in ('exit', 'quit'):
                break

            if not query:
                print("Please enter a valid query.")
                continue

            try:
                results = search_and_build_timeline(session, query)

                # Print results
                print(f"\nQuery: {results['query']}")
                print(f"Found {len(results['top_files'])} matching files")

                if results['top_files']:
                    print("\nTop Files:")
                    for i, file in enumerate(results['top_files'][:5], 1):
                        print(f"{i}. {file['name']} ({file['fileName']})")
                        print(f"   Distance: {file['distance']:.3f}")
                        print(f"   OParl ID: {file['oparlId']}")
                        print(f"   Download URL: {file['downloadurl']}")
                        print(f"   Date: {file['date']}")

                if results['timeline']:
                    print("\nTimeline of Related Events:")
                    for i, group in enumerate(results['timeline'], 1):
                        print(f"\nGroup {i}: {group['start_date']} to {group['end_date']}")
                        for event in group['events']:
                            print(f"  - {event['date']}: [{event['type']}] {event['name']} {event['oparlId']}")

                # Save results to file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = os.path.join(directory, f"search_results_{timestamp}.json")
                with open(save_path, 'w') as f:
                    json.dump(results, f, default=str, indent=2, ensure_ascii=False)
                print(f"\nDetailed results saved to {save_path}")

            except Exception as e:
                print(f"Error processing query: {str(e)}")

    finally:
        session.close()

if __name__ == "__main__":
    from sklearn.metrics.pairwise import cosine_similarity
    import sys
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main(os.getcwd())
