import os
from dotenv import load_dotenv

# load_dotenv() MUST run before any module that reads environment
# variables at import time (vector_store, embeddings, llm, auth).
load_dotenv()

from pathlib import Path
from uuid import uuid4
import logging
from fastapi import FastAPI, HTTPException, Depends, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, UTC
from qdrant_client.models import (
    PointIdsList,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.embeddings import embed_text

from app.vector_store import (
    client,
    create_collection,
    ensure_payload_indexes,
    COLLECTION_NAME,
)

from app.prompt_builder import build_prompt
from app.llm import ask_llm
from app.database import engine
from app.models import Base, User
from app.auth import router as auth_router, limiter, get_current_user
from app.schemas import PaginatedMemories

# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------
# Fail fast if the JWT secret is missing — better a crash at deploy time
# than a silent security hole at runtime.

_jwt_key = os.getenv("JWT_SECRET_KEY", "")
if len(_jwt_key) < 32:
    raise RuntimeError(
        "JWT_SECRET_KEY must be set and at least 32 characters long. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

app = FastAPI(title="Memoria")

# ---------------------------------------------------------------------------
# Rate limiter — slowapi middleware
# ---------------------------------------------------------------------------

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# Database — create tables on startup
# ---------------------------------------------------------------------------

Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth_router)

# ---------------------------------------------------------------------------
# Static files — serves the frontend at /static/
# ---------------------------------------------------------------------------

_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/ui", include_in_schema=False)
def serve_ui():
    """Serve the frontend SPA."""
    index = _static_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    raise HTTPException(status_code=404, detail="Frontend not found")


# gemini-embedding-001 = 3072 dimensions
VECTOR_SIZE = 3072

create_collection(VECTOR_SIZE)
ensure_payload_indexes()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request models — input size limits
# ---------------------------------------------------------------------------
# Hard caps prevent cost amplification (each text field triggers a
# Gemini embedding call) and limit Qdrant payload bloat.
#   - 10 000 chars ≈ 2 500 words — generous for a single memory.
#   - 20 tags × 50 chars each — prevents tag-bombing.
#   - 2 000 chars for questions — well above normal usage.
#   - Import batch capped at 100 (enforced at endpoint level).
# ---------------------------------------------------------------------------

_MAX_MEMORY_TEXT = 10_000
_MAX_QUESTION_TEXT = 2_000
_MAX_TAG_COUNT = 20
_MAX_TAG_LENGTH = 50
_MAX_FIELD_LENGTH = 100
_MAX_IMPORT_BATCH = 100


class MemoryRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=_MAX_MEMORY_TEXT)
    source: str = Field(default="manual", max_length=_MAX_FIELD_LENGTH)
    category: str = Field(default="general", max_length=_MAX_FIELD_LENGTH)
    tags: list[str] = Field(default_factory=list, max_length=_MAX_TAG_COUNT)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        for tag in v:
            if len(tag) > _MAX_TAG_LENGTH:
                raise ValueError(
                    f"Each tag must be at most {_MAX_TAG_LENGTH} characters"
                )
        return v


class ImportMemory(BaseModel):
    text: str = Field(..., min_length=1, max_length=_MAX_MEMORY_TEXT)
    source: str = Field(default="import", max_length=_MAX_FIELD_LENGTH)
    category: str = Field(default="general", max_length=_MAX_FIELD_LENGTH)
    tags: list[str] = Field(default_factory=list, max_length=_MAX_TAG_COUNT)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        for tag in v:
            if len(tag) > _MAX_TAG_LENGTH:
                raise ValueError(
                    f"Each tag must be at most {_MAX_TAG_LENGTH} characters"
                )
        return v


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=_MAX_QUESTION_TEXT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_filter(user_id: int) -> Filter:
    """Build a Qdrant filter scoped to a single user."""
    return Filter(
        must=[
            FieldCondition(
                key="user_id",
                match=MatchValue(value=str(user_id)),
            )
        ]
    )


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "status": "Memoria running",
        "version": "0.3.0"
    }

@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


# ---------------------------------------------------------------------------
# Protected endpoints — all require JWT via get_current_user
# ---------------------------------------------------------------------------

@app.post("/memory")
@limiter.limit("30/minute")
def store_memory(
    request: Request,
    data: MemoryRequest,
    current_user: User = Depends(get_current_user),
):
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
                    "user_id": str(current_user.id),
                    "created_by": current_user.username,
                    "text": data.text,
                    "source": data.source,
                    "category": data.category,
                    "tags": data.tags,
                    "timestamp": datetime.now(UTC).isoformat()
                }
            )
        ]
    )

    logger.info("Memory stored: %s (user=%s)", memory_id, current_user.username)

    return {
        "message": "memory stored",
        "id": memory_id
    }


@app.get("/memories", response_model=PaginatedMemories)
@limiter.limit("30/minute")
def get_memories(
    request: Request,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    cursor: str | None = Query(default=None, description="Cursor from previous page"),
):
    """
    List the authenticated user's memories with cursor-based pagination.

    Pass the ``next_cursor`` value from the response as the ``cursor``
    query parameter to fetch the next page.
    """
    memories, next_offset = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=_user_filter(current_user.id),
        limit=limit,
        offset=cursor,
        with_payload=True,
    )

    items = [
        {"id": str(memory.id), **memory.payload}
        for memory in memories
    ]

    return PaginatedMemories(
        memories=items,
        next_cursor=str(next_offset) if next_offset else None,
        count=len(items),
    )


@app.get("/export", response_model=PaginatedMemories)
@limiter.limit("10/minute")
def export_memories(
    request: Request,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=500, description="Items per page"),
    cursor: str | None = Query(default=None, description="Cursor from previous page"),
):
    """
    Export the authenticated user's memories with cursor-based pagination.

    Higher default limit (100) and maximum (500) than /memories to
    support bulk export workflows.  Paginate until ``next_cursor``
    is ``null`` to export everything.
    """
    memories, next_offset = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=_user_filter(current_user.id),
        limit=limit,
        offset=cursor,
        with_payload=True,
    )

    items = [
        {"id": str(memory.id), **memory.payload}
        for memory in memories
    ]

    return PaginatedMemories(
        memories=items,
        next_cursor=str(next_offset) if next_offset else None,
        count=len(items),
    )


@app.delete("/memory/{memory_id}")
@limiter.limit("30/minute")
def delete_memory(
    request: Request,
    memory_id: str,
    current_user: User = Depends(get_current_user),
):
    # BOLA mitigation: retrieve the point first and verify ownership.
    # Without this check, any authenticated user could delete another
    # user's memory by guessing the UUID — a horizontal privilege
    # escalation vulnerability (OWASP API1:2023).
    points = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[memory_id],
        with_payload=True,
        with_vectors=False,
    )

    if not points:
        raise HTTPException(status_code=404, detail="Memory not found")

    point = points[0]
    if point.payload.get("user_id") != str(current_user.id):
        # Return 404 instead of 403 to prevent information leakage —
        # an attacker should not be able to distinguish "exists but
        # not mine" from "does not exist".
        raise HTTPException(status_code=404, detail="Memory not found")

    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=PointIdsList(
            points=[memory_id]
        )
    )

    logger.info("Memory deleted: %s (user=%s)", memory_id, current_user.username)

    return {
        "deleted": memory_id
    }


@app.get("/search")
@limiter.limit("30/minute")
def search_memory(
    request: Request,
    q: str,
    current_user: User = Depends(get_current_user),
):
    vector = embed_text(q)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        query_filter=_user_filter(current_user.id),
        limit=5,
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
@limiter.limit("10/minute")
def ask(
    request: Request,
    data: QuestionRequest,
    current_user: User = Depends(get_current_user),
):
    if not data.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    vector = embed_text(data.question)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        query_filter=_user_filter(current_user.id),
        limit=5,
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
@limiter.limit("5/minute")
def import_memories(
    request: Request,
    memories: list[ImportMemory],
    current_user: User = Depends(get_current_user),
):
    if not memories:
        raise HTTPException(status_code=400, detail="No memories provided")

    if len(memories) > _MAX_IMPORT_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {_MAX_IMPORT_BATCH} memories per import request",
        )

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
                    "user_id": str(current_user.id),
                    "created_by": current_user.username,
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
        points=points,
    )

    logger.info(
        "Memories imported (user=%s)",
        current_user.username,
        extra={"imported": len(points)},
    )

    return {
        "imported": len(points),
        "ids": imported_ids
    }