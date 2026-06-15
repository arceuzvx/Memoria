import os
import logging

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PayloadSchemaType,
)

logger = logging.getLogger(__name__)

COLLECTION_NAME = "memoria"

_qdrant_api_key = os.getenv("QDRANT_API_KEY")
if not _qdrant_api_key:
    logger.warning(
        "QDRANT_API_KEY is not set — connecting to Qdrant WITHOUT "
        "authentication. This is acceptable for local development "
        "but MUST be configured in production."
    )

client = QdrantClient(
    host=os.getenv("QDRANT_HOST"),
    port=int(os.getenv("QDRANT_PORT", "6333")),
    api_key=_qdrant_api_key,
    # The qdrant-client library auto-enables HTTPS when an api_key is
    # provided.  Inside Docker Compose the Qdrant container serves plain
    # HTTP — TLS termination happens at the reverse-proxy layer in
    # production.  Force HTTP here to avoid SSL handshake failures.
    https=False,
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


def ensure_payload_indexes():
    """
    Create payload indexes for fields that are frequently filtered.

    Without an index on ``user_id``, every filtered scroll/query
    performs a full scan across all points in the collection.  With
    a KEYWORD index, Qdrant builds an inverted index that resolves
    user-scoped queries in O(user's points) instead of O(all points).

    This function is idempotent — Qdrant silently ignores index
    creation requests for fields that are already indexed.
    """
    try:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="user_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        logger.info("Payload index ensured: user_id (KEYWORD)")
    except Exception as e:
        # Index may already exist — log and continue.
        logger.debug("Payload index creation skipped (may already exist): %s", e)