import fitz
import json
import uuid
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from database import get_connection
from ingestion_worker import process_ingestion_job
from pydantic import BaseModel, Field
from retrieval import retrieve_chunks
from ingestion import ingest_pdf
from llm_service import generate_answer
from fastapi.responses import StreamingResponse
from llm_service import generate_answer_stream
from fastapi.middleware.cors import CORSMiddleware

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB

app = FastAPI(
    title="DocuAI",
    description="A RAG service for PDF question answering",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

class SearchRequest(BaseModel):
    question: str
    top_k: int = 8

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=8, ge=1, le=50)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/documents/ingest", status_code=202)
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a PDF file.")
        
    document_name = Path(file.filename).name
    job_id = str(uuid.uuid4())
    upload_path = UPLOAD_DIR / f"{job_id}.pdf"

    total_size = 0

    try:
        with upload_path.open("wb") as f:
            while True:
                data = await file.read(1024 * 1024)
                if not data:
                    break
                total_size += len(data)
                if total_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=400, detail="File size exceeds the maximum limit of 25 MB.")
                f.write(data)

        if total_size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ingestion_jobs (id, document_name)
                    VALUES (%s, %s)
                    """,
                    (job_id, document_name),
                )

        background_tasks.add_task(process_ingestion_job, job_id, str(upload_path), document_name)
        return {
            "job_id": job_id,
            "document_name": document_name,
            "status": "queued",
            "status_url": f"/documents/jobs/{job_id}"
        }
    except ValueError as ve:
        upload_path.unlink(missing_ok=True)
        raise
    except Exception:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Error ingesting PDF") from None
    finally:
        await file.close()

@app.post("/search")
def search_documents(request: SearchRequest):
    try:
        results = retrieve_chunks(request.question, request.top_k)
        return {
            "question": request.question,
            "results": results
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Document search failed:{str(exc)}") from exc

@app.post("/documents/extract")
async def extract_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a PDF file.")
        
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
            pages = []

            for page_index, page in enumerate(pdf):
                pages.append({
                    "page_number": page_index + 1,
                    "text": page.get_text("text").strip(),
                })
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Error processing PDF") from exc

    return {
        "filename": file.filename,
        "num_pages": len(pages),
        "pages": pages,
    }

@app.post("/ask")
async def ask_question(request: AskRequest):
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        # retrieve relevant chunks from the database
        chunks = retrieve_chunks(question=question, top_k=request.top_k)

        # generate an answer
        result = await generate_answer(question=question, chunks=chunks)
        return result

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(exc)}") from exc

@app.post("/ask/stream")
async def ask_question_stream(request: AskRequest):
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        chunks = retrieve_chunks(question=question, top_k=request.top_k)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def event_generator():
        try:
            async for event in generate_answer_stream(question=question, chunks=chunks):
                yield event
        except Exception as exc:
            yield (
                "event: error\n"
                f"data: {json.dumps({'message': 'Answer generation failed'})}\n\n" 
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/documents/jobs/{job_id}")
def get_ingestion_job(job_id: uuid.UUID):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, document_name, status, error_message, created_at, started_at, completed_at FROM ingestion_jobs WHERE id = %s
""", (job_id,)
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found.")

    return {
        "job_id": str(row[0]),
        "document_name": row[1],
        "status": row[2],
        "error": row[3],
        "created_at": row[4],
        "started_at": row[5],
        "completed_at": row[6],
    }
