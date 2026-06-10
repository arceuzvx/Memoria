import os

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams
)

COLLECTION_NAME = "memoria"

client = QdrantClient(
    host=os.getenv("QDRANT_HOST"),
    port=int(os.getenv("QDRANT_PORT"))
)

def create_collection(vector_size: int):

    collections = client.get_collections().collections

    exists = any(
        c.name == COLLECTION_NAME
        for c in collections
    )

    if not exists:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE
            )
        )