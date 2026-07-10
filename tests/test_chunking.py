from app.core.chunking import chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_short_text_is_single_chunk():
    chunks = chunk_text("A short sentence.", chunk_size=300, overlap=40)
    assert chunks == ["A short sentence."]


def test_chunks_respect_size_budget():
    text = " ".join(f"word{i}" for i in range(400))
    chunks = chunk_text(text, chunk_size=200, overlap=20)
    assert len(chunks) > 1
    # Allow a little slack for the prepended overlap tail.
    assert all(len(c) <= 200 + 40 for c in chunks)


def test_overlap_carries_context_between_chunks():
    text = ("Alpha paragraph about cats.\n\n" * 4) + ("Beta paragraph about dogs.\n\n" * 4)
    chunks = chunk_text(text, chunk_size=120, overlap=30)
    assert len(chunks) >= 2
    # The tail of chunk n should reappear at the head of chunk n+1.
    assert chunks[1].startswith(chunks[0][-30:].lstrip()[:10])


def test_overlap_must_be_smaller_than_chunk_size():
    import pytest

    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size=100, overlap=100)
