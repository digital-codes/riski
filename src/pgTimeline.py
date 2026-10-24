
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
from src.timing import timed

log = None  # set by _ensure_log()


def _ensure_log():
    """Lazily create the module logger (debug chatter hidden by default)."""
    global log
    if log is None:
        import logging
        log = logging.getLogger("riski.timeline")
        if not log.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            log.addHandler(handler)
            log.setLevel(logging.WARNING)
    return log
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
        _ensure_log().debug("Reranking API URL not configured, skipping reranking")
        return 1.0  # If no reranking API is configured, return a default relevance score of 1.0 (keep all results)
    lang = "German"  # Assuming the content and query are in German
    headers = {"Authorization": f"Bearer {RERANKING_API_KEY}"} if RERANKING_API_KEY else {}
    rerank_prompt = f"You are a helpful assistant that scores the relevance of a {lang} text to a user's query in {lang}. Return a score between 0 and 1, where 1 means highly relevant and 0 means not relevant at all. Be strict and focus on meaning, not on word similarity."
    #rerank_query = f"Query: {query}\n\nFile content: {content}\n\nBased on the {lang} query and content, how relevant is this {lang} content to the query? Return only a single number between 0 and 1. Do not return any text other than the number."
    rerank_query = f"Query: {query}\n\nContent: {content}\n\nReturn only a single number between 0 and 1. Do not return any text other than the number."
    _ensure_log().debug(f"Calling reranking model with query: {query} and content length: {len(content)}")  # Debugging line
    response = requests.post(
        RERANKING_API_URL,
        json={"model": RERANKING_MODEL,  "temperature": 0.1, "random_seed": 42, "messages": [{"role": "system", "content": rerank_prompt}, {"role": "user", "content": rerank_query}]},
        headers=headers
    )
    # handle 429 too many requests error by retrying after a delay. get delay from response headers if available, otherwise default to 5 seconds
    if response.status_code == 429:
        for attempt in range(5):  # Retry up to 5 times
            retry_after = int(response.headers.get("Retry-After", 5))
            _ensure_log().warning(f"Reranking model rate limited; retrying after {retry_after}s")
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
            _ensure_log().debug(f"Could not parse relevance score from model response: '{score_str}'")
            return 0.0
    else:
        _ensure_log().debug(f"Unexpected response format from reranking model: {result}")
        return 0.0 

@timed
def call_reranking_model(query: str, content: list[str], top_n=0) -> list[float]:
    """
    Call local reranking model and return relevance score
    Adjust based on your actual API endpoint
    """
    if RERANKING_API_URL == None:
        _ensure_log().debug("Reranking API URL not configured, skipping reranking")
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
            _ensure_log().warning(f"Reranking model rate limited; retrying after {retry_after}s")
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
            _ensure_log().debug(f"Reranking model item: {item}")  # Debugging line
            try:
                index = item.get("index")
                score = 1.0 if item.get("relevance_score") is None else float(item.get("relevance_score", 1.0))
                scores.append((index, score))
            except ValueError:
                _ensure_log().debug(f"Could not parse relevance score from model response: '{item}'")
                scores.append((index, 1.0))
            _ensure_log().debug(f"Reranking model item: index={index}, score={score}")  # Debugging line
        # reorder scores to match the original order of the content list
        scores.sort(key=lambda x: x[0])
        return [score for index, score in scores]
    else:
        _ensure_log().debug(f"Unexpected response format from reranking model: {result}")
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



@timed(label="pgTimeline.embed_query")
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
    _ensure_log().debug(f"Received vector of length {len(vector)}")  # Debug print to check vector length
    return vector

# here, threshold is a distance threshold, so we want to keep vectors with distance <= threshold (i.e. similarity above a certain level)
def filter_by_threshold(vectors_with_scores: list[tuple], threshold: float) -> list[tuple]:
    """Filter vectors above threshold"""
    return [(vec, score) for vec, score in vectors_with_scores if score <= threshold]

@timed
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



@timed
def find_related_objects(session, file_sids: List[str]) -> Dict[str, List[Dict]]:
    """
    Find all OParl objects related to the given file sids through junction tables.

    Traverses the OParl association tables and logs every relationship it
    walks as a typed edge (add-network-view tasks 1.2/1.3). The returned
    dict carries the objects per type plus two extra keys: ``edges`` (the
    typed edge log) and ``_sid_maps`` (sid→oparlKey lookups used for FK
    edges) — both consumed by ``build_graph`` and stripped before output.

    Args:
        session: SQLAlchemy session
        file_sids: Dict mapping File oparlKey → File sid to find related objects for

    Returns:
        Dictionary with object types as keys and lists of related objects
        as values, plus "edges" and "_sid_maps".
    """
    engine = session.get_bind()
    metadata = MetaData()

    # typed edge log: {"source": "Type_key", "target": "Type_key", "relation": ..., "via": ...}
    edges: List[Dict[str, str]] = []
    # invert file_sids (oparlKey → sid) for junction-target resolution
    sid_to_file_key = {sid: key for key, sid in file_sids.items()}

    def log_edge(src_type: str, src_key, relation: str, tgt_type: str, tgt_key, via: str) -> None:
        if src_key is None or tgt_key is None:
            return
        edges.append({
            "source": f"{src_type}_{src_key}",
            "target": f"{tgt_type}_{tgt_key}",
            "relation": relation,
            "via": via,
        })

    
    
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
            agenda_tbl.c.result,
            af_assoc_tbl.c.tgtSid.label("fileSid"),
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
        log_edge("AgendaItem", row.oparlKey, "auxiliaryFile", "File",
                 sid_to_file_key.get(row.fileSid), "AgendaItem__auxiliaryFile__File")

    _ensure_log().debug(f"Found {len(related_objects['AgendaItem'])} agenda items related to files")  # Debugging line

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
            paper_tbl.c.bodySid,
            pf_assoc_tbl.c.tgtSid.label("fileSid"),
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
        log_edge("Paper", row.oparlKey, "auxiliaryFile", "File",
                 sid_to_file_key.get(row.fileSid), "Paper__auxiliaryFile__File")
    _ensure_log().debug(f"Found {len(related_objects['Paper'])} papers related to files")  # Debugging line

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
                file_tbl.c.date,
                pf_assoc_tbl.c.srcSid.label("paperSid"),
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

        paper_sid_to_key = {p["sid"]: p["oparlKey"] for p in related_objects["Paper"]}
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
            log_edge("Paper", paper_sid_to_key.get(row.paperSid), "auxiliaryFile", "AuxFile",
                     row.oparlKey, "Paper__auxiliaryFile__File")
        _ensure_log().debug(f"Found {len(related_objects['AuxFile'])} additional files related to papers")  # Debugging line
    
    # 3. Find Meetings connected to Files
    stmt = (
        select(
            meeting_tbl.c.sid,
            meeting_tbl.c.id,
            meeting_tbl.c.oparlKey,
            meeting_tbl.c.oparlId,
            meeting_tbl.c.name,
            meeting_tbl.c.start_date,
            meeting_tbl.c.end_date,
            mf_assoc_tbl.c.tgtSid.label("fileSid"),
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
        log_edge("Meeting", row.oparlKey, "auxiliaryFile", "File",
                 sid_to_file_key.get(row.fileSid), "Meeting__auxiliaryFile__File")

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

        paper_sid_to_key = {p["sid"]: p["oparlKey"] for p in related_objects["Paper"]}
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
            log_edge("Paper", paper_sid_to_key.get(row.paperSid), "consultation", "Consultation",
                     row.oparlKey, "Paper__consultation__Consultation")
    _ensure_log().debug(f"Found {len(related_objects['Consultation'])} consultations related to papers")  # Debugging line

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

        meeting_sid_to_key = {m["sid"]: m["oparlKey"] for m in related_objects["Meeting"]}
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
            log_edge("Meeting", meeting_sid_to_key.get(row.meetingSid), "agendaItem", "AgendaItem",
                     row.oparlKey, "Meeting__agendaItem__AgendaItem")
    _ensure_log().debug(f"Found {len(related_objects['AgendaItem'])} agenda items related to meetings")  # Debugging line

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

    # 6b. Fetch Meetings referenced by consultations/agenda items that were
    # not found through direct file links — without this, Meeting nodes (and
    # their calendar links) are missing from the graph whenever no seed file
    # links to the meeting directly.
    meeting_sid_to_key = {m["sid"]: m["oparlKey"] for m in related_objects["Meeting"]}
    referenced_meeting_sids = {c["meetingSid"] for c in related_objects["Consultation"] if c.get("meetingSid")}
    referenced_meeting_sids |= {a["meetingSid"] for a in related_objects["AgendaItem"] if a.get("meetingSid")}
    missing_meeting_sids = referenced_meeting_sids - set(meeting_sid_to_key)
    if missing_meeting_sids:
        stmt = (
            select(
                meeting_tbl.c.sid,
                meeting_tbl.c.id,
                meeting_tbl.c.oparlKey,
                meeting_tbl.c.oparlId,
                meeting_tbl.c.name,
                meeting_tbl.c.start_date,
                meeting_tbl.c.end_date,
            )
            .where(meeting_tbl.c.sid.in_(missing_meeting_sids))
        )
        with engine.connect() as conn:
            for row in conn.execute(stmt).fetchall():
                related_objects["Meeting"].append({
                    "sid": row.sid,
                    "id": row.id,
                    "oparlKey": row.oparlKey,
                    "oparlId": row.oparlId,
                    "name": row.name,
                    "start_date": row.start_date,
                    "end_date": row.end_date,
                })
        _ensure_log().debug(f"Fetched {len(missing_meeting_sids)} additional meetings via consultations/agenda items")

    # 7. For Consultations, find related Organizations
    consultation_sids = [c["sid"] for c in related_objects["Consultation"]]
    consultation_sid_to_key = {c["sid"]: c["oparlKey"] for c in related_objects["Consultation"]}
    if consultation_sids:
        stmt = (
            select(
                organization_tbl.c.sid,
                organization_tbl.c.id,
                organization_tbl.c.oparlKey,
                organization_tbl.c.oparlId,
                organization_tbl.c.name,
                organization_tbl.c.classification,
                organization_tbl.c.shortname,
                co_assoc_tbl.c.srcSid.label("consultSid"),
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
            log_edge("Consultation", consultation_sid_to_key.get(row.consultSid), "organization", "Organization",
                     row.oparlKey, "Consultation__organization__Organization")

    _ensure_log().debug(f"Found {len(related_objects['Organization'])} organizations related to consultations")  # Debugging line

    # 8. For Papers, find related Organizations (underDirectionOf)
    paper_sid_to_key = {p["sid"]: p["oparlKey"] for p in related_objects["Paper"]}
    if paper_sids:
        stmt = (
            select(
                organization_tbl.c.sid,
                organization_tbl.c.id,
                organization_tbl.c.oparlKey,
                organization_tbl.c.oparlId,
                organization_tbl.c.name,
                organization_tbl.c.classification,
                organization_tbl.c.shortname,
                po_assoc_tbl.c.srcSid.label("paperSid"),
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
            log_edge("Paper", paper_sid_to_key.get(row.paperSid), "underDirectionOf", "Organization",
                     row.oparlKey, "Paper__underDirectionOf__Organization")

        _ensure_log().debug(f"Found {len(related_objects['Organization'])} organizations related to papers")  # Debugging line

    # 9. Direct-FK edges derivable from collected objects (no extra queries):
    #    Consultation.meetingSid/paperSid, AgendaItem.meetingSid
    meeting_sid_to_key = {m["sid"]: m["oparlKey"] for m in related_objects["Meeting"]}
    agenda_sid_to_key = {a["sid"]: a["oparlKey"] for a in related_objects["AgendaItem"]}
    for c in related_objects["Consultation"]:
        log_edge("Consultation", c["oparlKey"], "meeting", "Meeting",
                 meeting_sid_to_key.get(c.get("meetingSid")), "FK:Consultation.meetingSid")
        log_edge("Consultation", c["oparlKey"], "paper", "Paper",
                 paper_sid_to_key.get(c.get("paperSid")), "FK:Consultation.paperSid")
        log_edge("Consultation", c["oparlKey"], "agendaItem", "AgendaItem",
                 agenda_sid_to_key.get(c.get("agendaItemSid")), "FK:Consultation.agendaItemSid")
    for a in related_objects["AgendaItem"]:
        log_edge("AgendaItem", a["oparlKey"], "meeting", "Meeting",
                 meeting_sid_to_key.get(a.get("meetingSid")), "FK:AgendaItem.meetingSid")

    related_objects["edges"] = edges
    return related_objects

def build_timeline(related_objects: Dict[str, List[Dict]]) -> List[Dict]:
    """
    Build a timeline from related OParl objects, sorted by date.
    """
    timeline_events = []
    for obj_type, objects in related_objects.items():
        _ensure_log().debug(f"Processing {len(objects)} objects of type {obj_type} for timeline")  # Debugging line
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
    _ensure_log().debug(f"Built timeline with {len(timeline_events)} events after sorting")  # Debugging line

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

    _ensure_log().debug(f"Grouping {len(events_with_dates)} timeline events with window of {window_days} days")  # Debugging line

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

    _ensure_log().debug(f"Grouped into {len(grouped)} event groups")  # Debugging line
    return grouped

@timed
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
    _ensure_log().debug(f"Generated embedding for query: {query_embedding[:5]}...")  # Debugging line

    matched_entities: List[Dict[str, Any]] = []
    facets_data: Dict[str, Any] = {}
    applied_filters: List[Dict[str, Any]] = []
    hybrid_distances: Dict[str, Optional[float]] = {}
    hybrid_match_info: Dict[str, Dict[str, Any]] = {}

    if hybrid:
        from src.pgHybridSearch import (
            _strip_terms_py,
            facets as facet_listing,
            hybrid_candidates,
            load_stop_terms,
            parse_filters,
        )

        conn = session.connection()
        applied_filters = parse_filters(filters)
        # Name vectors are embedded from stop-term-stripped names, so the
        # query side of that signal must be stripped too (design decision 6).
        stop_terms = load_stop_terms()
        stripped_query = _strip_terms_py(query, stop_terms)
        query_embedding_stripped = None
        if stripped_query and stripped_query != query:
            query_embedding_stripped = call_embedding_model(
                stripped_query, EMBEDDING_API_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL
            )
        hyb = hybrid_candidates(
            conn, query, query_embedding, top_k, filters=filters, signals=signals,
            query_embedding_stripped=query_embedding_stripped,
        )
        matched_entities = hyb["matched_entities"]
        candidates = hyb["file_candidates"]  # [{oparlKey, score, signals}]
        facets_data = facet_listing(conn)
        hybrid_distances = {
            c["oparlKey"]: c["signals"].get("content") for c in candidates
        }
        hybrid_match_info = {c["oparlKey"]: c["signals"] for c in candidates}
        _ensure_log().debug(f"Hybrid recall: {len(matched_entities)} entities, {len(candidates)} file candidates")
        if not candidates:
            return {
                "query": query,
                "top_files": [],
                "results": [],
                "timeline": [],
                "graph": {"nodes": [], "edges": []},
                "geo_available": False,
                "matched_entities": [],
                "facets": facets_data,
                "applied_filters": applied_filters,
                "message": "No candidates found for the given query/filters",
            }
        # Fused score feeds the reranker stage; distances are kept for output.
        top_scores = [(c["oparlKey"], c["score"]) for c in candidates]
    else:
        # legacy vector-only path
        # find similarities and get top-k files
        file_scores = query_vector_similarity(session, query_embedding, top_k)
        _ensure_log().debug(f"Inital Top files: {file_scores}")  # Debugging line

        _ensure_log().debug(f"Top files (before thresholding): {file_scores}")  # Debugging line
        if not file_scores:
            return {"query": query, "results": [], "timeline": [], "graph": {"nodes": [], "edges": []}, "geo_available": False, "matched_entities": [], "facets": {}, "applied_filters": [], "message": "No files with embeddings found"}

        # filter by threshold
        top_scores = filter_by_threshold(file_scores, threshold=threshold)
        _ensure_log().debug(f"Top files (after thresholding {threshold}): {top_scores}")  # Debugging line
        if not top_scores:
            return {"query": query, "top_files": [], "results": [], "timeline": [], "graph": {"nodes": [], "edges": []}, "geo_available": False, "matched_entities": [], "facets": {}, "applied_filters": [], "message": "No files above similarity threshold"}

    # run reranking on all files and append rerank score to file_score 
    top_scores_with_rerank = []
    _ensure_log().debug(f"Running reranking on top {len(top_scores)} files")  # Debugging line

    if RERANK_MODE == "chat":
        for oparlKey, score in top_scores:
            _ensure_log().debug(f"Processing file {oparlKey} with initial score {score:.4f}")  # Debugging line
            # get file content for reranking
            file_content = session.query(File.content).filter(File.oparlKey == oparlKey).first()
            if file_content and file_content[0]:  # Check if content exists and is not None
                rerank_score = call_reranking_chat_model(query, file_content[0])
                _ensure_log().debug(f"Reranking score for file {oparlKey}: {rerank_score:.4f}")  # Debugging line
                if rerank_score is not None and isinstance(rerank_score, (int, float)) and rerank_score >= .8:
                    top_scores_with_rerank.append((oparlKey, score))
                    _ensure_log().debug(f"Accept reranked file {oparlKey}: original score {score:.4f}, rerank score {rerank_score:.4f}")  # Debugging line
                else:
                    _ensure_log().debug(f"Reject reranked file {oparlKey}: original score {score:.4f}, rerank score {rerank_score:.4f}")  # Debugging line
            else:
                _ensure_log().debug(f"No content found for file {oparlKey}, skipping reranking")  # Debugging line
                top_scores_with_rerank.append((oparlKey, score))  # No content, keep original score
                _ensure_log().debug(f"No content for file {oparlKey}, keeping original score {score:.4f}")  # Debugging line

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
                _ensure_log().debug(f"No content found for file {oparlKey}, skipping reranking")  # Debugging line
                documents.append("")  # Append empty string to maintain order
        rerank_scores = call_reranking_model(query, documents, top_n=len(documents))
        _ensure_log().debug(f"Reranking scores: {rerank_scores}")  # Debugging line
        for i, rscore in enumerate(rerank_scores):
            oparlKey, score = top_scores[i]
            if rscore is None or not isinstance(rscore, (int, float)):
                _ensure_log().debug(f"Invalid rerank score received: {rscore}, keep old score")  # Debugging line
                top_scores_with_rerank.append((oparlKey, score))  # No content, keep original score
            elif rscore >= .8:
                top_scores_with_rerank.append((oparlKey, score * rscore))
                _ensure_log().debug(f"Accept reranked file {oparlKey}: original score {score:.4f}, rerank score {rscore:.4f}")  # Debugging line
            else:
                _ensure_log().debug(f"Reject reranked file {oparlKey}: original score {score:.4f}, rerank score {rscore:.4f}")  # Debugging line
                # reject reranked file. don't append
        

    _ensure_log().debug(f"Top files after reranking: {top_scores_with_rerank}")  # Debugging line

    # Get Keys of top files
    top_file_keys = [f[0] for f in top_scores_with_rerank]
    _ensure_log().debug(f"Top file Keys: {top_file_keys}")
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
        # from that signal, plus which signals matched it (match-type
        # qualifier; name-vector distance included where available)
        "distance": hybrid_distances.get(row.oparlKey)
                    if hybrid else
                    next((score for key, score in top_scores_with_rerank if key == row.oparlKey), None),
        "match": hybrid_match_info.get(row.oparlKey) if hybrid else None,
    } for row in result]
    top_files.sort(key=lambda f: key_rank.get(f["oparlKey"], len(key_rank)))
    _ensure_log().debug(f"Top files details: {top_files}")  # Debugging line
    
    file_sids = {item["oparlKey"]: item["sid"] for item in top_files}
    _ensure_log().debug(f"Resolved file keys to sids: {file_sids}")  # Debugging line

    
    # Find all related OParl objects
    related_objects = find_related_objects(session, file_sids)
    _ensure_log().debug(f"Related objects found: { {k: len(v) for k, v in related_objects.items()} }")  # Debugging line

    # Serialize the traversed graph (nodes + typed edges, add-network-view)
    from src.graphModel import build_graph
    graph = build_graph(related_objects, related_objects.pop("edges", []), top_files)

    # georeferences: streets/districts linked to the GRAPH-connected answer
    # set (seed files + traversal). Deliberately NOT the matched_entities
    # long tail — weak recall matches (rank 11+) drag in unrelated streets
    # and flood the map (analysis: query "rückbau herrenalber strasse":
    # graph scope = 175 features/13 streets, tail scope = 1475/65).
    from src.pgGeo import geo_available_for_keys
    agenda_item_keys = [n["oparlKey"] for n in graph["nodes"] if n["type"] == "AgendaItem"]
    file_keys = [n["oparlKey"] for n in graph["nodes"] if n["type"] in ("File", "AuxFile")]
    file_keys = [k for k in file_keys if k]
    geo_available = geo_available_for_keys(session.get_bind(), agenda_item_keys, file_keys)

    # Build timeline from all related objects
    timeline_events = build_timeline(related_objects)
    _ensure_log().debug(f"Timeline events built: {len(timeline_events)}")  # Debugging line

    # Group timeline events
    grouped_timeline = group_timeline_events(timeline_events)
    _ensure_log().debug(f"Grouped timeline events: {len(grouped_timeline)}")  # Debugging line
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
            "distance": f["distance"],
            "match": f.get("match")
        } for f in top_files],
        "timeline": grouped_timeline,
        "graph": graph,
        "geo_available": geo_available,
        "matched_entities": matched_entities,
        "facets": facets_data,
        "applied_filters": applied_filters,
        "stats": {
            "total_files": len(top_files),
            "total_events": len(timeline_events),
            "event_types": {k: len(v) for k, v in related_objects.items() if v}
        }
    }

@timed
def search_and_summarize(
    session,
    query: str,
    top_k: int = TOP_K,
    threshold: float = 0.40,
    hybrid: bool = True,
    filters: Optional[List[Dict[str, Any]]] = None,
    signals: Optional[Dict[str, bool]] = None,
    summarize: bool = True,
) -> Dict[str, Any]:
    """Convenience wrapper: hybrid search + German summary of the top files.

    Calls :func:`search_and_build_timeline` and — unless *summarize* is
    False or no chat model is configured — runs
    ``src.pgResultSummarizer.ResultSummarizer`` over the result, adding
    ``result["summary"]`` (the field the web app's SummaryCard renders).
    This is the recommended entry point for non-interactive consumers
    (regeneration scripts, the future /search API endpoint).
    """
    result = search_and_build_timeline(
        session, query, top_k=top_k, threshold=threshold,
        hybrid=hybrid, filters=filters, signals=signals,
    )
    if summarize:
        from src.pgResultSummarizer import ResultSummarizer

        ResultSummarizer(session).summarize(result)
    return result


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
                _ensure_log().debug("Please enter a valid query.")
                continue

            try:
                parsed_filters = json.loads(filters) if filters else None
                results = search_and_build_timeline(session, query, top_k=top_k, threshold=threshold, filters=parsed_filters)

                # Print results
                _ensure_log().debug(f"\nQuery: {results['query']}")
                _ensure_log().debug(f"Found {len(results['top_files'])} matching files")

                if results['top_files']:
                    _ensure_log().debug("\nTop Files:")
                    for i, file in enumerate(results['top_files'][:5], 1):
                        _ensure_log().debug(f"{i}. {file['name']} ({file['fileName']})")
                        _ensure_log().debug(f"   Distance: {file['distance']:.3f}")
                        _ensure_log().debug(f"   OParl ID: {file['oparlId']}")
                        _ensure_log().debug(f"   Download URL: {file['downloadurl']}")
                        _ensure_log().debug(f"   Date: {file['date']}")

                    # generate a summary of the top files via the result summarizer
                    from src.pgResultSummarizer import ResultSummarizer

                    ResultSummarizer(session).summarize(results, force=True)
                else:
                    _ensure_log().debug("No top files found above the similarity threshold.")

                if results['timeline']:
                    _ensure_log().debug("\nTimeline of Related Events:")
                    for i, group in enumerate(results['timeline'], 1):
                        _ensure_log().debug(f"\nGroup {i}: {group['start_date']} to {group['end_date']}")
                        for event in group['events']:
                            _ensure_log().debug(f"  - {event['date']}: [{event['type']}] {event['name']} {event['oparlId']}")

                # Save results to file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = os.path.join(directory, f"search_results_{timestamp}.json")
                with open(save_path, 'w') as f:
                    json.dump(results, f, default=str, indent=2, ensure_ascii=False)
                _ensure_log().debug(f"\nDetailed results saved to {save_path}")




            except Exception as e:
                _ensure_log().debug(f"Error processing query: {str(e)}")

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
