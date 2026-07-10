import numpy as np

from app.core.embeddings import HashingEmbeddings
from app.core.vectorstore import NumpyVectorStore, Record


def _records(texts):
    return [Record(id=str(i), text=t, source="doc.md", chunk_index=i) for i, t in enumerate(texts)]


def test_search_ranks_semantically_closest_chunk_first(tmp_path):
    embedder = HashingEmbeddings(dim=256)
    store = NumpyVectorStore(tmp_path / "index")

    texts = [
        "Python is a popular programming language for data science.",
        "The Eiffel Tower is a landmark located in Paris, France.",
        "Neural networks are the foundation of modern deep learning.",
    ]
    store.add(_records(texts), embedder.embed_documents(texts))

    results = store.search(embedder.embed_query("deep learning neural network"), k=2)
    assert results
    assert results[0].record.text == texts[2]
    # Similarity scores should be sorted descending.
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_persistence_survives_reload(tmp_path):
    embedder = HashingEmbeddings(dim=64)
    index_dir = tmp_path / "index"

    store = NumpyVectorStore(index_dir)
    texts = ["first chunk", "second chunk"]
    store.add(_records(texts), embedder.embed_documents(texts))
    assert store.count() == 2

    # A brand-new instance should load the persisted index from disk.
    reloaded = NumpyVectorStore(index_dir)
    assert reloaded.count() == 2
    assert reloaded.documents() == {"doc.md": 2}


def test_clear_empties_the_index(tmp_path):
    embedder = HashingEmbeddings(dim=32)
    store = NumpyVectorStore(tmp_path / "index")
    store.add(_records(["a", "b"]), embedder.embed_documents(["a", "b"]))
    store.clear()
    assert store.count() == 0
    assert store.search(np.zeros(32, dtype=np.float32), k=3) == []


def test_search_on_empty_store_returns_empty(tmp_path):
    store = NumpyVectorStore(tmp_path / "index")
    assert store.search(np.zeros(8, dtype=np.float32), k=5) == []


def test_remove_document_deletes_only_that_source(tmp_path):
    embedder = HashingEmbeddings(dim=64)
    store = NumpyVectorStore(tmp_path / "index")

    a = [Record(id=f"a{i}", text=t, source="a.md", chunk_index=i) for i, t in enumerate(["one", "two"])]
    b = [Record(id="b0", text="three", source="b.md", chunk_index=0)]
    store.add(a, embedder.embed_documents(["one", "two"]))
    store.add(b, embedder.embed_documents(["three"]))
    assert store.count() == 3

    removed = store.remove_document("a.md")
    assert removed == 2
    assert store.documents() == {"b.md": 1}
    # Search still works on the remaining document.
    results = store.search(embedder.embed_query("three"), k=3)
    assert results and results[0].record.source == "b.md"
