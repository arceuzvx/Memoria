# Memoria

**Model-Agnostic Memory & Context Engine for AI Applications**

Memoria is a context retrieval service that provides persistent memory for Large Language Models (LLMs). It stores user memories as vector embeddings, retrieves relevant context through semantic search, and injects that context into prompts before sending them to an LLM.

The goal is to separate **memory** from **reasoning**, allowing the same context layer to work with multiple AI models.

---

## Why Memoria?

Modern AI systems are largely stateless. They can only reason over the information available in the current prompt or conversation window.

As users switch between different AI platforms, context is fragmented:

* ChatGPT knows one thing
* Claude knows another
* Gemini knows something else

Memoria explores the idea of a shared context layer where memory is owned by the user rather than a specific model.

---

## Features

* Persistent memory storage
* Semantic memory retrieval
* Vector search with Qdrant
* Gemini embedding generation
* Context-aware prompt construction
* FastAPI REST API
* Dockerized deployment
* Model-agnostic architecture

---

## Architecture

```text
User
  │
  ▼
FastAPI
  │
  ▼
Gemini Embeddings
  │
  ▼
Qdrant Vector Database
  │
  ▼
Prompt Builder
  │
  ▼
LLM
```

### Memory Flow

```text
User Memory
     │
     ▼
Embedding Generation
     │
     ▼
Qdrant Storage
```

### Retrieval Flow

```text
User Question
      │
      ▼
Embedding Generation
      │
      ▼
Semantic Search
      │
      ▼
Relevant Memories
      │
      ▼
Prompt Construction
      │
      ▼
LLM Response
```

---

## Tech Stack

### Backend

* FastAPI
* Python 3.12

### AI

* Gemini Embeddings
* Gemini 2.5 Flash

### Database

* Qdrant Vector Database

### Infrastructure

* Docker
* Docker Compose

---

## Project Structure

```text
memoria/
│
├── app/
│   ├── main.py
│   ├── vector_store.py
│   ├── embeddings.py
│   ├── llm.py
│   └── prompt_builder.py
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env
└── README.md
```

---

# API Endpoints

## Health Check

### GET `/`

Returns application status and version.

**Response**

```json
{
  "status": "Memoria running",
  "version": "0.1.0"
}
```

---

### GET `/health`

Returns service health status.

**Response**

```json
{
  "status": "healthy"
}
```

---

## Memory Management

### POST `/memory`

Store a new memory.

**Request**

```json
{
  "text": "I am building Memoria",
  "source": "manual",
  "category": "project",
  "tags": ["startup", "ai"]
}
```

**Response**

```json
{
  "message": "memory stored",
  "id": "uuid"
}
```

---

### GET `/memories`

Retrieve all stored memories.

**Response**

```json
[
  {
    "id": "uuid",
    "text": "I am building Memoria",
    "source": "manual",
    "category": "project",
    "tags": ["startup", "ai"],
    "timestamp": "2026-06-14T12:00:00+00:00"
  }
]
```

---

### DELETE `/memory/{memory_id}`

Delete a memory by ID.

**Response**

```json
{
  "deleted": "memory_id"
}
```

---

## Memory Import & Export

### POST `/import`

Bulk import memories.

**Request**

```json
[
  {
    "text": "I am learning Kubernetes",
    "source": "chatgpt",
    "category": "learning",
    "tags": ["cloud", "devops"]
  },
  {
    "text": "I am building TraceHawk",
    "source": "claude",
    "category": "project",
    "tags": ["security"]
  }
]
```

**Response**

```json
{
  "imported": 2,
  "ids": [
    "uuid1",
    "uuid2"
  ]
}
```

---

### GET `/export`

Export all memories.

**Response**

```json
[
  {
    "id": "uuid",
    "text": "I am building Memoria",
    "source": "manual",
    "category": "project",
    "tags": ["startup"],
    "timestamp": "2026-06-14T12:00:00+00:00"
  }
]
```

---

## Semantic Search

### GET `/search?q=<query>`

Search memories using semantic vector similarity.

**Example**

```http
GET /search?q=AI project
```

**Response**

```json
{
  "results": [
    {
      "id": "uuid",
      "text": "I am building Memoria",
      "source": "manual",
      "category": "project",
      "tags": ["startup", "ai"],
      "timestamp": "2026-06-14T12:00:00+00:00",
      "score": 0.92
    }
  ]
}
```

---

## Context-Aware Question Answering

### POST `/ask`

Ask a question using stored memories as context.

**Request**

```json
{
  "question": "What projects am I currently working on?"
}
```

**Workflow**

1. Generate embedding for the question
2. Search relevant memories in Qdrant
3. Build contextual prompt
4. Send prompt to the LLM
5. Return generated answer

**Response**

```json
{
  "question": "What projects am I currently working on?",
  "memories": [
    {
      "text": "I am building Memoria",
      "source": "manual",
      "category": "project",
      "tags": ["startup", "ai"],
      "timestamp": "2026-06-14T12:00:00+00:00"
    }
  ],
  "answer": "You are currently building Memoria..."
}
```
---

## Future Roadmap

### V2

* Memory categories
* Metadata and timestamps
* User profiles
* Authentication
* Memory management UI

### V3

* Multi-model support
* Claude integration
* OpenAI integration
* Grok integration
* Perplexity integration

### V4

* Shared context layer across AI applications
* User-owned memory platform
* Context synchronization engine
* Cross-model memory portability

---

## Motivation

Memoria was built to understand how modern AI systems manage context, memory, and retrieval.

Rather than building another chatbot, the focus of this project is the infrastructure layer between users and LLMs:

* Vector databases
* Embeddings
* Semantic retrieval
* Context engineering
* AI infrastructure

The long-term vision is a model-agnostic context platform where users own their memories and can use them across multiple AI systems.
