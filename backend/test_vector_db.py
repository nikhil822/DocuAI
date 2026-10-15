
from embeddings import embed_texts
from database import get_connection
from pgvector import Vector


sentences = [
    "How do I handle a delayed redemption request?",
    "What should we do when a withdrawal is late?",
    "How do I reset my office Wi-Fi password?",
]

vectors = embed_texts(sentences)

with get_connection() as conn:
    with conn.cursor() as cur:
        # Insert test vectors using the real embedding model.
        cur.execute("DELETE FROM chunks WHERE document_name = %s", ("demo.pdf",))
        print("vectors", vectors)
        for i, (sentence, vector) in enumerate(zip(sentences, vectors)):
            print(f"Inserting vector for sentence: {sentence}")
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
                    "demo.pdf",
                    i + 1,
                    0,
                    sentence,
                    vector,
                    "sentence-transformers/all-MiniLM-L6-v2",
                ),
            )

        question = "What should I do if redemption is delayed?"
        query_vector = Vector(embed_texts([question])[0])

        cur.execute(
            """
            SELECT
                document_name,
                page_number,
                text,
                1 - (embedding <=> %s) AS similarity
            FROM chunks
            ORDER BY embedding <=> %s
            LIMIT 3
            """,
            (query_vector, query_vector),
        )

        for doc, page, text, score in cur.fetchall():
            print(f"{doc}, page {page}, score={score:.4f}")
            print(text)
            print()
