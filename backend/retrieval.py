# function takes a question, converts it to an embedding, and retrieves the top 8 most similar chunks from the database

from database import get_connection
from embeddings import embed_texts

def retrieve_chunks(question: str, top_k: int = 8):
    if not question.strip():
        raise ValueError("Question is empty")

    if not 1 <= top_k <= 50:
        raise ValueError("top_k must be between 1 and 50")

    query_vector = embed_texts([question])[0]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    document_name,
                    page_number,
                    chunk_index,
                    text,
                    1 - (embedding <=> %s) AS similarity
                FROM chunks
                WHERE embedding_model = %s
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (query_vector, "sentence-transformers/all-MiniLM-L6-v2", query_vector, top_k),
            )
            rows = cur.fetchall()

    return [
        {
            "document_name": row[0],
            "page_number": row[1],
            "chunk_index": row[2],
            "text": row[3],
            "similarity": float(row[4]),
        }
        for row in rows
    ]