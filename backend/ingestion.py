import hashlib
import uuid
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

    content_hash = hashlib.sha256(pdf_bytes).hexdigest()
    document_id = uuid.uuid4()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (id, filename, content_hash)
                VALUES (%s, %s, %s)
                ON CONFLICT (filename)
                DO UPDATE SET
                    content_hash = EXCLUDED.content_hash,
                    updated_at = NOW()
                RETURNING id
                """,
                (document_id, filename, content_hash),
            )
            document_id = cur.fetchone()[0]

            #replace old chunks only for this doc
            cur.execute(
                "DELETE FROM chunks WHERE document_id = %s",
                (document_id,),
            )

            for chunk, vector in zip(chunks, vectors):
                cur.execute(
                    """
                    INSERT INTO chunks (
                        document_id,
                        document_name,
                        page_number,
                        chunk_index,
                        text,
                        embedding,
                        embedding_model
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        document_id,
                        filename,
                        chunk["page_number"],
                        chunk["chunk_index"],
                        chunk["text"],
                        vector,
                        MODEL_NAME,
                    ),
                )

    return {
        "document_id": str(document_id),
        "filename": filename,
        "total_pages": len(pages),
        "indexed_chunks": len(chunks),
    }
