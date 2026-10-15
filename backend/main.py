import fitz
from fastapi import FastAPI, File, UploadFile, HTTPException

app = FastAPI(
    title="DocuAI",
    description="A RAG service for PDF question answering",
    version="0.1.0",
)

@app.get("/health")
def health_check():
    return {"status": "ok"}

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
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(exc)}")

    return {
        "filename": file.filename,
        "num_pages": len(pages),
        "pages": pages,
    }