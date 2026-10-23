
# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.<name>``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass
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

import time

# ----------------------------------------------------------------------
# Shared layers: DB (read-only engine + config) and remote model client
# ----------------------------------------------------------------------
from src.db import get_engine, _load_private
from src import remote


# Configuration
EMBEDDING_API_URL = None
EMBEDDING_MODEL = None
EMBEDDING_API_KEY = None
TOP_K = 100
TIMELINE_WINDOW_DAYS = 30


def _get_setting(attr: str, env_key: str):
    """Resolve a setting from private.py, then environment variables."""
    pr = _load_private()
    if pr is not None:
        value = getattr(pr, attr, None)
        if value:
            return value
    return os.getenv(env_key) or None


# test reranking with a small local model
try:
    RERANKING_API_URL = _get_setting("RERANK_URL", "RERANK_URL")
    RERANKING_MODEL = _get_setting("RERANK_MDL", "RERANK_MDL")
    RERANKING_API_KEY = _get_setting("RERANK_KEY", "RERANK_KEY")
    if RERANKING_API_URL is None:
        raise AttributeError("no reranking configuration")
    if "rerank" in RERANKING_API_URL.lower():
        RERANK_MODE = "rerank"
    else:
        RERANK_MODE = "chat"
except AttributeError:
    RERANKING_API_URL = None
    RERANKING_MODEL = None
    RERANKING_API_KEY = None
    RERANK_MODE = None

# summary model configuration is handled by src.remote (SUMMARY_*/CHAT_*)
SUMMARY_API_URL = remote.CHAT_BASE_URL
SUMMARY_MODEL = remote.CHAT_MODEL
SUMMARY_API_KEY = remote.CHAT_API_KEY

def call_reranking_chat_model(query: str, content: str) -> float:
    """
    Call local reranking model and return relevance score
    Adjust based on your actual API endpoint
    """
    if RERANKING_API_URL == None:
        print("Reranking API URL not configured, skipping reranking")
        return 1.0  # If no reranking API is configured, return a default relevance score of 1.0 (keep all results)
    lang = "German"  # Assuming the content and query are in German
    headers = {"Authorization": f"Bearer {RERANKING_API_KEY}"} if RERANKING_API_KEY else {}
    rerank_prompt = f"You are a helpful assistant that scores the relevance of a {lang} text to a user's query in {lang}. Return a score between 0 and 1, where 1 means highly relevant and 0 means not relevant at all. Be strict and focus on meaning, not on word similarity."
    #rerank_query = f"Query: {query}\n\nFile content: {content}\n\nBased on the {lang} query and content, how relevant is this {lang} content to the query? Return only a single number between 0 and 1. Do not return any text other than the number."
    rerank_query = f"Query: {query}\n\nContent: {content}\n\nReturn only a single number between 0 and 1. Do not return any text other than the number."
    print(f"Calling reranking model with query: {query} and content length: {len(content)}")  # Debugging line
    response = requests.post(
        RERANKING_API_URL,
        json={"model": RERANKING_MODEL,  "temperature": 0.1, "random_seed": 42, "messages": [{"role": "system", "content": rerank_prompt}, {"role": "user", "content": rerank_query}]},
        headers=headers
    )
    # handle 429 too many requests error by retrying after a delay. get delay from response headers if available, otherwise default to 5 seconds
    if response.status_code == 429:
        for attempt in range(5):  # Retry up to 5 times
            retry_after = int(response.headers.get("Retry-After", 5))
            print(f"Reranking model rate limit exceeded. Retrying after {retry_after} seconds...")
            time.sleep(retry_after)
            response = requests.post(
                RERANKING_API_URL,
                json={"model": RERANKING_MODEL,  "temperature": 0.1, "random_seed": 42, "messages": [{"role": "system", "content": rerank_prompt}, {"role": "user", "content": rerank_query}]},
                headers=headers
            )
            if response.status_code != 429:
                break
    response.raise_for_status()
    result = response.json()
    # Adjust based on actual API response structure
    if isinstance(result, dict) and result.get("choices") and isinstance(result["choices"], list) and len(result["choices"]) > 0:
        score_str = result["choices"][0].get('message', {}).get('content', '0')
        try:
            score = float(score_str.strip())
            return score
        except ValueError:
            print(f"Could not parse relevance score from model response: '{score_str}'")
            return 0.0
    else:
        print(f"Unexpected response format from reranking model: {result}")
        return 0.0 

def call_reranking_model(query: str, content: list[str], top_n=0) -> list[float]:
    """
    Call local reranking model and return relevance score
    Adjust based on your actual API endpoint
    """
    if RERANKING_API_URL == None:
        print("Reranking API URL not configured, skipping reranking")
        return [1.0 for x in content]  # If no reranking API is configured, return a default relevance score of 1.0 (keep all results)
    headers = {"Authorization": f"Bearer {RERANKING_API_KEY}"} if RERANKING_API_KEY else {}
    # adjust top_n if zero
    top_n = top_n if top_n > 0 else len(content)
    # with reranker we don't need a prompt, just the query and the content
    params = {"model": RERANKING_MODEL,  "random_seed": 42, 
                      "top_n": top_n, "query": query, "documents": content, 
                      "return_embeddings": False, "return_documents": False,
                      "max_doc_length": 4096}
    #print(f"Reranking model params: {params}")  # Debugging line
    response = requests.post(
        RERANKING_API_URL,
        json=params,
        headers=headers
    )
    # handle 429 too many requests error by retrying after a delay. get delay from response headers if available, otherwise default to 5 seconds
    if response.status_code == 429:
        for attempt in range(5):  # Retry up to 5 times
            retry_after = int(response.headers.get("Retry-After", 5))
            print(f"Reranking model rate limit exceeded. Retrying after {retry_after} seconds...")
            time.sleep(retry_after)
            response = requests.post(
                RERANKING_API_URL,
                json=params,
                headers=headers
            )
            if response.status_code != 429:
                break
    response.raise_for_status()
    result = response.json()
    # Adjust based on actual API response structure
    # llamacpp repsonse is like this:{
    #     "model": "jina-reranker-v3.5-Q4_K_M",
    #     "object": "list",
    #     "results": [
    #         {
    #             "index": 0,
    #             "relevance_score": 0.9999481439590454
    #         },
    #         {
    #             "index": 2,
    #             "relevance_score": 4.775548950419761e-05
    #         }
    #     ],
    #     "usage": {
    #         "prompt_tokens": 196,
    #         "total_tokens": 196
    #     }
    # }
    if isinstance(result, dict) and result.get("results") and isinstance(result["results"], list) and len(result["results"]) > 0:
        scores = []
        # results are ordered by best relevance first, with index indicating the original index of the document in the input list
        # we need to reorder the scores to match the original order of the content list
        for item in result["results"]:
            print(f"Reranking model item: {item}")  # Debugging line
            try:
                index = item.get("index")
                score = 1.0 if item.get("relevance_score") is None else float(item.get("relevance_score", 1.0))
                scores.append((index, score))
            except ValueError:
                print(f"Could not parse relevance score from model response: '{item}'")
                scores.append((index, 1.0))
            print(f"Reranking model item: index={index}, score={score}")  # Debugging line
        # reorder scores to match the original order of the content list
        scores.sort(key=lambda x: x[0])
        return [score for index, score in scores]
    else:
        print(f"Unexpected response format from reranking model: {result}")
        return [1.0 for x in content]  # Return a list of default relevance scores if response format is unexpected


######### 


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



def call_embedding_model(text: str, api_url: str = None, api_key: str = None, model: str = None) -> tuple[list[float], float]:
    """
    Call the shared remote embedding client and return a normalised vector.

    The endpoint/model/key configuration lives in ``src.remote`` (resolved
    from ``private.py`` / environment variables); the arguments are kept for
    API compatibility and override the shared configuration when given.
    """
    if model:
        vec = remote.embed(text, model=model)
    else:
        vec = remote.embed(text)
    vector = vec.tolist()
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



def get_db_session(db_url: str = None):
    """Create and return a new database session on the shared read-only engine."""
    if db_url is None:
        engine = get_engine(readonly=True)
    else:
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
    file_tbl = Table('File', metadata, autoload_with=engine)
    
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
        "Location": [],
        "AuxFile": []  
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

    # 2.b when a paper is identified, we also want to get all associated files via pf_assoc_tbl, since the paper may have multiple files, and we want to include them in the timeline
    paper_sids = [p["sid"] for p in related_objects["Paper"]]
    if paper_sids:
        stmt = (
            select(
                file_tbl.c.sid,
                file_tbl.c.oparlKey,
                file_tbl.c.name,
                file_tbl.c.filename,
                file_tbl.c.oparlId,
                file_tbl.c.downloadurl,
                file_tbl.c.date
            )
            .select_from(
                pf_assoc_tbl.join(
                    file_tbl, pf_assoc_tbl.c.tgtSid == file_tbl.c.sid
                )
            )
            .where(pf_assoc_tbl.c.srcSid.in_(paper_sids))
        )
        with engine.connect() as conn:
            paper_files = conn.execute(stmt).fetchall()
        
        for row in paper_files:
            if not any(f["sid"] == row.sid for f in related_objects["AuxFile"]):
                related_objects["AuxFile"].append({
                    "sid": row.sid,
                    "oparlKey": row.oparlKey,
                    "name": row.name,
                    "fileName": row.filename,
                    "oparlId": row.oparlId,
                    "downloadurl": row.downloadurl,
                    "date": row.date
                })
        print(f"Found {len(related_objects['AuxFile'])} additional files related to papers")  # Debugging line
    
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
            elif obj_type == "AuxFile":
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

def search_and_build_timeline(
    session,
    query: str,
    top_k: int = TOP_K,
    threshold: float = 0.40,
    hybrid: bool = True,
    filters: Optional[List[Dict[str, Any]]] = None,
    signals: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """
    Main function to search files by embeddings and build a timeline of related OParl events.

    Args:
        session: SQLAlchemy session
        query: User search query
        top_k: Number of top results to return
        threshold: Similarity threshold for filtering results (legacy vector-only path)
        hybrid: Use hybrid multi-signal recall (lexical + name vectors + content
            vectors, RRF-fused). With False, falls back to the legacy
            content-vector-only path with distance thresholding.
        filters: Structured facet filters (see pgHybridSearch.parse_filters)
        signals: Per-signal toggles {"lexical": bool, "name_vectors": bool,
            "content_vectors": bool}; all default to True.

    Returns:
        Dictionary containing search results and timeline
    """
    # Generate embedding for the query
    query_embedding = call_embedding_model(query, EMBEDDING_API_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL)
    print(f"Generated embedding for query: {query_embedding[:5]}...")  # Debugging line

    hybrid_distances: Dict[str, Optional[float]] = {}
    matched_entities: List[Dict[str, Any]] = []
    facets_data: Dict[str, Any] = {}
    applied_filters: List[Dict[str, Any]] = []

    if hybrid:
        from src.pgHybridSearch import facets as facet_listing
        from src.pgHybridSearch import hybrid_candidates, parse_filters

        conn = session.connection()
        applied_filters = parse_filters(filters)
        hyb = hybrid_candidates(
            conn, query, query_embedding, top_k, filters=filters, signals=signals
        )
        matched_entities = hyb["matched_entities"]
        candidates = hyb["file_candidates"]  # [(oparlKey, fused_score, content_distance)]
        facets_data = facet_listing(conn)
        hybrid_distances = {k: d for k, _s, d in candidates}
        print(f"Hybrid recall: {len(matched_entities)} entities, {len(candidates)} file candidates")
        if not candidates:
            return {
                "query": query,
                "top_files": [],
                "results": [],
                "timeline": [],
                "matched_entities": [],
                "facets": facets_data,
                "applied_filters": applied_filters,
                "message": "No candidates found for the given query/filters",
            }
        # Fused score feeds the reranker stage; distances are kept for output.
        top_scores = [(key, fused) for key, fused, _dist in candidates]
    else:
        # legacy vector-only path
        # find similarities and get top-k files
        file_scores = query_vector_similarity(session, query_embedding, top_k)
        print(f"Inital Top files: {file_scores}")  # Debugging line

        print(f"Top files (before thresholding): {file_scores}")  # Debugging line
        if not file_scores:
            return {"query": query, "results": [], "timeline": [], "matched_entities": [], "facets": {}, "applied_filters": [], "message": "No files with embeddings found"}

        # filter by threshold
        top_scores = filter_by_threshold(file_scores, threshold=threshold)
        print(f"Top files (after thresholding {threshold}): {top_scores}")  # Debugging line
        if not top_scores:
            return {"query": query, "top_files": [], "results": [], "timeline": [], "matched_entities": [], "facets": {}, "applied_filters": [], "message": "No files above similarity threshold"}

    # run reranking on all files and append rerank score to file_score 
    top_scores_with_rerank = []
    print(f"Running reranking on top {len(top_scores)} files")  # Debugging line

    if RERANK_MODE == "chat":
        for oparlKey, score in top_scores:
            print(f"Processing file {oparlKey} with initial score {score:.4f}")  # Debugging line
            # get file content for reranking
            file_content = session.query(File.content).filter(File.oparlKey == oparlKey).first()
            if file_content and file_content[0]:  # Check if content exists and is not None
                rerank_score = call_reranking_chat_model(query, file_content[0])
                print(f"Reranking score for file {oparlKey}: {rerank_score:.4f}")  # Debugging line
                if rerank_score is not None and isinstance(rerank_score, (int, float)) and rerank_score >= .8:
                    top_scores_with_rerank.append((oparlKey, score))
                    print(f"Accept reranked file {oparlKey}: original score {score:.4f}, rerank score {rerank_score:.4f}")  # Debugging line
                else:
                    print(f"Reject reranked file {oparlKey}: original score {score:.4f}, rerank score {rerank_score:.4f}")  # Debugging line
            else:
                print(f"No content found for file {oparlKey}, skipping reranking")  # Debugging line
                top_scores_with_rerank.append((oparlKey, score))  # No content, keep original score
                print(f"No content for file {oparlKey}, keeping original score {score:.4f}")  # Debugging line

        # update top_scores_with_rerank with rerank scores
        # top_scores_with_rerank = [(top_scores[i][0], rerank_scores[i]) for i in range(len(top_scores))]
    else:
        # we call the real reranker with the full list of documents and the query, and it will return a list of scores for each document
        documents = []
        for oparlKey, score in top_scores:
            file_content = session.query(File.content).filter(File.oparlKey == oparlKey).first()
            if file_content and file_content[0]:  # Check if content exists and is not None
                documents.append(file_content[0])
            else:
                print(f"No content found for file {oparlKey}, skipping reranking")  # Debugging line
                documents.append("")  # Append empty string to maintain order
        rerank_scores = call_reranking_model(query, documents, top_n=len(documents))
        print(f"Reranking scores: {rerank_scores}")  # Debugging line
        for i, rscore in enumerate(rerank_scores):
            oparlKey, score = top_scores[i]
            if rscore is None or not isinstance(rscore, (int, float)):
                print(f"Invalid rerank score received: {rscore}, keep old score")  # Debugging line
                top_scores_with_rerank.append((oparlKey, score))  # No content, keep original score
            elif rscore >= .8:
                top_scores_with_rerank.append((oparlKey, score * rscore))
                print(f"Accept reranked file {oparlKey}: original score {score:.4f}, rerank score {rscore:.4f}")  # Debugging line
            else:
                print(f"Reject reranked file {oparlKey}: original score {score:.4f}, rerank score {rscore:.4f}")  # Debugging line
                # reject reranked file. don't append
        

    print(f"Top files after reranking: {top_scores_with_rerank}")  # Debugging line

    # Get Keys of top files
    top_file_keys = [f[0] for f in top_scores_with_rerank]
    print(f"Top file Keys: {top_file_keys}")
    # keep the rerank/fusion ordering in the output (DB returns arbitrary order)
    key_rank = {k: i for i, k in enumerate(top_file_keys)}  # Debugging line

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
        # hybrid mode: content-vector cosine distance where the file came
        # from that signal, else the fused score (None-safe for JSON)
        "distance": hybrid_distances.get(row.oparlKey)
                    if hybrid else
                    next((score for key, score in top_scores_with_rerank if key == row.oparlKey), None)
    } for row in result]
    top_files.sort(key=lambda f: key_rank.get(f["oparlKey"], len(key_rank)))
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
        "matched_entities": matched_entities,
        "facets": facets_data,
        "applied_filters": applied_filters,
        "stats": {
            "total_files": len(top_files),
            "total_events": len(timeline_events),
            "event_types": {k: len(v) for k, v in related_objects.items() if v}
        }
    }

def main(directory: str, threshold: float = .40, top_k: int = TOP_K, filters: Optional[str] = None) -> None:
    """Main entry point for the script."""
    global EMBEDDING_API_KEY, EMBEDDING_API_URL, EMBEDDING_MODEL
    # Embedding configuration comes from src.remote (private.py / env)
    EMBEDDING_API_KEY = remote.EMBED_API_KEY
    EMBEDDING_API_URL = remote.EMBED_BASE_URL
    EMBEDDING_MODEL = remote.EMBED_MODEL

    # Create database session on the shared read-only engine
    session = get_db_session()

    try:
        while True:
            query = input("\nEnter your search query (or 'exit' to quit): ").strip()
            if query.lower() in ('exit', 'quit'):
                break

            if not query:
                print("Please enter a valid query.")
                continue

            try:
                parsed_filters = json.loads(filters) if filters else None
                results = search_and_build_timeline(session, query, top_k=top_k, threshold=threshold, filters=parsed_filters)

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

                    # generate a summary of the top files if summary model configured
                    if SUMMARY_API_URL and SUMMARY_MODEL:
                        summary = "\nSummary of Top Files:\n"
                        # get the content of the top files via their oparlKey.
                        for i, file in enumerate(results['top_files'][:5], 1):
                            file_content = session.query(File.content).filter(File.oparlKey == file['oparlKey']).first()
                            if file_content and file_content[0]:
                                summary += f"\nFile {i}: {file['name']} ({file['fileName']})\n"
                                summary += f"Content: {file_content[0][:5000]}...\n"  # Show first 5000 chars
                            else:
                                summary += f"\nFile {i}: {file['name']} ({file['fileName']})\n"
                                summary += "Content: Not available\n"
                        # Call summary model via the shared chat client
                        summary_response = remote.chat(
                            [
                                {"role": "system", "content": "You are a helpful assistant that summarizes German text. Respond in German. stay below 500 words. no emojis."},
                                {"role": "user", "content": summary},
                            ],
                            model=SUMMARY_MODEL,
                            temperature=0.1,
                        )
                        summary_text = summary_response.get("content", "")
                        if summary_text and summary_text != "[dummy response]":
                            print(f"\nSummary of Top Files:\n{summary_text}")
                            # append summary to results for saving
                            results['summary'] = summary_text
                else:
                    print("No top files found above the similarity threshold.")

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
    import argparse
    parser = argparse.ArgumentParser(description="Search OParl files by embedding similarity and build a timeline of related events.")
    parser.add_argument("-d", "--directory", default = os.getcwd(), help="Directory to save results (default: current directory)")
    parser.add_argument("-t", "--threshold", type=float, default=0.40, help="Similarity threshold (default: 0.40)")
    parser.add_argument("-k", "--top_k", type=int, default=TOP_K, help="Number of top results to return (default: TOP_K)")
    parser.add_argument("-F", "--filters", type=str, default=None, help='Structured facet filters as JSON, e.g. \'[{"facet":"paperType","op":"in","values":["Antrag"]}]\'' )
    parser.add_argument("-F", "--filters", type=str, default=None, help='Structured facet filters as JSON, e.g. \'[{"facet":"paperType","op":"in","values":["Antrag"]}]\'' )
    args = parser.parse_args()
    main(args.directory, args.threshold, args.top_k, args.filters)
