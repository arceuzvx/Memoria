# Memoria

**A security-first, model-agnostic AI memory platform.**

Memoria gives users ownership of their AI context. Instead of repeating yourself across ChatGPT, Claude, Gemini, and every other AI system, Memoria provides a portable memory layer that sits between you and any model.

Store memories once. Retrieve them anywhere.

---

## Features

**Core**
- Persistent memory storage with vector embeddings
- Semantic memory search
- Context-aware question answering via LLM
- Memory import and export (JSON)

**Authentication & Security**
- JWT access tokens with refresh token rotation
- bcrypt password hashing
- Per-user memory isolation (multi-tenant)
- Rate limiting on all endpoints
- Input size validation
- Prompt injection defenses

**Infrastructure**
- FastAPI REST API
- Qdrant vector database (authenticated)
- SQLite user database (SQLAlchemy)
- Dockerized deployment
- Minimal frontend dashboard

---

## Architecture

```
User ──▶ Frontend (static HTML/JS)
              │
              ▼
         FastAPI API
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
 SQLite    Gemini    Qdrant
 (auth)   (embed)  (vectors)
              │
              ▼
         Gemini LLM
         (answers)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python 3.12 |
| Auth | JWT (HS256), bcrypt, refresh token rotation |
| Vector DB | Qdrant |
| Embeddings | Gemini `gemini-embedding-001` (3072 dims) |
| LLM | Gemini 2.5 Flash |
| User DB | SQLite + SQLAlchemy |
| Frontend | Vanilla HTML, CSS, JavaScript |
| Infra | Docker, Docker Compose |

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- A [Gemini API key](https://aistudio.google.com/apikey)

### 1. Clone

```bash
git clone https://github.com/yourusername/memoria.git
cd memoria
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your-gemini-api-key
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_API_KEY=your-qdrant-secret
JWT_SECRET_KEY=your-jwt-secret
```

Generate secure secrets:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Run this twice — once for `QDRANT_API_KEY`, once for `JWT_SECRET_KEY`.

### 3. Run

```bash
docker compose up --build
```

### 4. Open

| URL | Description |
|---|---|
| `http://localhost:8000/ui` | Frontend dashboard |
| `http://localhost:8000/docs` | API documentation (Swagger) |

---

## Project Structure

```
memoria/
├── app/
│   ├── main.py              # FastAPI app, routes, request models
│   ├── auth.py              # Registration, login, JWT, refresh tokens
│   ├── models.py            # SQLAlchemy models (User, RefreshToken)
│   ├── schemas.py           # Pydantic schemas, validation
│   ├── database.py          # SQLite engine and session
│   ├── vector_store.py      # Qdrant client and collection setup
│   ├── embeddings.py        # Gemini embedding client
│   ├── llm.py               # Gemini LLM client
│   └── prompt_builder.py    # LLM prompt construction
│
├── static/
│   ├── index.html           # Frontend SPA
│   ├── styles.css           # Dark theme styles
│   └── app.js               # Frontend logic
│
├── docs/
│   └── ai_context.md        # AI assistant context document
│
├── Dockerfile
├── .dockerignore
├── docker-compose.yml
├── requirements.txt
├── .env                      # Not committed (secrets)
└── README.md
```

---

## API Reference

All endpoints except `/`, `/health`, `/register`, and `/login` require a JWT bearer token.

### Authentication

| Method | Endpoint | Description | Rate Limit |
|---|---|---|---|
| `POST` | `/register` | Create account | 3/min |
| `POST` | `/login` | Login, get token pair | 5/min |
| `POST` | `/refresh` | Rotate tokens | 10/min |
| `POST` | `/logout` | Revoke refresh token | 10/min |

### Memories

| Method | Endpoint | Description | Rate Limit |
|---|---|---|---|
| `POST` | `/memory` | Store a memory | 30/min |
| `GET` | `/memories` | List memories (paginated) | 30/min |
| `DELETE` | `/memory/{id}` | Delete a memory | 30/min |
| `GET` | `/search?q=` | Semantic search | 30/min |
| `POST` | `/ask` | Ask a question with context | 10/min |
| `POST` | `/import` | Bulk import (max 100) | 5/min |
| `GET` | `/export` | Export memories (paginated) | 10/min |

### Examples

**Register**
```bash
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username": "shreya", "email": "shreya@example.com", "password": "securepassword123"}'
```

**Login**
```bash
curl -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"username": "shreya", "password": "securepassword123"}'
```

**Store a memory**
```bash
curl -X POST http://localhost:8000/memory \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"text": "I am building Memoria", "source": "manual", "category": "project", "tags": ["ai", "startup"]}'
```

**Search**
```bash
curl "http://localhost:8000/search?q=AI%20project" \
  -H "Authorization: Bearer <access_token>"
```

**Ask**
```bash
curl -X POST http://localhost:8000/ask \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"question": "What projects am I working on?"}'
```

---

## Security

Memoria is designed with security as a first-class concern.

- Passwords hashed with bcrypt (constant-time verification)
- Refresh tokens stored as SHA-256 hashes (database breach doesn't expose tokens)
- Token rotation with replay detection (reuse revokes all sessions)
- Per-user memory isolation via Qdrant payload filtering
- Qdrant secured with API key authentication
- Input size limits to prevent cost amplification
- Prompt injection defenses on LLM prompts
- Rate limiting on all endpoints
- Generic error messages to prevent user enumeration
- Container runs with non-root user (recommended)
- Secrets excluded from Docker image via `.dockerignore`

---

## Roadmap

- [x] v0.1.0 — Core memory platform
- [x] v0.2.0 — JWT authentication & user ownership
- [x] v0.3.0 — Security hardening
- [x] v0.4.0 — Frontend dashboard
- [ ] v0.5.0 — Observability (Prometheus, Grafana)
- [ ] v0.6.0 — CI/CD, cloud deployment
- [ ] Future — OAuth providers, ChatGPT/Claude memory import, cross-model sync

---

## Motivation

AI systems today are stateless. Users repeat the same context across every platform. Memoria explores a different model: **user-owned memory** that is portable across AI providers.

The focus is not another chatbot — it's the infrastructure layer between users and LLMs: vector databases, embeddings, semantic retrieval, and context engineering.

---

## License

This project is licensed under the [MIT License](LICENSE).
