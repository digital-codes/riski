from sqlalchemy import create_engine, Column, Integer, String, func, text, desc, inspect
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import ARRAY
import numpy as np
from pgvector.sqlalchemy import Vector

import requests
import private as pr


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
    vector = result["data"][0]['embedding'] if isinstance(result, dict) else []
    
    return vector


def filter_by_threshold(vectors_with_scores: list[tuple], threshold: float) -> list[tuple]:
    """Filter vectors above threshold"""
    return [(vec, score) for vec, score in vectors_with_scores if score >= threshold]


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
    # Configuration
    EMBEDDING_API_URL = pr.EMB_URL  # Adjust based on your private.py structure
    EMBEDDING_MODEL = pr.EMB_MDL  # Adjust based on your private.py structure
    EMBEDDING_API_KEY = pr.EMB_KEY  # Add if authentication required
    THRESHOLD = 0.45  # distance threshold (smaller is better)
    TOP_K = 10  # Number of results to return
    
    # Database setup
    pgengine = create_engine(
        f"postgresql+psycopg2://{pr.RO_USER}:{pr.RO_PWD}@{pr.DB_HOST}/{pr.DB_NAME}"
    )
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
    
