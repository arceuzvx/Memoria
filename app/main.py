from uuid import uuid4
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime, UTC
from qdrant_client.models import PointIdsList

from qdrant_client.models import PointStruct

from app.embeddings import embed_text

from app.vector_store import (
    client,
    create_collection,
    COLLECTION_NAME
)

from app.prompt_builder import build_prompt
from app.llm import ask_llm

app = FastAPI(title="Memoria")

# gemini-embedding-001 = 3072 dimensions
VECTOR_SIZE = 3072

create_collection(VECTOR_SIZE)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


class MemoryRequest(BaseModel):
    text: str
    source: str = "manual"
    category: str = "general"
    tags: list[str] = Field(default_factory=list)

class ImportMemory(BaseModel):
    text: str
    source: str = "import"
    category: str = "general"
    tags: list[str] = Field(default_factory=list)

class QuestionRequest(BaseModel):
    question: str


@app.get("/")
def root():
    return {
        "status": "Memoria running",
        "version": "0.1.0"
    }

@app.get("/health")
def health():
    return {
        "status": "healthy"
    }

@app.post("/memory")
def store_memory(data: MemoryRequest):

    memory_id = str(uuid4())

    if not data.text.strip():
        raise HTTPException(status_code=400, detail="Memory text cannot be empty")
    
    vector = embed_text(data.text)


    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=memory_id,
                vector=vector,
                payload={
                    "text": data.text,
                    "source": data.source,
                    "category": data.category,
                    "tags": data.tags,
                    "timestamp": datetime.now(UTC).isoformat()
                }
            )
        ]
    )

    logger.info(f"Memory stored: {memory_id}")

    return {
        "message": "memory stored",
        "id": memory_id
    }

@app.get("/memories")
def get_memories():

    memories, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        limit=1000,
        with_payload=True
    )

    return [
        {
            "id": str(memory.id),
            **memory.payload
        }
        for memory in memories
    ]

@app.get("/export")
def export_memories():

    memories, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        limit=1000,
        with_payload=True
    )

    return [
        {
            "id": str(memory.id),
            **memory.payload
        }
        for memory in memories
    ]

@app.delete("/memory/{memory_id}")
def delete_memory(memory_id: str):

    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=PointIdsList(
            points=[memory_id]
        )
    )

    logger.info(f"Memory deleted: {memory_id}")

    return {
        "deleted": memory_id
    }

@app.get("/search")
def search_memory(q: str):
    vector = embed_text(q)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=5
    )

    logger.info("Search executed", extra={"query": q, "hits": len(results.points) if hasattr(results, 'points') else 0})

    return {
        "results": [
            {
                "id": str(p.id),
                "text": p.payload["text"],
                "source": p.payload.get("source"),
                "category": p.payload.get("category"),
                "tags": p.payload.get("tags", []),
                "timestamp": p.payload.get("timestamp"),
                "score": p.score
            }
            for p in (results.points or [])
        ]
    }

@app.post("/ask")
def ask(data: QuestionRequest):

    if not data.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    vector = embed_text(data.question)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=5
    )

    memories = [
        {
            "text": hit.payload.get("text"),
            "source": hit.payload.get("source"),
            "category": hit.payload.get("category"),
            "tags": hit.payload.get("tags", []),
            "timestamp": hit.payload.get("timestamp")
        }
        for hit in (results.points or [])
    ]

    # For backward compatibility the prompt builder expects a list of texts
    memories_texts = [m["text"] for m in memories if m.get("text")]

    prompt = build_prompt(
        data.question,
        memories_texts
    )

    answer = ask_llm(prompt)

    logger.info("Ask executed", extra={"question": data.question, "memories_count": len(memories)})

    return {
        "question": data.question,
        "memories": memories,
        "answer": answer
    }

@app.post("/import")
def import_memories(
    memories: list[ImportMemory]
):
    if not memories:
        raise HTTPException(status_code=400,detail="No memories provided")

    points = []
    imported_ids = []

    for memory in memories:
        if not memory.text.strip():
            raise HTTPException(status_code=400, detail="Imported memory text cannot be empty")

        vector = embed_text(memory.text)

        point_id = str(uuid4())
        imported_ids.append(point_id)

        points.append(
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "text": memory.text,
                    "source": memory.source,
                    "category": memory.category,
                    "tags": memory.tags,
                    "timestamp": datetime.now(UTC).isoformat()
                }
            )
        )

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )

    logger.info("Memories imported", extra={"imported": len(points)})

    return {
        "imported": len(points),
        "ids": imported_ids
    }