
from chunking import chunk_text


def test_short_text():
    text = "A redemption request must be processed within two business days."
    chunks = chunk_text(text)

    assert len(chunks) == 1
    assert chunks[0] == text


def test_empty_text():
    assert chunk_text("") == []


def test_large_text():
    text = " ".join(["redemption"] * 2000)
    chunks = chunk_text(text)

    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)


if __name__ == "__main__":
    test_short_text()
    test_empty_text()
    test_large_text()
    print("All chunking tests passed!")
