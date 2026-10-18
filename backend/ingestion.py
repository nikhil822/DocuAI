import hashlib

import fitz

from chunking import chunk_text
from embeddings import embed_texts
from database import get_connection

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

def ingest_pdf(filename: str, pdf_bytes: bytes) -> dict:
    """Extract, chunk, embed and store a pdf"""

    if not pdf_bytes:
        raise ValueError("PDF is empty")

    # extract text
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        pages = [
            {
                "page_number": index + 1,
                "text": page.get_text("text").strip(),
            }
            for index, page in enumerate(pdf)
        ]

    # create chunks
    chunks = []
    for page in pages:
        if not page["text"]:
            continue

        for index, text in enumerate(chunk_text(page["text"])):
            chunks.append(
                {
                    "page_number": page["page_number"],
                    "chunk_index": index,
                    "text": text,
                }
            )

    if not chunks:
        raise ValueError("No text found in PDF")

    # generate embeddings
    vectors = embed_texts([chunk["text"] for chunk in chunks])

    # create stable document id from pdf's content
    document_id = hashlib.sha256(pdf_bytes).hexdigest()

    # store the chunks and embeddings in one transaction
    with get_connection() as conn:
        with conn.cursor() as cur:
            # delete any existing chunks for this document
            cur.execute(
                "DELETE FROM chunks WHERE document_name = %s", (document_id,)
            )

            # insert new chunks
            for chunk, vector in zip(chunks, vectors):
                cur.execute(
                    """
                    INSERT INTO chunks (
                        document_name,
                        page_number,
                        chunk_index,
                        text,
                        embedding,
                        embedding_model
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        document_id,
                        chunk["page_number"],
                        chunk["chunk_index"],
                        chunk["text"],
                        vector,
                        MODEL_NAME,
                    ),
                )

    return {
        "document_id": document_id,
        "filename": filename,
        "total_pages": len(pages),
        "indexed_chunks": len(chunks),
    }