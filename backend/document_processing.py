from chunking import chunk_text

def create_document_chunks(filename: str, pages: list[dict]) -> list[dict]:
    result = []

    for page in pages:
        page_number = page["page_number"]
        text = page["text"]
        if not text.strip():
            continue  # Skip empty pages

        chunks = chunk_text(text)

        for chunk_index, chunk in enumerate(chunks):
            result.append({
                "document_name": filename,
                "page_number": page_number,
                "chunk_index": chunk_index,
                "chunk_text": chunk,
            })
    return result