import fitz
from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel
from retrieval import retrieve_chunks
from ingestion import ingest_pdf

app = FastAPI(
    title="DocuAI",
    description="A RAG service for PDF question answering",
    version="0.1.0",
)

class SearchRequest(BaseModel):
    question: str
    top_k: int = 8

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/documents/ingest")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a PDF file.")
        
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = ingest_pdf(file.filename, pdf_bytes)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error ingesting PDF{str(exc)}") from exc

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