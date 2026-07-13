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


def test_reingesting_same_file_replaces_not_duplicates(client):
    first = client.post("/api/ingest", files={"file": ("energy.md", SAMPLE, "text/markdown")}).json()
    second = client.post("/api/ingest", files={"file": ("energy.md", SAMPLE, "text/markdown")}).json()
    # Same content, same filename -> chunk count stays put (no duplicates).
    assert first["chunks_added"] == second["chunks_added"]
    assert second["total_chunks"] == second["chunks_added"]
    docs = client.get("/api/documents").json()
    assert len([d for d in docs["documents"] if d["source"] == "energy.md"]) == 1


def test_delete_single_document(client):
    client.post("/api/ingest", files={"file": ("energy.md", SAMPLE, "text/markdown")})
    client.post("/api/ingest", files={"file": ("other.md", b"# Other\n\nUnrelated text.", "text/markdown")})

    r = client.delete("/api/documents/energy.md")
    assert r.status_code == 200
    sources = [d["source"] for d in client.get("/api/documents").json()["documents"]]
    assert sources == ["other.md"]

    # Deleting a document that isn't indexed is a 404.
    assert client.delete("/api/documents/nope.md").status_code == 404


def test_clear_documents(client):
    client.post("/api/ingest", files={"file": ("energy.md", SAMPLE, "text/markdown")})
    assert client.delete("/api/documents").status_code == 200
    assert client.get("/api/documents").json()["total_chunks"] == 0


def test_per_chat_collection_scoping(client):
    # Upload the same-topic docs into two separate chats.
    client.post(
        "/api/ingest",
        files={"file": ("solar.md", SAMPLE, "text/markdown")},
        data={"collection": "chatA"},
    )
    client.post(
        "/api/ingest",
        files={"file": ("wind.md", b"# Wind\n\nWind turbines make power.", "text/markdown")},
        data={"collection": "chatB"},
    )

    # Each chat only lists its own document.
    a_docs = [d["source"] for d in client.get("/api/documents", params={"collection": "chatA"}).json()["documents"]]
    b_docs = [d["source"] for d in client.get("/api/documents", params={"collection": "chatB"}).json()["documents"]]
    assert a_docs == ["solar.md"]
    assert b_docs == ["wind.md"]

    # A query scoped to chatA only cites chatA's document.
    result = client.post(
        "/api/query", json={"question": "How do solar panels work?", "collection": "chatA"}
    ).json()
    assert result["citations"]
    assert {c["source"] for c in result["citations"]} == {"solar.md"}

    # A chat with no documents answers gracefully.
    empty = client.post("/api/query", json={"question": "anything?", "collection": "chatZ"}).json()
    assert empty["citations"] == []

    # Deleting is scoped to the chat.
    assert client.delete("/api/documents/solar.md", params={"collection": "chatA"}).status_code == 200
    assert client.get("/api/documents", params={"collection": "chatA"}).json()["documents"] == []
    assert [d["source"] for d in client.get("/api/documents", params={"collection": "chatB"}).json()["documents"]] == ["wind.md"]


def test_email_signup_verification_flow(client):
    # No SMTP configured in tests -> the demo code is returned by /start.
    start = client.post("/api/auth/signup/start", json={"email": "New.Person@Example.com", "name": ""})
    assert start.status_code == 200, start.text
    body = start.json()
    assert body["ok"] and body["delivered"] is False
    token, code = body["token"], body["demo_code"]

    # A wrong code is rejected.
    assert client.post("/api/auth/signup/verify", json={"token": token, "code": "000000"}).status_code == 400

    # The right code creates a session; the name defaults to "Test" when omitted.
    ok = client.post("/api/auth/signup/verify", json={"token": token, "code": code})
    assert ok.status_code == 200, ok.text
    assert ok.json()["email"] == "new.person@example.com"
    assert ok.json()["name"] == "Test"

    # The session cookie now authenticates /me.
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "new.person@example.com"


def test_signup_start_rejects_bad_email(client):
    r = client.post("/api/auth/signup/start", json={"email": "not-an-email", "name": "X"})
    assert r.status_code == 400
