from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel

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


class MemoryRequest(BaseModel):
    text: str


class QuestionRequest(BaseModel):
    question: str


@app.get("/")
def root():
    return {
        "status": "Memoria running"
    }


@app.post("/memory")
def store_memory(data: MemoryRequest):

    vector = embed_text(data.text)

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=str(uuid4()),
                vector=vector,
                payload={
                    "text": data.text
                }
            )
        ]
    )

    return {
        "message": "memory stored"
    }


@app.get("/search")
def search_memory(q: str):

    vector = embed_text(q)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=5
    )

    print("TYPE:", type(results))
    print("RESULTS:", results)

    if hasattr(results, "points"):
        print("POINTS:", results.points)

        if len(results.points) > 0:
            print("FIRST:", results.points[0])
            print("FIRST TYPE:", type(results.points[0]))

    return {
    "results": [
        {"text": p.payload["text"], "score": p.score}
        for p in results.points
    ]
}

@app.post("/ask")
def ask(data: QuestionRequest):

    vector = embed_text(data.question)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=5
    )

    memories = [
        hit.payload["text"]
        for hit in results.points
    ]

    prompt = build_prompt(
        data.question,
        memories
    )

    answer = ask_llm(prompt)

    return {
        "question": data.question,
        "memories": memories,
        "answer": answer
    }