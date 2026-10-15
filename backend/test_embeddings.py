
import numpy as np
from embeddings import embed_texts


sentences = [
    "How do I process a delayed redemption request?",
    "What should we do when a withdrawal request is late?",
    "What is the office Wi-Fi password?",
]

vectors = np.array(embed_texts(sentences))

similarity_12 = float(vectors[0] @ vectors[1])
similarity_13 = float(vectors[0] @ vectors[2])

print("Similar redemption questions:", round(similarity_12, 4))
print("Redemption vs Wi-Fi question:", round(similarity_13, 4))

assert similarity_12 > similarity_13

print("Similarity test passed!")
