// RAG Knowledge Assistant — front-end logic (no framework, no build step).
const $ = (sel) => document.querySelector(sel);

const els = {
  messages: $("#messages"),
  composer: $("#composer"),
  question: $("#question"),
  sendBtn: $("#send-btn"),
  fileInput: $("#file-input"),
  dropzone: $("#dropzone"),
  uploadStatus: $("#upload-status"),
  docList: $("#doc-list"),
  clearBtn: $("#clear-btn"),
  statusDot: $("#status-dot"),
  statusText: $("#status-text"),
  modeLine: $("#mode-line"),
  suggestions: $("#suggestions"),
};

const SUGGESTIONS = [
  "What is this document about?",
  "Summarize the key points.",
  "What are the main benefits?",
];

// --- helpers ---------------------------------------------------------------
function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function scrollToBottom() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

function clearEmptyState() {
  const empty = els.messages.querySelector(".empty-state");
  if (empty) empty.remove();
}

function addMessage(role, text) {
  clearEmptyState();
  const msg = document.createElement("div");
  msg.className = `msg ${role}`;
  msg.innerHTML = `
    <div class="avatar">${role === "user" ? "🧑" : "📚"}</div>
    <div class="bubble"></div>`;
  const bubble = msg.querySelector(".bubble");
  bubble.textContent = text || "";
  els.messages.appendChild(msg);
  scrollToBottom();
  return bubble;
}

function renderCitations(bubble, citations) {
  if (!citations || !citations.length) return;
  const wrap = document.createElement("div");
  wrap.className = "citations";
  wrap.innerHTML = `<div class="citations-title">Sources</div>`;
  citations.forEach((c) => {
    const row = document.createElement("div");
    row.className = "citation";
    row.title = c.snippet;
    row.innerHTML = `
      <span class="cnum">[${c.marker}]</span>
      <span><span class="csrc">${escapeHtml(c.source)}</span>
        · chunk ${c.chunk_index} — ${escapeHtml(c.snippet)}</span>
      <span class="cscore">${c.score.toFixed(3)}</span>`;
    wrap.appendChild(row);
  });
  bubble.appendChild(wrap);
  scrollToBottom();
}

// --- API -------------------------------------------------------------------
async function refreshHealth() {
  try {
    const r = await fetch("/api/health");
    const h = await r.json();
    els.statusDot.classList.add("online");
    els.statusText.textContent = `${h.chunks} chunks · ${h.documents} docs`;
    els.modeLine.textContent =
      `embeddings: ${h.embedding_provider} · llm: ${h.llm_provider} (${h.model})`;
  } catch {
    els.statusText.textContent = "offline";
  }
}

async function refreshDocuments() {
  try {
    const r = await fetch("/api/documents");
    const data = await r.json();
    if (!data.documents.length) {
      els.docList.innerHTML = `<li class="doc-empty">No documents yet.</li>`;
      return;
    }
    els.docList.innerHTML = data.documents
      .map(
        (d) =>
          `<li><span class="doc-name" title="${escapeHtml(d.source)}">${escapeHtml(
            d.source
          )}</span><span class="doc-count">${d.chunks}</span></li>`
      )
      .join("");
  } catch {
    /* ignore */
  }
}

async function uploadFile(file) {
  els.uploadStatus.className = "upload-status";
  els.uploadStatus.textContent = `Uploading ${file.name}…`;
  const form = new FormData();
  form.append("file", file);
  try {
    const r = await fetch("/api/ingest", { method: "POST", body: form });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Upload failed");
    els.uploadStatus.className = "upload-status ok";
    els.uploadStatus.textContent = `✓ ${data.message}`;
    refreshDocuments();
    refreshHealth();
  } catch (e) {
    els.uploadStatus.className = "upload-status err";
    els.uploadStatus.textContent = `✕ ${e.message}`;
  }
}

async function ask(question) {
  addMessage("user", question);
  const bubble = addMessage("assistant", "");
  const cursor = document.createElement("span");
  cursor.className = "cursor";
  bubble.appendChild(cursor);

  els.sendBtn.disabled = true;
  let answer = "";
  let citations = [];

  try {
    const resp = await fetch("/api/query/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!resp.ok || !resp.body) throw new Error("Request failed");

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split("\n\n");
      buffer = events.pop() || "";
      for (const block of events) {
        const evMatch = block.match(/^event: (.+)$/m);
        const dataMatch = block.match(/^data: (.+)$/m);
        if (!evMatch || !dataMatch) continue;
        const type = evMatch[1];
        const data = JSON.parse(dataMatch[1]);
        if (type === "citations") {
          citations = data.citations;
        } else if (type === "token") {
          answer += data.text;
          bubble.textContent = answer;
          bubble.appendChild(cursor);
          scrollToBottom();
        }
      }
    }
  } catch (e) {
    answer = `⚠️ ${e.message}`;
    bubble.textContent = answer;
  } finally {
    cursor.remove();
    bubble.textContent = answer;
    renderCitations(bubble, citations);
    els.sendBtn.disabled = false;
    refreshHealth();
  }
}

// --- events ----------------------------------------------------------------
els.composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = els.question.value.trim();
  if (!q) return;
  els.question.value = "";
  els.question.style.height = "auto";
  ask(q);
});

els.question.addEventListener("input", () => {
  els.question.style.height = "auto";
  els.question.style.height = Math.min(els.question.scrollHeight, 160) + "px";
});
els.question.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    els.composer.requestSubmit();
  }
});

els.fileInput.addEventListener("change", () => {
  if (els.fileInput.files[0]) uploadFile(els.fileInput.files[0]);
});

["dragover", "dragenter"].forEach((evt) =>
  els.dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    els.dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((evt) =>
  els.dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    els.dropzone.classList.remove("dragover");
  })
);
els.dropzone.addEventListener("drop", (e) => {
  if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]);
});

els.clearBtn.addEventListener("click", async () => {
  if (!confirm("Clear all indexed documents?")) return;
  await fetch("/api/documents", { method: "DELETE" });
  refreshDocuments();
  refreshHealth();
});

function renderSuggestions() {
  els.suggestions.innerHTML = "";
  SUGGESTIONS.forEach((s) => {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.textContent = s;
    chip.onclick = () => ask(s);
    els.suggestions.appendChild(chip);
  });
}

// --- init ------------------------------------------------------------------
renderSuggestions();
refreshHealth();
refreshDocuments();
setInterval(refreshHealth, 15000);
