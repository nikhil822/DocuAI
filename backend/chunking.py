import tiktoken

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer.")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be a non-negative integer less than chunk_size.")

    text = text.strip()
    if not text:
        return []

    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)
    chunks = []
    step = chunk_size - overlap

    for start in range(0, len(tokens), step):
        token_slice = tokens[start:start + chunk_size]

        if not token_slice:
            break
        chunk = encoding.decode(token_slice).strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(tokens):
            break

    return chunks