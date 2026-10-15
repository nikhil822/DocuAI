from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

model = SentenceTransformer(MODEL_NAME)

def embed_texts(texts: list[str]) -> list[list[float]]:
    vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)

    return vectors.tolist()

if __name__ == "__main__":
    # Example usage
    sample_texts = [
        "This is the first sample text.",
        "Here is another example of text to embed.",
        "Sentence embeddings are useful for many NLP tasks."
    ]

    embeddings = embed_texts(sample_texts)
    for sentence, vector in zip(sample_texts, embeddings):
        print(f"Text: {sentence}")
        print("Vector dimensions:", len(vector))
        print("First five numbers:", vector[:5])
        print()