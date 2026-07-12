/* ============================================================
   Peit — single-page app (router + auth + landing + chat)
   No framework, no build step.

   NOTE: authentication + chat history are client-side (localStorage) so the
   live demo works with zero backend/database. The RAG endpoints (/api/*) are
   the real backend. See README for wiring a real auth + DB backend.
   ============================================================ */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// ---------- storage ----------
const store = {
  user: () => JSON.parse(localStorage.getItem("peit_user") || "null"),
  setUser: (u) => localStorage.setItem("peit_user", JSON.stringify(u)),
  clearUser: () => localStorage.removeItem("peit_user"),
  accounts: () => JSON.parse(localStorage.getItem("peit_accounts") || "{}"),
  setAccounts: (a) => localStorage.setItem("peit_accounts", JSON.stringify(a)),
  convos: (email) => JSON.parse(localStorage.getItem(`peit_convos_${email}`) || "[]"),
  setConvos: (email, c) => localStorage.setItem(`peit_convos_${email}`, JSON.stringify(c)),
};

const state = { currentConvoId: null, landingInit: false, appBound: false };

// ---------- helpers ----------
function escapeHtml(s) {
  return (s || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}
function initials(email) {
  return (email || "P").trim()[0].toUpperCase();
}

// ---------- tiny markdown renderer ----------
function renderMarkdown(src) {
  let text = (src || "").replace(/\r\n/g, "\n");
  const codeBlocks = [];
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_m, _l, code) => {
    codeBlocks.push(`<pre class="code"><code>${escapeHtml(code.replace(/\n$/, ""))}</code></pre>`);
    return ` CODE${codeBlocks.length - 1} `;
  });
  text = escapeHtml(text)
    .replace(/`([^`]+)`/g, (_m, c) => `<code>${c}</code>`)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>")
    .replace(/(^|[^_])_([^_\n]+)_(?!_)/g, "$1<em>$2</em>")
    .replace(/\[(\d+)\]/g, (_m, n) => `<sup class="cite" data-marker="${n}" title="Jump to source ${n}">${n}</sup>`);
  const lines = text.split("\n");
  const out = [];
  let para = [];
  const flush = () => { if (para.length) out.push(`<p>${para.join("<br>")}</p>`); para = []; };
  for (let i = 0; i < lines.length; ) {
    const line = lines[i].trim();
    const code = line.match(/^ CODE(\d+) $/);
    if (code) { flush(); out.push(codeBlocks[+code[1]]); i++; }
    else if (line === "") { flush(); i++; }
    else if (/^(#{1,6})\s+/.test(line)) { flush(); const m = line.match(/^(#{1,6})\s+(.*)$/); out.push(`<h${Math.min(m[1].length + 3, 6)}>${m[2]}</h${Math.min(m[1].length + 3, 6)}>`); i++; }
    else if (/^[-*]\s+/.test(line)) { flush(); const items = []; while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) { items.push(`<li>${lines[i].trim().replace(/^[-*]\s+/, "")}</li>`); i++; } out.push(`<ul>${items.join("")}</ul>`); }
    else if (/^\d+\.\s+/.test(line)) { flush(); const items = []; while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) { items.push(`<li>${lines[i].trim().replace(/^\d+\.\s+/, "")}</li>`); i++; } out.push(`<ol>${items.join("")}</ol>`); }
    else { para.push(line); i++; }
  }
  flush();
  return out.join("");
}

// ============================================================
//  ROUTER
// ============================================================
function showView(id) {
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === id));
  document.body.classList.toggle("in-app", id === "view-app");
  $(".app-sidebar")?.classList.remove("open");
  window.scrollTo(0, 0);
}

function router() {
  const hash = location.hash || "#/";
  const user = store.user();

  if (hash.startsWith("#/app")) {
    if (!user) { location.hash = "#/login"; return; }
    showView("view-app");
    initApp();
  } else if (hash === "#/login" || hash === "#/signup") {
    setAuthMode(hash === "#/signup" ? "signup" : "login");
    showView("view-auth");
  } else {
    showView("view-landing");
    initLanding();
    // anchor scrolling within landing
    if (hash.startsWith("#") && hash.length > 1 && !hash.startsWith("#/")) {
      const el = document.getElementById(hash.slice(1));
      if (el) setTimeout(() => el.scrollIntoView({ behavior: "smooth" }), 30);
    }
  }
}
window.addEventListener("hashchange", router);

// data-link anchors: let hash routing handle them naturally (no reload needed)

// ============================================================
//  LANDING
// ============================================================
function initLanding() {
  // The minimal landing animates purely in CSS (the aurora background) — nothing to init.
}

// ============================================================
//  AUTH
// ============================================================
function setAuthMode(mode) {
  const isSignup = mode === "signup";
  $("#auth-title").textContent = isSignup ? "Create your account" : "Welcome back";
  $("#auth-lead").textContent = isSignup
    ? "Start chatting with your documents in seconds."
    : "Log in to continue to your knowledge base.";
  $("#auth-submit").textContent = isSignup ? "Create account" : "Log in";
  $("#name-field").style.display = isSignup ? "" : "none";
  $("#auth-aside-title").textContent = isSignup ? "Chat with your documents." : "Welcome back to Peit.";
  $("#auth-error").textContent = "";
  $("#auth-switch").innerHTML = isSignup
    ? `Already have an account? <a data-goto="#/login">Log in</a>`
    : `New to Peit? <a data-goto="#/signup">Create an account</a>`;
  $("#auth-form").dataset.mode = mode;
}

function bindAuth() {
  $("#auth-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const mode = $("#auth-form").dataset.mode || "login";
    const name = $("#auth-name").value.trim();
    const email = $("#auth-email").value.trim().toLowerCase();
    const password = $("#auth-password").value;
    const err = $("#auth-error");
    err.textContent = "";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { err.textContent = "Enter a valid email address."; return; }
    if (password.length < 6) { err.textContent = "Password must be at least 6 characters."; return; }

    const accounts = store.accounts();
    if (mode === "signup") {
      if (accounts[email]) { err.textContent = "An account with this email already exists. Try logging in."; return; }
      accounts[email] = { name: name || email.split("@")[0], pass: btoa(password) };
      store.setAccounts(accounts);
      loginUser({ name: accounts[email].name, email });
    } else {
      const acc = accounts[email];
      if (!acc || acc.pass !== btoa(password)) { err.textContent = "Wrong email or password."; return; }
      loginUser({ name: acc.name, email });
    }
  });

  $("#auth-demo").addEventListener("click", () =>
    loginUser({ name: "Demo user", email: "demo@peit.app" })
  );

  // switch login/signup links (delegated)
  $("#view-auth").addEventListener("click", (e) => {
    const a = e.target.closest("[data-goto]");
    if (a) { e.preventDefault(); location.hash = a.dataset.goto; }
  });
}

function loginUser(user) {
  store.setUser(user);
  $("#auth-password").value = "";
  state.currentConvoId = null;
  location.hash = "#/app";
}

// ============================================================
//  APP / DASHBOARD
// ============================================================
function initApp() {
  const user = store.user();
  $("#user-email").textContent = user.email;
  $("#user-avatar").textContent = initials(user.email);

  if (!state.appBound) { bindApp(); state.appBound = true; }

  applyTheme(localStorage.getItem("peit_theme") || effectiveTheme());
  renderHistory();
  refreshDocuments();
  refreshHealth();

  // open the most recent conversation, or start fresh
  const convos = store.convos(user.email);
  if (!state.currentConvoId) {
    if (convos.length) selectChat(convos[0].id);
    else newChat();
  } else {
    renderMessages();
  }
}

function currentConvos() { return store.convos(store.user().email); }
function saveConvos(c) { store.setConvos(store.user().email, c); }

function newChat() {
  const c = currentConvos();
  const convo = { id: uid(), title: "New chat", messages: [], ts: Date.now() };
  c.unshift(convo);
  saveConvos(c);
  state.currentConvoId = convo.id;
  renderHistory();
  renderMessages();
  $("#question").focus();
}

function selectChat(id) {
  state.currentConvoId = id;
  renderHistory();
  renderMessages();
}

function deleteChat(id) {
  let c = currentConvos().filter((x) => x.id !== id);
  saveConvos(c);
  if (state.currentConvoId === id) {
    if (c.length) state.currentConvoId = c[0].id;
    else { newChat(); return; }
  }
  renderHistory();
  renderMessages();
}

function getConvo() {
  return currentConvos().find((c) => c.id === state.currentConvoId);
}

function renderHistory() {
  const list = $("#history-list");
  const convos = currentConvos();
  if (!convos.length) { list.innerHTML = `<li class="history-empty">No chats yet.</li>`; return; }
  list.innerHTML = "";
  convos.forEach((c) => {
    const li = document.createElement("li");
    li.className = "history-item" + (c.id === state.currentConvoId ? " active" : "");
    li.innerHTML = `<span class="hi-title">💬 ${escapeHtml(c.title)}</span><button class="hi-del" title="Delete">✕</button>`;
    li.querySelector(".hi-title").addEventListener("click", () => selectChat(c.id));
    li.querySelector(".hi-del").addEventListener("click", (e) => { e.stopPropagation(); deleteChat(c.id); });
    list.appendChild(li);
  });
}

const SUGGESTIONS = ["What is this document about?", "Summarize the key points.", "What are the best practices?"];

function renderMessages() {
  const box = $("#messages");
  const convo = getConvo();
  box.innerHTML = "";
  if (!convo || !convo.messages.length) {
    box.innerHTML = `
      <div class="app-empty">
        <div class="ae-mark">P</div>
        <h3>Ask anything about your documents</h3>
        <p>Peit answers only from your indexed sources, and cites them inline.</p>
        <div class="app-suggestions">${SUGGESTIONS.map((s) => `<button class="chip">${s}</button>`).join("")}</div>
      </div>`;
    $$("#messages .chip").forEach((c) => (c.onclick = () => ask(c.textContent)));
    return;
  }
  convo.messages.forEach((m) => {
    const msg = document.createElement("div");
    msg.className = `msg ${m.role}`;
    msg.innerHTML = `<div class="avatar">${m.role === "user" ? initials(store.user().email) : "P"}</div><div class="bubble"></div>`;
    const bubble = msg.querySelector(".bubble");
    if (m.role === "user") bubble.textContent = m.content;
    else {
      bubble.innerHTML = renderMarkdown(m.content);
      renderCitations(msg, m.citations || []);
      addCopyButton(bubble, m.content);
    }
    box.appendChild(msg);
  });
  box.scrollTop = box.scrollHeight;
}

function addMessageEl(role, text) {
  const box = $("#messages");
  box.querySelector(".app-empty")?.remove();
  const msg = document.createElement("div");
  msg.className = `msg ${role}`;
  msg.innerHTML = `<div class="avatar">${role === "user" ? initials(store.user().email) : "P"}</div><div class="bubble"></div>`;
  msg.querySelector(".bubble").textContent = text || "";
  box.appendChild(msg);
  box.scrollTop = box.scrollHeight;
  return msg;
}

function addCopyButton(bubble, text) {
  const btn = document.createElement("button");
  btn.className = "copy-btn";
  btn.textContent = "⧉";
  btn.title = "Copy answer";
  btn.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(text); btn.textContent = "✓"; setTimeout(() => (btn.textContent = "⧉"), 1200); } catch {}
  });
  bubble.appendChild(btn);
}

function renderCitations(msg, citations) {
  if (!citations || !citations.length) return;
  const bubble = msg.querySelector(".bubble");
  const wrap = document.createElement("div");
  wrap.className = "citations";
  wrap.innerHTML = `<div class="citations-title">Sources</div>`;
  citations.forEach((c) => {
    const row = document.createElement("div");
    row.className = "citation";
    row.dataset.marker = c.marker;
    row.innerHTML = `<span class="cnum">${c.marker}</span>
      <span class="cbody"><span class="csrc">${escapeHtml(c.source)}</span>
        <span class="cmeta">chunk ${c.chunk_index}</span>
        <span class="csnippet">${escapeHtml(c.snippet)}</span></span>
      <span class="cscore" title="cosine similarity">${(c.score ?? 0).toFixed(3)}</span>`;
    wrap.appendChild(row);
  });
  bubble.appendChild(wrap);
  bubble.querySelectorAll(".cite").forEach((chip) => {
    chip.addEventListener("click", () => {
      const t = wrap.querySelector(`.citation[data-marker="${chip.dataset.marker}"]`);
      if (!t) return;
      t.scrollIntoView({ behavior: "smooth", block: "nearest" });
      t.classList.remove("flash"); void t.offsetWidth; t.classList.add("flash");
    });
  });
}

async function ask(question) {
  question = (question || "").trim();
  if (!question) return;
  let convo = getConvo();
  if (!convo) { newChat(); convo = getConvo(); }

  // record + render user message
  convo.messages.push({ role: "user", content: question });
  if (convo.title === "New chat") convo.title = question.slice(0, 40);
  persist(convo);
  renderHistory();
  addMessageEl("user", question);

  const msg = addMessageEl("assistant", "");
  const bubble = msg.querySelector(".bubble");
  bubble.innerHTML = `<span class="typing"><span></span><span></span><span></span></span>`;

  $("#send-btn").disabled = true;
  let answer = "", citations = [], started = false;
  try {
    const resp = await fetch("/api/query/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
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
        const type = block.match(/^event: (.+)$/m)?.[1];
        const data = block.match(/^data: (.+)$/m)?.[1];
        if (!type || !data) continue;
        const payload = JSON.parse(data);
        if (type === "citations") citations = payload.citations;
        else if (type === "token") {
          if (!started) { bubble.textContent = ""; started = true; }
          answer += payload.text;
          bubble.textContent = answer;
          const cur = document.createElement("span"); cur.className = "cursor"; bubble.appendChild(cur);
          $("#messages").scrollTop = $("#messages").scrollHeight;
        }
      }
    }
  } catch (e) {
    answer = `⚠️ ${e.message}`;
  } finally {
    bubble.innerHTML = renderMarkdown(answer);
    renderCitations(msg, citations);
    if (answer && !answer.startsWith("⚠️")) addCopyButton(bubble, answer);
    $("#send-btn").disabled = false;
    // save assistant message
    convo.messages.push({ role: "assistant", content: answer, citations });
    persist(convo);
    refreshHealth();
  }
}

function persist(convo) {
  const c = currentConvos();
  const i = c.findIndex((x) => x.id === convo.id);
  if (i >= 0) c[i] = convo;
  // bump to top
  c.sort((a, b) => (b.id === convo.id ? 1 : 0) - (a.id === convo.id ? 1 : 0));
  saveConvos(c);
}

// ---------- documents ----------
async function refreshHealth() {
  try {
    const h = await (await fetch("/api/health")).json();
    // (status is reflected implicitly; kept for future badges)
    void h;
  } catch {}
}
async function refreshDocuments() {
  try {
    const data = await (await fetch("/api/documents")).json();
    const list = $("#doc-list");
    if (!data.documents.length) { list.innerHTML = `<li class="history-empty">No documents yet.</li>`; return; }
    list.innerHTML = "";
    data.documents.forEach((d) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="doc-name" title="${escapeHtml(d.source)}">📄 ${escapeHtml(d.source)}</span><span class="doc-count">${d.chunks}</span><button class="doc-del" title="Remove">✕</button>`;
      li.querySelector(".doc-del").addEventListener("click", async () => {
        await fetch(`/api/documents/${encodeURIComponent(d.source)}`, { method: "DELETE" });
        refreshDocuments();
      });
      list.appendChild(li);
    });
  } catch {}
}
async function uploadFile(file) {
  const s = $("#upload-status");
  s.className = "upload-status"; s.textContent = `Uploading ${file.name}…`;
  const form = new FormData(); form.append("file", file);
  try {
    const r = await fetch("/api/ingest", { method: "POST", body: form });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Upload failed");
    s.className = "upload-status ok"; s.textContent = `✓ ${data.message}`;
    refreshDocuments();
  } catch (e) {
    s.className = "upload-status err"; s.textContent = `✕ ${e.message}`;
  }
}

// ---------- theme ----------
function effectiveTheme() {
  return document.documentElement.dataset.theme ||
    (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("peit_theme", theme);
  const t = $("#theme-toggle"); if (t) t.textContent = theme === "dark" ? "☀️" : "🌙";
}

// ---------- app event bindings (once) ----------
function bindApp() {
  $("#composer").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("#question").value.trim();
    if (!q) return;
    $("#question").value = ""; $("#question").style.height = "auto";
    ask(q);
  });
  $("#question").addEventListener("input", () => {
    const q = $("#question"); q.style.height = "auto"; q.style.height = Math.min(q.scrollHeight, 170) + "px";
  });
  $("#question").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#composer").requestSubmit(); }
  });
  $("#new-chat-btn").addEventListener("click", newChat);
  $("#logout-btn").addEventListener("click", () => { store.clearUser(); location.hash = "#/"; });
  $("#theme-toggle").addEventListener("click", () => applyTheme(effectiveTheme() === "dark" ? "light" : "dark"));

  // uploads
  $("#file-input").addEventListener("change", () => { if ($("#file-input").files[0]) uploadFile($("#file-input").files[0]); $("#file-input").value = ""; });
  const dz = $("#dropzone");
  ["dragover", "dragenter"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("dragover"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("dragover"); }));
  dz.addEventListener("drop", (e) => { if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]); });
  $("#clear-btn").addEventListener("click", async () => {
    if (!confirm("Clear all indexed documents? (This affects the shared demo knowledge base.)")) return;
    await fetch("/api/documents", { method: "DELETE" }); refreshDocuments();
  });

  // mobile sidebar toggle
  const menuBtn = document.createElement("button");
  menuBtn.className = "btn btn-ghost btn-sm mobile-menu";
  menuBtn.textContent = "☰";
  menuBtn.onclick = () => $(".app-sidebar").classList.toggle("open");
  document.body.appendChild(menuBtn);
}

// ============================================================
//  INIT
// ============================================================
applyTheme(localStorage.getItem("peit_theme") || effectiveTheme());
bindAuth();
router();
