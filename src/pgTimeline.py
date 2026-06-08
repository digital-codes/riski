import os
import json
import requests
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np
from sqlalchemy import create_engine, MetaData, Table, select, and_, or_, func
from sqlalchemy.orm import sessionmaker

# Configuration
EMBEDDING_API_URL = "https://openai.inference.de-txl.ionos.com/v1/embeddings"
EMBEDDING_MODEL = "BAAI/bge-m3"
TOP_K = 10
TIMELINE_WINDOW_DAYS = 30

API_KEY = None

# Global metadata object for table reflections
metadata = MetaData()



def get_embedding(text: str) -> np.ndarray:
    """Generate embedding using the OpenAI-compatible API."""
    headers = {"Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}"}
    payload = {
        "model": EMBEDDING_MODEL,
        "input": text
    }

    response = requests.post(EMBEDDING_API_URL, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()

    # Extract embedding from response (assuming first item in data)
    # print(f"Embedding API response: {data}")  # Debugging line
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
        embedding = data["data"][0].get("embedding")
        if embedding is not None:
            return np.array(embedding)
        else:
            raise ValueError("Embedding field is missing in API response")
    elif isinstance(data, list) and len(data) > 0 and "embedding" in data[0]:
        return np.array(data[0]["embedding"])
    else:
        raise ValueError("No embedding returned from API")

def get_db_session(db_url: str):
    """Create and return a new database session."""
    engine = create_engine(db_url, future=True)
    Session = sessionmaker(bind=engine)
    return Session()

def get_files_with_embeddings(session) -> List[Dict]:
    """
    Get all files that have contentEmbeddings, with their embedding vectors.
    """
    print("Fetching files with embeddings from the database...")  # Debugging line  
    result = session.execute(
        select(
            Table('File', metadata).c.sid,
            Table('File', metadata).c.id,
            Table('File', metadata).c.oparlKey,
            Table('File', metadata).c.oparlId,
            Table('File', metadata).c.name,
            Table('File', metadata).c.date,
            Table('File', metadata).c.fileName,
            Table('contentEmbeddings', metadata).c.value
        )
        .join(
            Table('contentEmbeddings', metadata),
            Table('File', metadata).c.sid == Table('contentEmbeddings', metadata).c.id
        )
    ).fetchall()
    
    print(f"Fetched {len(result)} files with embeddings")  # Debugging line
    
    return [{
        "sid": row.sid,
        "id": row.id,
        "oparlKey": row.oparlKey,
        "oparlId": row.oparlId,
        "name": row.name,
        "date": row.date,
        "fileName": row.fileName,
        "embedding": row.value
    } for row in result]

def find_related_objects(session, file_sids: List[int]) -> Dict[str, List[Dict]]:
    """
    Find all OParl objects related to the given file SIDs through junction tables.

    Args:
        session: SQLAlchemy session
        file_sids: List of File SIDs to find related objects for

    Returns:
        Dictionary with object types as keys and lists of related objects as values
    """
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

    # 1. Find AgendaItems connected to Files via AgendaItem__auxiliaryFile__File
    agenda_items = session.execute(
        select(
            Table('AgendaItem', metadata).c.sid,
            Table('AgendaItem', metadata).c.id,
            Table('AgendaItem', metadata).c.oparlKey,
            Table('AgendaItem', metadata).c.oparlId,
            Table('AgendaItem', metadata).c.name,
            Table('AgendaItem', metadata).c.start_date,
            Table('AgendaItem', metadata).c.end_date,
            Table('AgendaItem', metadata).c.meetingSid,
            Table('AgendaItem', metadata).c.number,
            Table('AgendaItem', metadata).c.result
        )
        .join(
            Table('AgendaItem__auxiliaryFile__File', metadata),
            Table('AgendaItem', metadata).c.sid == Table('AgendaItem__auxiliaryFile__File', metadata).c.srcSid
        )
        .where(Table('AgendaItem__auxiliaryFile__File', metadata).c.tgtSid.in_(file_sids))
    ).fetchall()

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

    # 2. Find Papers connected to Files via Paper__auxiliaryFile__File
    papers = session.execute(
        select(
            Table('Paper', metadata).c.sid,
            Table('Paper', metadata).c.id,
            Table('Paper', metadata).c.oparlKey,
            Table('Paper', metadata).c.oparlId,
            Table('Paper', metadata).c.name,
            Table('Paper', metadata).c.date,
            Table('Paper', metadata).c.reference,
            Table('Paper', metadata).c.paperType,
            Table('Paper', metadata).c.bodySid
        )
        .join(
            Table('Paper__auxiliaryFile__File', metadata),
            Table('Paper', metadata).c.sid == Table('Paper__auxiliaryFile__File', metadata).c.srcSid
        )
        .where(Table('Paper__auxiliaryFile__File', metadata).c.tgtSid.in_(file_sids))
    ).fetchall()

    for row in papers:
        related_objects["Paper"].append({
            "sid": row.sid,
            "id": row.id,
            "oparlKey": row.oparlKey,
            "oparlId": row.oparlId,
            "name": row.name,
            "date": row.date,
            "reference": row.reference,
            "paperType": row.paperType,
            "bodySid": row.bodySid
        })

    # 3. Find Meetings connected to Files via Meeting__auxiliaryFile__File
    meetings = session.execute(
        select(
            Table('Meeting', metadata).c.sid,
            Table('Meeting', metadata).c.id,
            Table('Meeting', metadata).c.oparlKey,
            Table('Meeting', metadata).c.oparlId,
            Table('Meeting', metadata).c.name,
            Table('Meeting', metadata).c.start_date,
            Table('Meeting', metadata).c.end_date
        )
        .join(
            Table('Meeting__auxiliaryFile__File', metadata),
            Table('Meeting', metadata).c.sid == Table('Meeting__auxiliaryFile__File', metadata).c.srcSid
        )
        .where(Table('Meeting__auxiliaryFile__File', metadata).c.tgtSid.in_(file_sids))
    ).fetchall()

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
        consultations = session.execute(
            select(
                Table('Consultation', metadata).c.sid,
                Table('Consultation', metadata).c.id,
                Table('Consultation', metadata).c.oparlKey,
                Table('Consultation', metadata).c.oparlId,
                Table('Consultation', metadata).c.role,
                Table('Consultation', metadata).c.authoritative,
                Table('Consultation', metadata).c.agendaItemSid,
                Table('Consultation', metadata).c.meetingSid,
                Table('Consultation', metadata).c.paperSid
            )
            .join(
                Table('Paper__consultation__Consultation', metadata),
                Table('Paper__consultation__Consultation', metadata).c.srcSid == Table('Consultation', metadata).c.sid
            )
            .where(Table('Paper__consultation__Consultation', metadata).c.srcSid.in_(paper_sids))
        ).fetchall()

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

    # 5. For Meetings, find related AgendaItems
    meeting_sids = [m["sid"] for m in related_objects["Meeting"]]
    if meeting_sids:
        meeting_agenda_items = session.execute(
            select(
                Table('AgendaItem', metadata).c.sid,
                Table('AgendaItem', metadata).c.id,
                Table('AgendaItem', metadata).c.oparlKey,
                Table('AgendaItem', metadata).c.oparlId,
                Table('AgendaItem', metadata).c.name,
                Table('AgendaItem', metadata).c.start_date,
                Table('AgendaItem', metadata).c.end_date,
                Table('AgendaItem', metadata).c.meetingSid,
                Table('AgendaItem', metadata).c.number,
                Table('AgendaItem', metadata).c.result
            )
            .join(
                Table('Meeting__agendaItem__AgendaItem', metadata),
                Table('Meeting__agendaItem__AgendaItem', metadata).c.tgtSid == Table('AgendaItem', metadata).c.sid
            )
            .where(Table('Meeting__agendaItem__AgendaItem', metadata).c.srcSid.in_(meeting_sids))
        ).fetchall()

        for row in meeting_agenda_items:
            # Avoid duplicates
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

    # 6. For AgendaItems, find related Consultations
    agenda_item_sids = [ai["sid"] for ai in related_objects["AgendaItem"]]
    if agenda_item_sids:
        agenda_consultations = session.execute(
            select(
                Table('Consultation', metadata).c.sid,
                Table('Consultation', metadata).c.id,
                Table('Consultation', metadata).c.oparlKey,
                Table('Consultation', metadata).c.oparlId,
                Table('Consultation', metadata).c.role,
                Table('Consultation', metadata).c.authoritative,
                Table('Consultation', metadata).c.agendaItemSid,
                Table('Consultation', metadata).c.meetingSid,
                Table('Consultation', metadata).c.paperSid
            )
            .where(Table('Consultation', metadata).c.agendaItemSid.in_(agenda_item_sids))
        ).fetchall()

        for row in agenda_consultations:
            # Avoid duplicates
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
        consultation_orgs = session.execute(
            select(
                Table('Organization', metadata).c.sid,
                Table('Organization', metadata).c.id,
                Table('Organization', metadata).c.oparlKey,
                Table('Organization', metadata).c.oparlId,
                Table('Organization', metadata).c.name,
                Table('Organization', metadata).c.classification,
                Table('Organization', metadata).c.shortName
            )
            .join(
                Table('Consultation__organization__Organization', metadata),
                Table('Consultation__organization__Organization', metadata).c.tgtSid == Table('Organization', metadata).c.sid
            )
            .where(Table('Consultation__organization__Organization', metadata).c.srcSid.in_(consultation_sids))
        ).fetchall()

        for row in consultation_orgs:
            related_objects["Organization"].append({
                "sid": row.sid,
                "id": row.id,
                "oparlKey": row.oparlKey,
                "oparlId": row.oparlId,
                "name": row.name,
                "classification": row.classification,
                "shortName": row.shortName
            })

    # 8. For Papers, find related Organizations (underDirectionOf)
    if paper_sids:
        paper_orgs = session.execute(
            select(
                Table('Organization', metadata).c.sid,
                Table('Organization', metadata).c.id,
                Table('Organization', metadata).c.oparlKey,
                Table('Organization', metadata).c.oparlId,
                Table('Organization', metadata).c.name,
                Table('Organization', metadata).c.classification,
                Table('Organization', metadata).c.shortName
            )
            .join(
                Table('Paper__underDirectionOf__Organization', metadata),
                Table('Paper__underDirectionOf__Organization', metadata).c.tgtSid == Table('Organization', metadata).c.sid
            )
            .where(Table('Paper__underDirectionOf__Organization', metadata).c.srcSid.in_(paper_sids))
        ).fetchall()

        for row in paper_orgs:
            # Avoid duplicates
            if not any(o["sid"] == row.sid for o in related_objects["Organization"]):
                related_objects["Organization"].append({
                    "sid": row.sid,
                    "id": row.id,
                    "oparlKey": row.oparlKey,
                    "oparlId": row.oparlId,
                    "name": row.name,
                    "classification": row.classification,
                    "shortName": row.shortName
                })

    return related_objects

def build_timeline(related_objects: Dict[str, List[Dict]]) -> List[Dict]:
    """
    Build a timeline from related OParl objects, sorted by date.
    """
    timeline_events = []

    for obj_type, objects in related_objects.items():
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
    query_embedding = get_embedding(query)
    print(f"Generated embedding for query: {query_embedding[:5]}...")  # Debugging line

    # Get all files with their embeddings
    files_with_embeddings = get_files_with_embeddings(session)
    print(f"Total files with embeddings: {len(files_with_embeddings)}")  # Debugging line
    if not files_with_embeddings:
        return {"query": query, "results": [], "timeline": [], "message": "No files with embeddings found"}

    # Calculate cosine similarities
    file_embeddings = np.array([f["embedding"] for f in files_with_embeddings])
    query_embedding_array = query_embedding.reshape(1, -1)
    similarities = cosine_similarity(query_embedding_array, file_embeddings)[0]

    # Add similarity scores to files
    for i, file in enumerate(files_with_embeddings):
        file["similarity"] = float(similarities[i])

    # Sort by similarity and get top-k
    files_with_embeddings.sort(key=lambda x: x["similarity"], reverse=True)
    top_files = files_with_embeddings[:top_k]

    # Get SIDs of top files
    top_file_sids = [f["sid"] for f in top_files]

    # Find all related OParl objects
    related_objects = find_related_objects(session, top_file_sids)

    # Build timeline from all related objects
    timeline_events = build_timeline(related_objects)

    # Group timeline events
    grouped_timeline = group_timeline_events(timeline_events)

    return {
        "query": query,
        "top_files": [{
            "sid": f["sid"],
            "id": f["id"],
            "name": f["name"],
            "fileName": f["fileName"],
            "oparlId": f["oparlId"],
            "date": f["date"],
            "similarity": f["similarity"]
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
    global API_KEY, EMBEDDING_API_URL, EMBEDDING_MODEL
    import private as pr
    API_KEY = pr.EMB_KEY
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
                        print(f"   Similarity: {file['similarity']:.3f}")
                        print(f"   OParl ID: {file['oparlId']}")
                        print(f"   Date: {file['date']}")

                if results['timeline']:
                    print("\nTimeline of Related Events:")
                    for i, group in enumerate(results['timeline'], 1):
                        print(f"\nGroup {i}: {group['start_date']} to {group['end_date']}")
                        for event in group['events']:
                            print(f"  - {event['date']}: [{event['type']}] {event['name']}")

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
