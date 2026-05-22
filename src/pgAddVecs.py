from sqlalchemy import create_engine, Column, Integer, String, func, text, desc, inspect
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import ARRAY
import numpy as np
from pgvector.sqlalchemy import Vector

# important: 
# sudo -u postgres psql
# \c riski_agentic
# CREATE EXTENSION vector;


# Database connection
import private as pr
engine = create_engine(f"postgresql+psycopg2://{pr.DB_USER}:{pr.DB_PWD}@{pr.DB_HOST}/{pr.DB_NAME}")
Session = sessionmaker(bind=engine)
Base = declarative_base()

# Define the table
class Embedding(Base):
    __tablename__ = "embeddings"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    value = Column(Vector(1024))  # 1024-dimensional vector


# Drop the table if it exists
inspector = inspect(engine)
if inspector.has_table("embeddings"):
    Embedding.__table__.drop(engine)


# Create the table
Base.metadata.create_all(engine)

with np.load("/mnt_ai/data/odd26/ris/riski/riski-vec.npz", allow_pickle=True) as data:
    loaded_vectors = data["vectors"]
    loaded_files = data["files"]
    print(f"Loaded {len(loaded_vectors)} vectors and {len(loaded_files)} files from output.")

embs  = [Embedding(name=name, value=vec) for name, vec in zip(loaded_files, loaded_vectors)]

# Insert sample data
session = Session()
session.add_all(embs)

session.commit()

session.close()



