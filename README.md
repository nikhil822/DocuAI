# Chat With Your Documents

A Retrieval-Augmented Generation (RAG) application for asking questions
about PDF documents and receiving answers grounded in retrieved
passages, with source references and token-by-token streaming.

## Project status

The core end-to-end prototype is working: PDF ingestion, token-based
chunking, local embeddings, PostgreSQL/pgvector retrieval, OpenRouter
answer generation, and SSE streaming to a React chat interface. The
retrieval evaluation suite currently reports a **93.3% HitRate@8** and
**0.917 MRR@8** on a 30-question resume-based dataset.

This is a prototype, not a production-ready multi-user service.
Authentication and per-user document authorization, a durable worker
queue, comprehensive answer/citation evaluation, and production
deployment hardening remain future work.

## Contents

-   [Features](#features)
-   [Technology stack](#technology-stack)
-   [Architecture](#architecture)
-   [How the RAG workflow works](#how-the-rag-workflow-works)
-   [Project structure](#project-structure)
-   [Prerequisites](#prerequisites)
-   [Local setup](#local-setup)
-   [Configuration](#configuration)
-   [API endpoints](#api-endpoints)
-   [Data model](#data-model)
-   [Retrieval evaluation](#retrieval-evaluation)

## Features

### Implemented

-   FastAPI backend with health and document/chat endpoints.
-   PDF text extraction using PyMuPDF.
-   Token-based chunking with `tiktoken` (800-token chunks and 100-token
    overlap by default).
-   Local text embeddings using Sentence Transformers.
-   PostgreSQL persistence and vector similarity search with `pgvector`.
-   Semantic top-k retrieval using cosine distance.
-   LLM answer generation through OpenRouter with an OpenAI-compatible
    client.
-   Server-Sent Events (SSE) for incremental answer delivery.
-   React + Vite chat interface that consumes the streaming response.
-   Source metadata including document name, page number, and chunk
    index.
-   PDF upload and ingestion-job status flow in the current development
    version.
-   Retrieval evaluation over a 30-question dataset, including HitRate@k
    and Mean Reciprocal Rank (MRR@k).

### Not yet production-ready

-   User authentication and document-level access control.
-   Durable background queue and recovery after backend restarts.
-   Automated answer correctness, groundedness, and citation validation.
-   Robust handling of scanned PDFs requiring OCR.
-   Comprehensive retry, cancellation, rate-limit, and timeout policies.
-   Production deployment, monitoring, and load testing.

## Technology stack

  -----------------------------------------------------------------------
  Layer                   Technology              Purpose
  ----------------------- ----------------------- -----------------------
  Frontend                React, Vite             Chat, upload UI,
                                                  streaming answer and
                                                  sources

  Backend API             Python, FastAPI         HTTP API and request
                                                  validation

  PDF extraction          PyMuPDF (`fitz`)        Extract text page by
                                                  page

  Chunking                `tiktoken`              Split extracted text
                                                  into token windows

  Embeddings              Sentence Transformers,  Generate
                          `all-MiniLM-L6-v2`      384-dimensional text
                                                  vectors locally

  Database                PostgreSQL              Store document
                                                  metadata, chunks, and
                                                  job metadata

  Vector search           `pgvector`              Similarity search over
                                                  embeddings

  Database client         `psycopg`, `pgvector`   Connect to PostgreSQL
                          Python package          and handle vector
                                                  values

  LLM gateway             OpenRouter              Access a configurable
                                                  chat model

  LLM client              OpenAI Python SDK       Call the
                                                  OpenAI-compatible
                                                  OpenRouter API

  Local database runtime  Docker Compose          Run PostgreSQL with
                                                  pgvector locally

  Streaming               Server-Sent Events      Send generated answer
                          (SSE)                   chunks to the browser
  -----------------------------------------------------------------------

### Why these choices?

-   **FastAPI** provides request validation and async endpoint support.
-   **PostgreSQL + pgvector** keep application data and vector search in
    one database.
-   **Sentence Transformers** generate embeddings locally instead of
    sending document text to an external embedding service.
-   **OpenRouter** keeps the model provider configurable.
-   **SSE** fits one-way streaming from the backend to the browser.
-   **React + Vite** provide a straightforward frontend development
    setup.

## Architecture

``` mermaid
flowchart TD
    U[User] --> UI[React + Vite]
    UI -->|Upload PDF / Ask question| API[FastAPI]
    API --> ING[PDF ingestion]
    ING --> EXT[PyMuPDF extraction]
    EXT --> CH[Token chunking]
    CH --> EMB[Sentence Transformers]
    EMB --> DB[(PostgreSQL + pgvector)]
    API --> RET[Question embedding and top-k retrieval]
    RET <--> DB
    RET --> CTX[Retrieved chunks and source metadata]
    CTX --> LLM[OpenRouter LLM]
    LLM -->|SSE token, sources, done events| API
    API -->|Streaming HTTP response| UI
    UI --> ANS[Answer and source references]
```

## How the RAG workflow works

### 1. Ingestion

1.  The user uploads a PDF.
2.  The backend validates the upload and extracts text page by page.
3.  Each page's text is split into token chunks.
4.  Sentence Transformers generates an embedding for each chunk.
5.  Chunk text, embeddings, and source metadata are saved in PostgreSQL.
6.  The stored chunks become available to semantic retrieval.

The default chunking configuration is **800 tokens** with **100 tokens
of overlap**. Pages are chunked independently to keep page citations
straightforward. This can create smaller chunks at page boundaries or
separate context that spans two pages; chunking should be adjusted only
after measuring retrieval quality.

The embedding model is `sentence-transformers/all-MiniLM-L6-v2`, which
produces **384-dimensional vectors**. The database vector column must
use the matching dimension, and the same embedding model must be used
for both document chunks and user questions.

### 2. Retrieval and answer generation

1.  The user submits a question.
2.  The backend embeds the question using the same embedding model.
3.  PostgreSQL/pgvector ranks stored chunks by cosine distance.
4.  The top retrieved chunks and their source metadata are supplied to
    the LLM.
5.  The LLM generates an answer grounded in the supplied context.
6.  The backend streams answer text and then sends source metadata and a
    completion event.

``` mermaid
sequenceDiagram
    participant B as Browser (React)
    participant A as FastAPI
    participant P as PostgreSQL + pgvector
    participant L as OpenRouter LLM

    B->>A: POST /ask/stream
    A->>A: Embed question
    A->>P: Similarity search
    P-->>A: Top-k chunks and metadata
    A->>L: Question, context, instructions
    loop During generation
        L-->>A: Text delta
        A-->>B: SSE token event
    end
    A-->>B: SSE sources event
    A-->>B: SSE done event
```

Retrieval uses pgvector's cosine-distance operator (`<=>`). The default
`top_k` is 8.

The model is instructed to use the supplied context, cite sources using
identifiers such as `[S1]`, ignore instructions embedded in document
text, and say when the context does not support an answer. Prompt
instructions reduce risk but do not guarantee correctness or valid
citations.

### 3. Streaming events

The streaming endpoint currently uses these SSE event types:

-   `token`: a piece of generated answer text.
-   `sources`: retrieved source metadata.
-   `done`: indicates successful completion.
-   `error`: communicates a generation error.

Network chunks do not necessarily align with SSE event boundaries, so
the frontend must buffer partial data and parse complete events.

## Project structure

The following is a representative layout. Adjust it to match the actual
repository if filenames differ.

``` text
DocuAI/
├── backend/
│   ├── main.py                  # FastAPI routes
│   ├── chunking.py              # Token-window chunking
│   ├── document_processing.py   # Text/chunk processing helpers
│   ├── embeddings.py             # Sentence Transformers model
│   ├── database.py              # PostgreSQL connection
│   ├── ingestion.py             # Extract, embed and persist PDF chunks
│   ├── ingestion_worker.py      # Ingestion job processing
│   ├── retrieval.py              # Vector similarity search
│   ├── llm_service.py            # LLM generation and SSE
│   ├── evaluate_retrieval.py     # Retrieval evaluation
│   ├── eval_questions.json       # 30-question evaluation dataset
│   ├── uploads/                  # Temporary uploads; do not commit
│   ├── .env                      # Local secrets; do not commit
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx               # Chat and upload UI
│   │   ├── App.css
│   │   └── index.css
│   ├── .env                      # Local frontend configuration
│   └── package.json
├── docker-compose.yml
├── .gitignore
└── README.md
```

## Prerequisites

-   Python 3.11 or another version supported by your installed
    dependencies.
-   Node.js and npm.
-   Docker Desktop or Docker Engine with Docker Compose, if running
    PostgreSQL locally.
-   An OpenRouter API key and access to the configured model.
-   Git.

The embedding model downloads its model files on first use, so the first
startup may take longer and requires network access.

## Local setup

Commands below assume separate `backend/` and `frontend/` directories.
Adjust paths and module names to match the repository.

### 1. Start PostgreSQL with pgvector

Create or use a `docker-compose.yml` similar to this example:

``` yaml
services:
  db:
    image: pgvector/pgvector:pg17
    container_name: rag-postgres
    environment:
      POSTGRES_DB: ragdb
      POSTGRES_USER: raguser
      POSTGRES_PASSWORD: local_dev_password
    ports:
      - "5433:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U raguser -d ragdb"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

Start the database:

``` bash
docker compose up -d db
docker compose ps
```

Connect to PostgreSQL:

``` bash
docker exec -it rag-postgres psql -U raguser -d ragdb
```

Enable pgvector:

``` sql
CREATE EXTENSION IF NOT EXISTS vector;
```

**Schema note:** use the schema/migrations in your repository as the
source of truth. The current implementation may use a `documents` table
linked to `chunks` by `document_id`; older setups may only have
`chunks.document_name`. Do not blindly apply a second schema over an
existing database. Back up the database before running migrations.

### 2. Configure the backend

Create and activate a virtual environment:

``` bash
cd backend
python -m venv .venv
```

macOS/Linux:

``` bash
source .venv/bin/activate
```

Windows PowerShell:

``` powershell
.venv\Scripts\Activate.ps1
```

Install dependencies if they are not already captured in
`requirements.txt`:

``` bash
pip install fastapi "uvicorn[standard]" python-multipart \
  pymupdf tiktoken sentence-transformers "psycopg[binary]" \
  pgvector openai python-dotenv
```

Create `backend/.env`:

``` dotenv
DATABASE_URL=postgresql://raguser:local_dev_password@localhost:5433/ragdb
OPENROUTER_API_KEY=replace_with_your_key
OPENROUTER_MODEL=openai/gpt-4o-mini
```

Use a model identifier available to your OpenRouter account; the model
shown is an example and availability/pricing can change.

Ensure the backend loads environment variables during local development,
for example:

``` python
from dotenv import load_dotenv

load_dotenv()
```

Start FastAPI using the module path in your project:

``` bash
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000/docs` to inspect the API. If `main.py` is
nested inside a package, use the appropriate import path.

### 3. Configure the frontend

In a separate terminal:

``` bash
cd frontend
npm install
```

Create `frontend/.env`:

``` dotenv
VITE_API_URL=http://localhost:8000
```

Start Vite:

``` bash
npm run dev
```

Open the URL printed by Vite, typically `http://localhost:5173`.

The FastAPI CORS configuration must allow the exact frontend origin used
locally. Do not expose secrets through `VITE_*` variables because
frontend variables are bundled into client-side code.

## Configuration

  Variable               Used by    Description
  ---------------------- ---------- ---------------------------------
  `DATABASE_URL`         Backend    PostgreSQL connection string
  `OPENROUTER_API_KEY`   Backend    Secret key for the LLM gateway
  `OPENROUTER_MODEL`     Backend    OpenRouter model identifier
  `VITE_API_URL`         Frontend   Base URL of the FastAPI backend

Keep real credentials in local environment files or a secrets manager.
Commit an `.env.example` containing placeholder values if useful, but
never commit `.env`.

## API endpoints

The running application at `http://localhost:8000/docs` is
authoritative. The following endpoints are part of the current API
workflow; confirm exact request/response schemas in the running
application.

  ----------------------------------------------------------------------------
  Method                  Endpoint                     Purpose
  ----------------------- ---------------------------- -----------------------
  `GET`                   `/health`                    Check that the API is
                                                       running

  `POST`                  `/documents/extract`         Extract PDF text for
                                                       inspection

  `POST`                  `/documents/ingest`          Ingest a PDF; the
                                                       current flow may return
                                                       an ingestion job ID

  `GET`                   `/documents/jobs/{job_id}`   Check ingestion job
                                                       status

  `POST`                  `/search`                    Retrieve semantically
                                                       similar chunks

  `POST`                  `/ask`                       Generate a complete
                                                       answer with source
                                                       metadata

  `POST`                  `/ask/stream`                Stream answer tokens
                                                       and source events over
                                                       SSE
  ----------------------------------------------------------------------------

Example semantic search request:

``` json
{
  "question": "How did the export pipeline reduce memory usage?",
  "top_k": 8
}
```

Example streaming request:

``` bash
curl -N -X POST http://localhost:8000/ask/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"question":"How did the export pipeline reduce memory usage?","top_k":8}'
```

The `-N` option disables curl output buffering so streamed events are
easier to observe.

## Data model

The schema can vary depending on which migration has been applied.
Confirm the actual database schema before running manual SQL.

### `documents` (when document identity/version tracking is enabled)

Stores document-level metadata such as the document ID, filename,
content hash, and creation/update timestamps. A stable document ID
allows chunks to be associated with a specific uploaded document and
makes replacing a document's chunks safer.

### `chunks`

  -----------------------------------------------------------------------
  Column                              Meaning
  ----------------------------------- -----------------------------------
  `id`                                Database-generated row identifier

  `document_id`                       Foreign key to `documents.id`, when
                                      the document table is enabled

  `document_name`                     Document filename used for display
                                      or compatibility

  `page_number`                       One-based page number for citations

  `chunk_index`                       Chunk index within a page/document

  `text`                              Text passed to retrieval and the
                                      LLM

  `embedding`                         384-dimensional vector generated by
                                      the configured embedding model

  `embedding_model`                   Model identifier used to create the
                                      vector

  `created_at`                        Row creation timestamp
  -----------------------------------------------------------------------

### `ingestion_jobs` (when background ingestion is enabled)

Tracks ingestion job identifiers, document names, status, errors, and
timestamps. Intended states include `queued`, `processing`, `completed`,
and `failed`.

A job-status table alone does not make a queue durable. A production
worker should recover queued or abandoned jobs after restarts and
prevent unsafe duplicate processing.

## Retrieval evaluation

A 30-question dataset based on a resume PDF is used to check whether
retrieval returns a chunk matching the expected document, page, and at
least one expected answer term.

### Latest reported baseline

  Metric                      Result
  ---------------------- -----------
  Evaluation questions            30
  Hits within top 8               28
  Misses                           2
  HitRate@8                **93.3%**
  MRR@8                    **0.917**

-   **HitRate@8** is the fraction of questions with at least one chunk
    meeting the current relevance rule in the top eight results.
-   **MRR@8 (Mean Reciprocal Rank)** averages the reciprocal rank of the
    first relevant result. A relevant result at rank 1 contributes
    `1.0`; rank 2 contributes `0.5`; a question with no relevant result
    in the top eight contributes `0`.
