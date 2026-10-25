
# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.<name>``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass
from sqlalchemy import create_engine, Column, Integer, String, func, text, desc, inspect
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
import numpy as np
from pgvector.sqlalchemy import Vector

import requests

# Shared layers: read-only DB engine and centralised embedding client
from src.db import get_engine
from src import remote


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

    Endpoint/model/key configuration lives in ``src.remote`` (resolved from
    ``private.py`` / environment variables); the arguments are kept for API
    compatibility and override the shared configuration when given.
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

def queryFiles(session, key) -> tuple[str, str, str, str]:
    """Query PostgreSQL for file URL and content based on document key"""
    # Adjust table/column names based on your schema
    key = key.lstrip('0') or '0'
    #print(f"Querying file for key: {key}")  # Debug print to check key format
    result = session.query(File).filter(File.oparlKey == key).first()
    if result:
        #print(f"File query result: {result}")  # Debug print to check query result
        return result.date, result.name, result.downloadurl, result.content
    else:        
        raise Exception(f"No file found for key: {key}")


def main():
    # Configuration comes from the shared layers (private.py / env)
    EMBEDDING_API_URL = remote.EMBED_BASE_URL
    EMBEDDING_MODEL = remote.EMBED_MODEL
    EMBEDDING_API_KEY = remote.EMBED_API_KEY
    THRESHOLD = 0.45  # distance threshold (smaller is better)
    TOP_K = 10  # Number of results to return

    # Database setup on the shared read-only engine
    pgengine = get_engine(readonly=True)
    PgSession = sessionmaker(bind=pgengine)

    # Check table exists
    inspector = inspect(pgengine)
    if not inspector.has_table("contentEmbeddings"):
        raise Exception("Table 'contentEmbeddings' does not exist")
    # we need File table in in postgres as well. Mariadb no longer in use, migrate to postgres only
    if not inspector.has_table("File"):
        raise Exception("Table 'File' does not exist")

    
    # Get user input
    user_text = input("Enter your query text: ")
    
    # Step 1: Call embedding model
    print("Calling embedding model...")
    vector = call_embedding_model(user_text, EMBEDDING_API_URL, EMBEDDING_API_KEY, EMBEDDING_MODEL)
    
    
    # Step 2: Query PostgreSQL for similarity
    print("Querying vector database...")
    pgSession = PgSession()
    try:
        docs = query_vector_similarity(pgSession, vector, TOP_K)
        
        # Step 4: Print document names
        print("\nMatching Embeddings Names:")
        for doc_key, distance in docs:
            print(f"Key: {doc_key}, Distance: {distance:.4f}")
            

        # Step 3: Filter by distance
        print(f"\nEmbeddings within distance threshold {THRESHOLD}:")
        # filtered_results = [(name, distance) for name, distance in docs if distance <= THRESHOLD]  # Single result from model with default score
        #for name, distance in filtered_results:
        #    print(f"Name: {name}, Distance: {distance:.4f}")    
        filtered_docs = [doc_key for doc_key, distance in sorted(docs, key=lambda x: x[1]) if distance <= THRESHOLD]  # Single result from model with default score
        print(filtered_docs)

        
        fileResults = []
        for key in filtered_docs:
            try:
                print(f"Key: {key}")
                date, name, url, content = queryFiles(pgSession, key)
                fileResults.append((key, date, name, url, content))
                # print(f"Date: {date}, Name: {name}, URL: {url}\nContent: {content}\n")
            except Exception as e:
                    print(f"Error querying file {key}: {e}")

    finally:
        pgSession.close()

    fileResults.sort(key=lambda x: x[0], reverse=True)  # Sort by date, newest first
    print("\nSorted File Results:")
    for key, date, name, url, content in fileResults:
        print(f"Key: {key}, Date: {date}, Name: {name}, URL: {url}\nContent: {content[:400]}\n")


if __name__ == "__main__":
    main()
    
