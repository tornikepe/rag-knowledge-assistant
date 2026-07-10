"""End-to-end API tests through FastAPI's TestClient (offline providers)."""

SAMPLE = (
    b"# Solar Power\n\n"
    b"Solar panels convert sunlight into electricity using photovoltaic cells. "
    b"They reduce electricity bills and lower carbon emissions.\n\n"
    b"# Wind Power\n\n"
    b"Wind turbines capture kinetic energy from moving air and convert it to power. "
    b"Wind farms are often built offshore where wind is stronger."
)


def test_health_reports_offline_providers(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["embedding_provider"] == "hash"
    assert body["llm_provider"] == "echo"
    assert body["chunks"] == 0


def test_ingest_then_query_flow(client):
    # Ingest a document.
    r = client.post(
        "/api/ingest",
        files={"file": ("energy.md", SAMPLE, "text/markdown")},
    )
    assert r.status_code == 200, r.text
    ingest = r.json()
    assert ingest["chunks_added"] >= 1

    # It should now show up in the document list.
    docs = client.get("/api/documents").json()
    assert any(d["source"] == "energy.md" for d in docs["documents"])

    # Query it — the echo LLM returns a grounded, cited answer.
    r = client.post("/api/query", json={"question": "How do solar panels work?"})
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["citations"], "expected at least one citation"
    assert "[1]" in result["answer"]
    assert result["citations"][0]["source"] == "energy.md"


def test_query_without_documents_is_graceful(client):
    r = client.post("/api/query", json={"question": "anything?"})
    assert r.status_code == 200
    assert r.json()["citations"] == []


def test_streaming_endpoint_emits_sse_events(client):
    client.post("/api/ingest", files={"file": ("energy.md", SAMPLE, "text/markdown")})
    with client.stream(
        "POST", "/api/query/stream", json={"question": "What is wind power?"}
    ) as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())
    assert "event: citations" in body
    assert "event: token" in body
    assert "event: done" in body


def test_unsupported_file_type_is_rejected(client):
    r = client.post(
        "/api/ingest",
        files={"file": ("photo.png", b"\x89PNG\r\n", "image/png")},
    )
    assert r.status_code == 415


def test_clear_documents(client):
    client.post("/api/ingest", files={"file": ("energy.md", SAMPLE, "text/markdown")})
    assert client.delete("/api/documents").status_code == 200
    assert client.get("/api/documents").json()["total_chunks"] == 0
