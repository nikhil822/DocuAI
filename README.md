# Chat With Your Documents

A Retrieval-Augmented Generation (RAG) application that lets users ask
questions about PDF documents and receive answers grounded in retrieved
document passages, with source references and streaming output.

> **Project status:** The backend PDF-processing, embedding,
> PostgreSQL/pgvector retrieval, LLM answer generation, and SSE
> streaming flow have been built during development. The React streaming
> chat has been connected and its incremental-rendering issue was fixed.
> PDF upload UI and background ingestion/job tracking are part of the
> current development path; verify the latest code and tests before
> treating those pieces as complete. Authentication, per-user document
> access control, durable background workers, and production deployment
> hardening are not implemented yet.

## Contents

-   [Overview](#overview)
-   [Features](#features)
-   [Technology stack](#technology-stack)
-   [Architecture](#architecture)
-   [RAG workflow](#rag-workflow)
-   [Project structure](#project-structure)
-   [Prerequisites](#prerequisites)
-   [Local setup](#local-setup)
-   [Configuration](#configuration)
-   [API endpoints](#api-endpoints)
-   [Data model](#data-model)
-   [Evaluation](#evaluation)
-   [Troubleshooting](#troubleshooting)
-   [Security and production
    considerations](#security-and-production-considerations)
-   [Roadmap](#roadmap)

## Overview

Traditional keyword search finds documents containing particular words.
RAG combines semantic search with a Large Language Model (LLM):

1.  Extract text from documents.
2.  Split the text into smaller chunks.
3.  Convert each chunk into an embedding (a numerical representation of
    its meaning).
4.  Store the chunks and embeddings in PostgreSQL with the `pgvector`
    extension.
5.  Convert a user's question into an embedding and retrieve similar
    chunks.
6.  Give the retrieved context and question to an LLM.
7.  Return an answer with source references, or abstain when the
    available context does not support an answer.

The LLM does not search the database by itself. The application
retrieves context first and then supplies that context to the model.

## Features

### Implemented and exercised during development

-   FastAPI backend with a health endpoint.
-   PDF text extraction using PyMuPDF.
-   Token-window chunking with `tiktoken`.
-   Local text embeddings using Sentence Transformers.
-   PostgreSQL persistence with `pgvector`.
-   Semantic top-k retrieval.
-   LLM answer generation through OpenRouter using an OpenAI-compatible
    client.
-   Server-Sent Events (SSE) for incremental answer delivery.
-   React chat interface that consumes the streaming response.
-   Source metadata including document name, page number, and chunk
    index.
-   Initial retrieval evaluation using a 30-question dataset; the
    reported baseline was 22 hits out of 30 (73.3%) using a
    keyword-based proxy metric.

### Under development / verify locally

-   Uploading PDFs through the React UI.
-   Background ingestion with persistent job status (`queued`,
    `processing`, `completed`, `failed`).
-   Polling job status from the frontend.

### Not yet production-ready

-   User authentication and document-level authorization.
-   Durable job queue and worker recovery after a process restart.
-   Robust document versioning and duplicate-file handling.
-   Streaming cancellation, retries, and comprehensive timeout handling.
-   Automated answer-quality and citation-quality evaluation.

## Technology stack

  -----------------------------------------------------------------------
  Layer                   Technology              Purpose
  ----------------------- ----------------------- -----------------------
  Frontend                React                   Chat interface, upload
                                                  form, source display

  Frontend tooling        Vite                    Local development
                                                  server and build
                                                  tooling

  Backend API             Python, FastAPI         HTTP API and request
                                                  validation

  PDF extraction          PyMuPDF (`fitz`)        Extract text page by
                                                  page from PDFs

  Chunking                `tiktoken`              Split text into token
                                                  windows

  Embeddings              Sentence Transformers,  Convert text and
                          `all-MiniLM-L6-v2`      questions into
                                                  384-dimensional vectors

  Database                PostgreSQL              Store document chunks
                                                  and job metadata

  Vector search           `pgvector`              Similarity search over
                                                  embeddings

  Database driver         `psycopg` and           Connect Python code to
                          `pgvector` Python       PostgreSQL and map
                          integration             vector values

  LLM gateway             OpenRouter              Access a configured
                                                  chat model

  LLM client              OpenAI Python SDK       Call OpenRouter's
                                                  OpenAI-compatible API

  Local database runtime  Docker Compose          Run PostgreSQL with
                                                  pgvector locally

  Streaming protocol      Server-Sent Events      Deliver generated
                          (SSE)                   answer text
                                                  incrementally
  -----------------------------------------------------------------------

### Why these choices?

-   **FastAPI:** provides type-friendly request validation and async
    endpoint support.
-   **PostgreSQL + pgvector:** stores application data and vectors in
    one database for this project's current scale.
-   **Sentence Transformers:** allows embeddings to run locally, without
    sending document text to a separate embedding API.
-   **OpenRouter:** separates the LLM provider from the rest of the
    application and makes the model configurable.
-   **SSE:** fits the one-way streaming response from the backend to the
    browser.
-   **React + Vite:** provides a small, straightforward frontend setup.

## Architecture

``` mermaid
flowchart TD
    U[User] --> UI[React + Vite]
    UI -->|Upload PDF / Ask question| API[FastAPI]
    API --> ING[PDF ingestion pipeline]
    ING --> EXT[PyMuPDF extraction]
    EXT --> CH[Token chunking]
    CH --> EMB[Sentence Transformers embeddings]
    EMB --> DB[(PostgreSQL + pgvector)]
    API --> RET[Question embedding and top-k retrieval]
    RET <--> DB
    RET --> CTX[Retrieved chunks + source metadata]
    CTX --> LLM[OpenRouter LLM]
    LLM -->|SSE token, sources, done events| API
    API -->|Streaming HTTP response| UI
    UI --> ANS[Answer and source references]
```

## RAG workflow

### 1. Ingestion

``` mermaid
flowchart TD
    A[PDF upload] --> B[Validate file]
    B --> C[Extract text by page]
    C --> D[Split page text into token chunks]
    D --> E[Generate embeddings]
    E --> F[Insert text, metadata and vectors]
    F --> G[Document is searchable]
```

The current chunking implementation uses `cl100k_base` tokenization with
a default chunk size of **800 tokens** and **100-token overlap**. Pages
are chunked independently to preserve straightforward page citations.
This can create small chunks at page boundaries and may separate context
spanning two pages; a more advanced splitter can be considered after
measuring retrieval quality.

The embedding model is `sentence-transformers/all-MiniLM-L6-v2`. Its
vectors have **384 dimensions**, so the database column is defined as
`VECTOR(384)`. The same embedding model must be used for document chunks
and user questions.

### 2. Retrieval and answer generation

``` mermaid
sequenceDiagram
    participant B as Browser (React)
    participant A as FastAPI
    participant P as PostgreSQL + pgvector
    participant L as OpenRouter LLM

    B->>A: POST /ask/stream (question, top_k)
    A->>A: Embed question
    A->>P: Similarity search
    P-->>A: Top-k chunks + page metadata
    A->>L: Question + retrieved context + instructions
    loop While model generates
        L-->>A: Text delta
        A-->>B: SSE token event
    end
    A-->>B: SSE sources event
    A-->>B: SSE done event
```

Retrieval currently uses cosine distance via pgvector's `<=>` operator
and returns the closest chunks. The default `top_k` is 8.

The model is instructed to: - Use only supplied context. - Cite sources
using identifiers such as `[S1]`. - Avoid following instructions found
inside document text. - State when the context does not contain enough
information.

Prompt instructions reduce risk but do **not** guarantee that every
answer is correct or that every citation is valid. Evaluation and
additional validation are still needed.

### 3. Streaming event format

The streaming endpoint uses SSE events with a blank line between events.
The current event types are:

-   `token`: a piece of answer text, for example
    `{"text":"The export pipeline..."}`.
-   `sources`: retrieved source metadata, for example
    `{"sources":[...]}`.
-   `done`: signals successful completion, typically with an empty JSON
    object.
-   `error`: signals a generation error, for example
    `{"message":"Answer generation failed"}`.

The React client reads the HTTP response body using a stream reader. It
must buffer incomplete data because network chunks do not necessarily
align with SSE event boundaries.

## Project structure

The following is a logical layout. Existing filenames may differ
slightly depending on how the project was created.

``` text
chat-with-your-documents/
├── backend/
│   ├── main.py                  # FastAPI routes
│   ├── chunking.py              # Token-window chunking
│   ├── document_processing.py   # Per-page chunk creation and metadata
│   ├── embeddings.py             # Sentence Transformers model
│   ├── database.py              # PostgreSQL connection
│   ├── ingestion.py             # Extract, embed and persist PDF chunks
│   ├── retrieval.py              # Vector similarity search
│   ├── llm_service.py            # LLM generation and SSE generation
│   ├── ingestion_worker.py       # Background job processor (if added)
│   ├── evaluate_retrieval.py     # Retrieval evaluation script
│   ├── evaluation_questions.json # 30-question evaluation dataset
│   ├── uploads/                  # Temporary uploads; do not commit files
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

If your current repository is flatter or uses different filenames, keep
the actual structure and update this section to match it.

## Prerequisites

Install or prepare:

-   Python 3.11 or another version supported by your installed
    dependencies.
-   Node.js and npm.
-   Docker Desktop or Docker Engine with Docker Compose.
-   An OpenRouter API key and access to the configured model.
-   Git (recommended).

The local embedding model downloads model files on first use, so the
first startup may take longer and requires network access.

## Local setup

Commands below assume the backend and frontend are in separate
directories. Adjust paths to match your repository.

### 1. Start PostgreSQL with pgvector

From the repository root, create or use `docker-compose.yml`:

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

Enable the vector extension:

``` sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Create the chunks table if your application does not already create it:

``` sql
CREATE TABLE IF NOT EXISTS chunks (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_name TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding VECTOR(384) NOT NULL,
    embedding_model TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (page_number > 0),
    CHECK (chunk_index >= 0)
);
```

If you implement background job tracking, also create the
`ingestion_jobs` table described in the background ingestion section of
the project code. Confirm the schema matches your actual implementation.

### 2. Configure the backend

Create and activate a Python virtual environment:

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

Install the dependencies used by the application:

``` bash
pip install fastapi "uvicorn[standard]" python-multipart \
  pymupdf tiktoken sentence-transformers "psycopg[binary]" \
  pgvector openai python-dotenv
```

Save a reproducible dependency list after checking that the application
starts:

``` bash
pip freeze > requirements.txt
```

Create `backend/.env`:

``` env
DATABASE_URL=postgresql://raguser:local_dev_password@localhost:5433/ragdb
OPENROUTER_API_KEY=replace_with_your_key
OPENROUTER_MODEL=openai/gpt-4o-mini
```

Use a model identifier supported by your OpenRouter account. The model
shown is a configurable example; availability and pricing may change.

Ensure the backend loads the environment file during local development,
for example:

``` python
from dotenv import load_dotenv

load_dotenv()
```

Start FastAPI using your actual module path:

``` bash
uvicorn main:app --reload --port 8000
```

If `main.py` is inside a package or another directory, run Uvicorn with
the correct import path. Open `http://localhost:8000/docs` to inspect
the API.

### 3. Configure the frontend

In a separate terminal:

``` bash
cd frontend
npm install
```

Create `frontend/.env`:

``` env
VITE_API_URL=http://localhost:8000
```

Run the frontend:

``` bash
npm run dev
```

Open the URL printed by Vite, typically `http://localhost:5173`.

The FastAPI CORS configuration must allow that exact development origin.
For local development:

``` python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
```

Do not expose API secrets through `VITE_*` environment variables;
frontend variables are bundled into client-side code.

## Configuration

  -----------------------------------------------------------------------
  Variable                Used by                 Description
  ----------------------- ----------------------- -----------------------
  `DATABASE_URL`          Backend                 PostgreSQL connection
                                                  string

  `OPENROUTER_API_KEY`    Backend                 Secret key for the LLM
                                                  gateway

  `OPENROUTER_MODEL`      Backend                 Model identifier to
                                                  request from OpenRouter

  `VITE_API_URL`          Frontend                Base URL of the FastAPI
                                                  backend
  -----------------------------------------------------------------------

Keep real credentials in local environment files or a secrets manager.
Commit a `.env.example` with placeholder values if helpful, but never
commit `.env`.

## API endpoints

Check `http://localhost:8000/docs` for the authoritative list exposed by
the running application. The table below describes the endpoints
developed or discussed during this project; verify exact request and
response schemas against your current code.

  ----------------------------------------------------------------------------
  Method                  Endpoint                     Purpose
  ----------------------- ---------------------------- -----------------------
  `GET`                   `/health`                    Check that the API is
                                                       running

  `POST`                  `/documents/extract`         Extract text from an
                                                       uploaded PDF for
                                                       inspection

  `POST`                  `/documents/ingest`          Ingest a PDF; may be
                                                       synchronous in an
                                                       earlier version or
                                                       return a job ID in the
                                                       background-job version

  `GET`                   `/documents/jobs/{job_id}`   Check ingestion job
                                                       status, if background
                                                       job tracking is
                                                       implemented

  `POST`                  `/search`                    Return semantically
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

The `-N` option disables curl's output buffering so streamed events are
easier to observe.

## Data model

### `chunks`

  -----------------------------------------------------------------------
  Column                              Meaning
  ----------------------------------- -----------------------------------
  `id`                                Database-generated row identifier

  `document_name`                     Original document name used for
                                      display and basic filtering

  `page_number`                       One-based page number for citations

  `chunk_index`                       Chunk index within a page/document
                                      according to the ingestion
                                      implementation

  `text`                              Text supplied to retrieval and the
                                      LLM

  `embedding`                         384-dimensional vector generated by
                                      the configured embedding model

  `embedding_model`                   Model identifier used to create the
                                      vector

  `created_at`                        Row creation timestamp
  -----------------------------------------------------------------------

### `ingestion_jobs` (when background ingestion is enabled)

The proposed job table tracks a UUID, document name, status, error
message, and timestamps. The intended states are `queued`, `processing`,
`completed`, and `failed`.

A job-status row is not, by itself, a durable queue. A production worker
must recover queued or abandoned jobs after restarts and avoid
processing the same job unsafely more than once.

## Evaluation

A 30-question dataset was created from a resume PDF to check whether
retrieval returns a chunk containing an expected answer term. The
reported result was:

-   Questions: 30
-   Hits: 22
-   Misses: 8
-   Keyword-proxy hit rate: 73.3%

This is an initial diagnostic metric, **not a rigorous measure of answer
correctness**. The current evaluation checks for an expected
document/page and at least one matching expected term in a retrieved
result. Because the resume is a one-page document, page matching
provides little discrimination.

Recommended next evaluation improvements:

1.  Inspect each missed question and its top retrieved chunks.
2.  Add expected supporting chunk IDs or stronger evidence annotations.
3.  Measure Recall@k using labeled relevant chunks.
4.  Evaluate answer correctness and citation support separately from
    retrieval.
5.  Include questions whose answers are absent from the document to test
    abstention.
6.  Track latency and token/cost usage when comparing models or
    retrieval settings.

Do not treat similarity scores as probabilities that an answer is
correct.

## Troubleshooting

### PostgreSQL connection fails

-   Check `docker compose ps`.
-   Confirm the container is healthy.
-   Confirm the host port is `5433` when using the Compose mapping
    above.
-   Verify `DATABASE_URL` matches the configured database, username,
    password, and port.

### `vector` type or extension is missing

Connect to the target database and run:

``` sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Make sure the database uses the pgvector-enabled image, not a plain
PostgreSQL image.

### Embedding dimension mismatch

The current schema expects `VECTOR(384)`. The stored document embeddings
and query embeddings must come from a compatible model with the same
dimension. Changing embedding models may require re-embedding all stored
chunks.

### OpenRouter request fails

-   Verify `OPENROUTER_API_KEY` is loaded in the backend process.
-   Check that `OPENROUTER_MODEL` is a supported model identifier.
-   Inspect the backend logs for provider errors.
-   Never send the API key to React or expose it in browser logs.

### Browser reports a CORS error

-   Check the exact frontend origin in the browser address bar.
-   Add that origin to FastAPI's CORS allowlist.
-   Restart FastAPI after changing middleware configuration.

### Streaming appears only at the end

-   Confirm the response is `text/event-stream`.
-   Check the browser Network tab and console.
-   Ensure the frontend parses complete SSE events separated by blank
    lines; network chunks may split an event.
-   Verify the frontend processes `token` events as they arrive and the
    React state update appends to the existing assistant message.
-   Check for buffering in any reverse proxy used in deployment.

### Search returns no useful chunks

-   Confirm the ingestion job completed and rows exist in `chunks`.
-   Inspect stored text and verify it isn't empty.
-   Check the embedding model identifier and vector dimensions.
-   Inspect the top retrieved chunks for the query before changing
    models.
-   Use the evaluation dataset to measure changes rather than judging
    only a single question.

## Security and production considerations

Before exposing this application to other users or uploading sensitive
documents:

-   **Authentication and authorization:** authenticate users and enforce
    document-level access controls in every retrieval query. Do not rely
    on frontend filtering.
-   **Isolation:** associate documents and chunks with a stable document
    ID and owner/tenant ID. Filter retrieval by the caller's authorized
    documents.
-   **File validation:** verify PDF content, enforce size and page
    limits, consider malware scanning, and use generated storage paths
    rather than trusting filenames.
-   **Secrets:** keep API keys and database credentials on the server
    and use a secrets manager in production.
-   **Prompt injection:** treat retrieved document text as untrusted
    input. Prompt instructions help but are not a security boundary.
-   **Safe errors:** return generic errors to clients and log detailed
    exceptions securely on the server.
-   **Resource limits:** bound upload size, embedding batch size,
    request duration, and LLM context length.
-   **Durable jobs:** replace in-process background tasks with a durable
    queue/worker arrangement when reliability matters.
-   **Observability:** log request IDs, job IDs, durations, retrieval
    counts, model identifiers, and errors without logging secrets or
    unnecessarily sensitive document contents.
-   **Retention and deletion:** provide a policy and implementation for
    deleting documents, chunks, embeddings, temporary files, and related
    job metadata.
-   **Citations:** validate source IDs against retrieved chunks and
    evaluate citation support; an LLM-generated citation alone is not
    proof.
-   **Database operations:** use migrations, backups, least-privilege
    credentials, and appropriate connection pooling before production
    deployment.

## Roadmap

-   [x] Extract text from PDFs.
-   [x] Chunk text and generate embeddings.
-   [x] Store chunks and vectors in PostgreSQL/pgvector.
-   [x] Retrieve top-k similar chunks.
-   [x] Generate context-grounded LLM responses.
-   [x] Stream answer text with SSE.
-   [x] Build a React chat UI and fix incremental rendering.
-   [ ] Verify end-to-end PDF upload from React.
-   [ ] Complete and test background ingestion/job polling.
-   [ ] Add document IDs, ownership, authentication, and access-aware
    retrieval.
-   [ ] Add reliable worker retries and recovery.
-   [ ] Improve retrieval and answer/citation evaluation.
-   [ ] Add PDF page preview and clickable source citations.
-   [ ] Add automated tests, CI, logging, and production deployment
    configuration.

## Contributing

For local changes:

1.  Create a feature branch.
2.  Keep configuration secrets in environment variables.
3.  Test backend endpoints and frontend behavior.
4.  Update this README when routes, schemas, environment variables, or
    architecture change.
5.  Do not commit private PDFs, temporary uploads, credentials, `.venv`,
    `node_modules`, or generated secrets.

## License

No license has been selected yet. Add a `LICENSE` file before
distributing or accepting external contributions, and choose terms
appropriate for the project.
