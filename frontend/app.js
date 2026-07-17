/* ============================================================
   Peit — single-page app (router + auth + landing + chat)
   No framework, no build step.

   NOTE: sign-up/login and chat history are client-side (localStorage) so the
   live demo works with zero database. Email verification, OAuth, and the RAG
   endpoints (/api/*) are the real backend. Documents are scoped per chat.
   ============================================================ */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const MARK = '<svg class="mark-ic" aria-hidden="true"><use href="#peit-mark" /></svg>';
const ICON_MOON = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg>';
const ICON_SUN = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
const ICON_CLIP = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.4 11.05 12.25 20.2a5.5 5.5 0 0 1-7.78-7.78l9.19-9.19a3.67 3.67 0 0 1 5.19 5.19l-9.2 9.19a1.83 1.83 0 0 1-2.59-2.59l8.49-8.49"/></svg>';

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

const state = { currentConvoId: null, appBound: false, pendingSignup: null };

// ---------- helpers ----------
function escapeHtml(s) {
  return (s || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}
function initials(nameOrEmail) {
  const s = (nameOrEmail || "P").trim();
  return (s[0] || "P").toUpperCase();
}
function displayName(user) {
  return (user && (user.name || (user.email || "").split("@")[0])) || "there";
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
  // Stop the background animation when it's off-screen so it costs no GPU in the app;
  // initLanding() re-creates it when the user returns to the landing view.
  if (id !== "view-landing") destroyVantaBg();
  closeSidebar();
  window.scrollTo(0, 0);
}

function goHome() {
  closeAuth();
  showView("view-landing");
  updateNav();
  initLanding();
}

function goApp() {
  if (!store.user()) { openAuth("login"); return; }
  showView("view-app");
  initApp();
}

// Landing nav reflects auth state (logged out → Log in / Get started; in → Open dashboard)
function updateNav() {
  const el = $("#nav-actions");
  if (!el) return;
  if (store.user()) {
    el.innerHTML = `<button class="btn btn-primary btn-sm" id="nav-dash">Open dashboard</button>`;
    $("#nav-dash").onclick = goApp;
  } else {
    el.innerHTML =
      `<a class="nav-link" data-auth="login">Log in</a>` +
      `<button class="btn btn-primary btn-sm" data-auth="signup">Get started</button>`;
  }
}

// Clean-URL routing: clicks drive the views/modal directly, no hash in the address bar.
document.addEventListener("click", (e) => {
  const home = e.target.closest("[data-home]");
  if (home) { e.preventDefault(); goHome(); return; }
  const auth = e.target.closest("[data-auth]");
  if (auth) { e.preventDefault(); openAuth(auth.dataset.auth); return; }
});

// ============================================================
//  LANDING
// ============================================================
function initLanding() {
  // Never let the optional 3D hero break navigation — the CSS aurora is the fallback.
  try { initHero3D(); } catch (_e) { /* WebGL/library unavailable → aurora only */ }
  try { initVantaBg(); } catch (_e) { /* Vanta/library unavailable → aurora only */ }
}

// ---- Ambient animated background (Vanta.js NET) --------------------------------
// A slowly drifting network of nodes — a fitting motif for a retrieval/knowledge
// product. It rides on the three.js already loaded for the hero orb. To try another
// look, swap VANTA.NET below for VANTA.WAVES / VANTA.GLOBE / VANTA.FOG / VANTA.DOTS.
let vantaBg = null;
function bgColorForTheme() {
  // Indigo lines; a touch deeper in light mode so they read on a pale background.
  return effectiveTheme() === "light" ? 0x4f46e5 : 0x6366f1;
}
function initVantaBg() {
  if (vantaBg) return;
  const el = document.getElementById("vanta-bg");
  if (!el || typeof VANTA === "undefined" || !VANTA.NET || typeof THREE === "undefined") return;
  // Respect users who prefer reduced motion — keep the static aurora instead.
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  vantaBg = VANTA.NET({
    el,
    THREE: window.THREE,
    mouseControls: false,
    touchControls: false,
    gyroControls: false,
    minHeight: 200.0,
    minWidth: 200.0,
    scale: 1.0,
    scaleMobile: 1.0,
    backgroundAlpha: 0.0, // transparent → the aurora glow shows through
    color: bgColorForTheme(),
    points: window.innerWidth < 700 ? 6.0 : 11.0,
    maxDistance: 22.0,
    spacing: 17.0,
    showDots: true,
  });
}
function destroyVantaBg() {
  if (vantaBg) { try { vantaBg.destroy(); } catch (_e) { /* ignore */ } vantaBg = null; }
}

// Interactive 3D hero: a glossy icosphere that "breathes" and follows the pointer.
let hero3DStarted = false;
function initHero3D() {
  if (hero3DStarted) return;
  const canvas = document.getElementById("hero-canvas");
  if (!canvas || typeof THREE === "undefined") return; // graceful fallback → aurora
  hero3DStarted = true;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.z = 8.5;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  const geo = new THREE.IcosahedronGeometry(1.7, 6);
  const base = Float32Array.from(geo.attributes.position.array);
  const orb = new THREE.Mesh(
    geo,
    new THREE.MeshStandardMaterial({
      color: 0x6366f1, metalness: 0.45, roughness: 0.28,
      emissive: 0x140f3a, emissiveIntensity: 0.55,
    })
  );
  scene.add(orb);

  scene.add(new THREE.AmbientLight(0x24304f, 0.7));
  const L = [
    [0x6366f1, 2.6, [-4, 3, 4]],
    [0xa78bfa, 2.3, [4, -3, 3]],
    [0x8b5cf6, 1.3, [0, 4, -4]],
    [0xffffff, 0.8, [0, 0, 6]],
  ];
  L.forEach(([c, i, p]) => { const l = new THREE.PointLight(c, i, 24); l.position.set(...p); scene.add(l); });

  let mx = 0, my = 0, tx = 0, ty = 0;
  window.addEventListener("pointermove", (e) => {
    tx = e.clientX / window.innerWidth - 0.5;
    ty = e.clientY / window.innerHeight - 0.5;
  });

  const resize = () => {
    const w = canvas.clientWidth || window.innerWidth;
    const h = canvas.clientHeight || window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(canvas);
  resize();

  const pos = geo.attributes.position;
  const clock = new THREE.Clock();
  function frame() {
    requestAnimationFrame(frame);
    if (!document.getElementById("view-landing").classList.contains("active")) return;
    const t = clock.getElapsedTime();
    for (let i = 0; i < pos.count; i++) {
      const ix = i * 3;
      const bx = base[ix], by = base[ix + 1], bz = base[ix + 2];
      const n = (Math.sin(bx * 2.1 + t) + Math.sin(by * 2.5 + t * 1.15) + Math.sin(bz * 1.9 + t * 0.85)) / 3;
      const s = 1 + 0.14 * n;
      pos.setXYZ(i, bx * s, by * s, bz * s);
    }
    pos.needsUpdate = true;
    geo.computeVertexNormals();
    mx += (tx - mx) * 0.05;
    my += (ty - my) * 0.05;
    orb.rotation.y = t * 0.12 + mx * 0.8;
    orb.rotation.x = my * 0.5;
    renderer.render(scene, camera);
  }
  frame();
}

// ============================================================
//  AUTH
// ============================================================
function setAuthMode(mode) {
  showCodeStep(false);
  const isSignup = mode === "signup";
  const isReset = mode === "reset";
  const copy = {
    login: ["Welcome back", "Log in to continue to your knowledge base.", "Log in"],
    signup: ["Create your account", "Start chatting with your documents in seconds.", "Create account"],
    reset: ["Reset your password", "Enter your email and we'll send you a reset code.", "Send reset code"],
  }[mode] || ["Welcome back", "Log in to continue to your knowledge base.", "Log in"];
  $("#auth-title").textContent = copy[0];
  $("#auth-lead").textContent = copy[1];
  $("#auth-submit").textContent = copy[2];
  $("#name-field").style.display = isSignup ? "" : "none";
  $("#password-field").style.display = isReset ? "none" : "";
  $("#confirm-field").style.display = isSignup ? "" : "none";
  $("#forgot-row").hidden = mode !== "login";
  // Social sign-in applies to login/signup, not the password-reset step.
  $(".oauth-row").style.display = isReset ? "none" : "";
  $("#auth-step-main .auth-divider").style.display = isReset ? "none" : "";
  $("#auth-error").textContent = "";
  $("#auth-switch").innerHTML = isSignup
    ? `Already have an account? <a data-auth="login">Log in</a>`
    : isReset
      ? `Remembered your password? <a data-auth="login">Log in</a>`
      : `New to Peit? <a data-auth="signup">Create an account</a>`;
  $("#auth-form").dataset.mode = mode;
}

function showCodeStep(on) {
  $("#auth-step-main").hidden = !!on;
  $("#auth-step-code").hidden = !on;
}

function openAuth(mode) {
  setAuthMode(mode || "login");
  const m = $("#auth-modal");
  if (m) m.hidden = false;
  setTimeout(() => $("#auth-email")?.focus(), 60);
}

function closeAuth() {
  const m = $("#auth-modal");
  if (m) m.hidden = true;
  const err = $("#auth-error");
  if (err) err.textContent = "";
  showCodeStep(false);
  state.pendingSignup = null;
}

function oauthClick(provider) {
  if (window.__oauthProviders && window.__oauthProviders[provider]) {
    location.href = `/api/auth/${provider}/login`; // real OAuth redirect
  } else {
    const demo = provider === "google"
      ? { name: "Google user", email: "you@gmail.com", provider: "demo" }
      : { name: "GitHub user", email: "you@users.noreply.github.com", provider: "demo" };
    loginUser(demo);
  }
}

// Ask the backend to email a one-time code. Throws (with a user-facing message)
// when it can't be delivered — email sign-in requires SMTP to be configured.
async function requestCode(email, name) {
  const r = await fetch("/api/auth/signup/start", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, name: name || "" }),
  });
  const data = await r.json();
  if (!r.ok || !data.ok) throw new Error(data.error || "Could not send a code. Try again.");
  if (!data.delivered) {
    if (data.demo_code) console.info("[Peit] verification code:", data.demo_code); // dev aid
    throw new Error("Email delivery isn't set up yet — please use Google or GitHub to sign in.");
  }
  return data;
}

function prepareCodeStep(email, mode) {
  const isReset = mode === "reset";
  $("#code-email").textContent = email;
  $("#code-lead").innerHTML = `We sent a 6-digit code to <strong>${escapeHtml(email)}</strong>.`;
  $("#auth-code").value = "";
  $("#code-error").textContent = "";
  $("#reset-pass-field").hidden = !isReset;
  $("#reset-confirm-field").hidden = !isReset;
  if (isReset) { $("#reset-pass").value = ""; $("#reset-confirm").value = ""; }
  $("#code-submit").textContent = isReset ? "Reset password" : "Verify & continue";
  showCodeStep(true);
  setTimeout(() => $("#auth-code")?.focus(), 60);
}

async function startSignup(name, email, password) {
  const finalName = name || email.split("@")[0];
  const err = $("#auth-error");
  $("#auth-submit").disabled = true;
  $("#auth-submit").textContent = "Sending code…";
  try {
    const data = await requestCode(email, finalName);
    // Stash the details; the account is only created once the code is verified.
    state.pendingSignup = { name: finalName, email, password, token: data.token, mode: "signup" };
    prepareCodeStep(email, "signup");
  } catch (e) {
    err.textContent = e.message;
  } finally {
    $("#auth-submit").disabled = false;
    $("#auth-submit").textContent = "Create account";
  }
}

async function startReset(email) {
  const err = $("#auth-error");
  $("#auth-submit").disabled = true;
  $("#auth-submit").textContent = "Sending code…";
  try {
    const data = await requestCode(email, "");
    state.pendingSignup = { email, token: data.token, mode: "reset" };
    prepareCodeStep(email, "reset");
  } catch (e) {
    err.textContent = e.message;
  } finally {
    $("#auth-submit").disabled = false;
    $("#auth-submit").textContent = "Send reset code";
  }
}

async function verifyCode() {
  const p = state.pendingSignup;
  const err = $("#code-error");
  if (!p) { err.textContent = "Something went wrong. Start again."; return; }
  const code = $("#auth-code").value.trim();
  if (!/^\d{4,6}$/.test(code)) { err.textContent = "Enter the code from your email."; return; }

  let newPass = null;
  if (p.mode === "reset") {
    newPass = $("#reset-pass").value;
    if (newPass.length < 6) { err.textContent = "New password must be at least 6 characters."; return; }
    if (newPass !== $("#reset-confirm").value) { err.textContent = "Passwords don't match."; return; }
  }

  const original = $("#code-submit").textContent;
  $("#code-submit").disabled = true;
  $("#code-submit").textContent = "Verifying…";
  try {
    const r = await fetch("/api/auth/signup/verify", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: p.token, code }),
    });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || "Incorrect code. Try again.");

    const accounts = store.accounts();
    if (p.mode === "reset") {
      const existing = accounts[p.email];
      const name = (existing && existing.name) || data.name || p.email.split("@")[0];
      accounts[p.email] = { name, pass: btoa(newPass) };
      store.setAccounts(accounts);
      state.pendingSignup = null;
      loginUser({ name, email: p.email, provider: "email" });
    } else {
      accounts[p.email] = { name: p.name, pass: btoa(p.password) };
      store.setAccounts(accounts);
      state.pendingSignup = null;
      loginUser({ name: p.name, email: p.email, provider: "email" });
    }
  } catch (e) {
    err.textContent = e.message;
  } finally {
    $("#code-submit").disabled = false;
    $("#code-submit").textContent = original;
  }
}

function bindAuth() {
  $("#auth-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const mode = $("#auth-form").dataset.mode || "login";
    const name = $("#auth-name").value.trim();
    const email = $("#auth-email").value.trim().toLowerCase();
    const password = $("#auth-password").value;
    const confirm = $("#auth-confirm").value;
    const err = $("#auth-error");
    err.textContent = "";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { err.textContent = "Enter a valid email address."; return; }

    if (mode === "reset") { startReset(email); return; }

    if (password.length < 6) { err.textContent = "Password must be at least 6 characters."; return; }
    const accounts = store.accounts();
    if (mode === "signup") {
      if (password !== confirm) { err.textContent = "Passwords don't match."; return; }
      if (accounts[email]) { err.textContent = "An account with this email already exists. Try logging in."; return; }
      startSignup(name, email, password);
    } else {
      const acc = accounts[email];
      if (!acc || acc.pass !== btoa(password)) { err.textContent = "Wrong email or password."; return; }
      loginUser({ name: acc.name, email, provider: "email" });
    }
  });

  $("#auth-step-code").addEventListener("submit", (e) => { e.preventDefault(); verifyCode(); });
  $("#code-back").addEventListener("click", () => { showCodeStep(false); state.pendingSignup = null; });
  $("#forgot-link").addEventListener("click", () => setAuthMode("reset"));

  $("#oauth-google").addEventListener("click", () => oauthClick("google"));
  $("#oauth-github").addEventListener("click", () => oauthClick("github"));

  $("#auth-close").addEventListener("click", closeAuth);
  $("#auth-modal").addEventListener("click", (e) => { if (e.target.id === "auth-modal") closeAuth(); });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("#auth-modal").hidden) closeAuth();
    else if (!$("#account-modal").hidden) closeModal("account-modal");
    else if (!$("#settings-modal").hidden) closeModal("settings-modal");
  });
}

function loginUser(user) {
  store.setUser(user);
  $("#auth-password").value = "";
  $("#auth-confirm").value = "";
  state.currentConvoId = null;
  closeAuth();
  showView("view-app");
  initApp();
}

// ============================================================
//  APP / DASHBOARD
// ============================================================
function initApp() {
  const user = store.user();
  $("#user-email").textContent = user.email;
  $("#user-name").textContent = displayName(user);
  $("#user-avatar").textContent = initials(displayName(user));

  if (!state.appBound) { bindApp(); state.appBound = true; }

  applyTheme(localStorage.getItem("peit_theme") || effectiveTheme());
  applySidebarCollapsed();
  renderHistory();

  const convos = store.convos(user.email);
  if (!state.currentConvoId) {
    if (convos.length) selectChat(convos[0].id);
    else newChat();
  } else {
    renderMessages();
    renderAttachments();
  }
}

function currentConvos() { return store.convos(store.user().email); }
function saveConvos(c) { store.setConvos(store.user().email, c); }

function newChat() {
  const c = currentConvos();
  const convo = { id: uid(), title: "New chat", messages: [], docs: [], ts: Date.now() };
  c.unshift(convo);
  saveConvos(c);
  state.currentConvoId = convo.id;
  renderHistory();
  renderMessages();
  renderAttachments();
  closeSidebar();
  $("#question").focus();
}

function selectChat(id) {
  state.currentConvoId = id;
  renderHistory();
  renderMessages();
  renderAttachments();
  closeSidebar();
}

async function deleteChat(id) {
  const convo = currentConvos().find((x) => x.id === id);
  // Best-effort: drop this chat's documents from the index (ephemeral on serverless).
  (convo?.docs || []).forEach((d) => {
    fetch(`/api/documents/${encodeURIComponent(d.source)}?collection=${encodeURIComponent(id)}`, { method: "DELETE" }).catch(() => {});
  });
  let c = currentConvos().filter((x) => x.id !== id);
  saveConvos(c);
  if (state.currentConvoId === id) {
    if (c.length) { selectChat(c[0].id); return; }
    else { newChat(); return; }
  }
  renderHistory();
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
    const dot = (c.docs && c.docs.length) ? `<span class="hi-doc" title="${c.docs.length} file(s)">${ICON_CLIP}</span>` : "";
    li.innerHTML =
      `<span class="hi-title" title="${escapeHtml(c.title)}">${escapeHtml(c.title)}</span>${dot}` +
      `<span class="hi-actions">` +
      `<button class="hi-btn hi-rename" title="Rename" aria-label="Rename chat">✎</button>` +
      `<button class="hi-btn hi-del" title="Delete" aria-label="Delete chat">✕</button>` +
      `</span>`;
    li.querySelector(".hi-title").addEventListener("click", () => selectChat(c.id));
    li.querySelector(".hi-title").addEventListener("dblclick", (e) => { e.stopPropagation(); startRename(li, c); });
    li.querySelector(".hi-rename").addEventListener("click", (e) => { e.stopPropagation(); startRename(li, c); });
    li.querySelector(".hi-del").addEventListener("click", (e) => { e.stopPropagation(); deleteChat(c.id); });
    list.appendChild(li);
  });
}

function startRename(li, convo) {
  const titleEl = li.querySelector(".hi-title");
  if (!titleEl) return;
  li.classList.add("renaming");
  const input = document.createElement("input");
  input.className = "hi-edit";
  input.maxLength = 60;
  input.value = convo.title;
  titleEl.replaceWith(input);
  input.focus();
  input.select();
  let done = false;
  const commit = (save) => {
    if (done) return;
    done = true;
    if (save) {
      const v = input.value.trim();
      const c = currentConvos();
      const target = c.find((x) => x.id === convo.id);
      if (target && v) { target.title = v.slice(0, 60); saveConvos(c); }
    }
    renderHistory();
    if (state.currentConvoId === convo.id) setChatTitle(getConvo());
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); commit(true); }
    else if (e.key === "Escape") { e.preventDefault(); commit(false); }
  });
  input.addEventListener("blur", () => commit(true));
  input.addEventListener("click", (e) => e.stopPropagation());
}

const SUGGESTIONS = ["What is this document about?", "Summarize the key points.", "What are the main takeaways?"];

function setChatTitle(convo) {
  const el = $("#chat-title");
  if (el) el.textContent = convo ? convo.title : "New chat";
}

function renderMessages() {
  const box = $("#messages");
  const convo = getConvo();
  setChatTitle(convo);
  box.innerHTML = "";
  if (!convo || !convo.messages.length) {
    const hasDocs = convo && convo.docs && convo.docs.length;
    box.innerHTML = `
      <div class="app-empty">
        <div class="ae-mark">${MARK}</div>
        <h3>Ask anything about your documents</h3>
        <p>${hasDocs
          ? "Peit answers only from the files in this chat, and cites them inline."
          : "Attach a PDF, TXT, or Markdown file to this chat, then ask away — answers are grounded and cited."}</p>
        <div class="app-suggestions">${SUGGESTIONS.map((s) => `<button class="chip">${s}</button>`).join("")}</div>
      </div>`;
    $$("#messages .chip").forEach((c) => (c.onclick = () => ask(c.textContent)));
    return;
  }
  convo.messages.forEach((m) => {
    const msg = document.createElement("div");
    msg.className = `msg ${m.role}`;
    msg.innerHTML = `<div class="avatar">${m.role === "user" ? escapeHtml(initials(displayName(store.user()))) : MARK}</div><div class="bubble"></div>`;
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
  msg.innerHTML = `<div class="avatar">${role === "user" ? escapeHtml(initials(displayName(store.user()))) : MARK}</div><div class="bubble"></div>`;
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

  convo.messages.push({ role: "user", content: question });
  if (convo.title === "New chat") convo.title = question.slice(0, 40);
  persist(convo);
  renderHistory();
  setChatTitle(convo);
  addMessageEl("user", question);

  const msg = addMessageEl("assistant", "");
  const bubble = msg.querySelector(".bubble");
  const hasDocs = (getConvo()?.docs || []).length > 0;
  const setStatus = (label) => {
    bubble.innerHTML =
      `<span class="thinking"><span class="spinner"></span>` +
      `<span class="thinking-label">${escapeHtml(label)}</span></span>`;
  };
  setStatus(hasDocs ? "Searching this chat’s files…" : "Thinking…");

  $("#send-btn").disabled = true;
  let answer = "", citations = [], started = false, failed = false;
  try {
    const resp = await fetch("/api/query/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, collection: convo.id }),
    });
    if (!resp.ok || !resp.body) throw new Error("The server didn’t respond. Please try again.");
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
        if (type === "citations") {
          citations = payload.citations;
          setStatus(citations.length
            ? `Reading ${citations.length} passage${citations.length > 1 ? "s" : ""} · writing…`
            : "Writing…");
        } else if (type === "token") {
          if (!started) { bubble.textContent = ""; started = true; }
          answer += payload.text;
          bubble.textContent = answer;
          const cur = document.createElement("span"); cur.className = "cursor"; bubble.appendChild(cur);
          $("#messages").scrollTop = $("#messages").scrollHeight;
        }
      }
    }
    if (!started && !answer) answer = "I didn’t get a response. Please try again.";
  } catch (e) {
    failed = true;
    answer = `⚠️ ${e.message}`;
  } finally {
    if (failed) {
      bubble.innerHTML = `<div class="msg-error">${escapeHtml(answer)}</div>`;
    } else {
      bubble.innerHTML = renderMarkdown(answer);
      addCopyButton(bubble, answer);
    }
    renderCitations(msg, citations);
    $("#send-btn").disabled = false;
    // Don't persist transient failures into the saved history.
    if (!failed) { convo.messages.push({ role: "assistant", content: answer, citations }); persist(convo); }
    $("#messages").scrollTop = $("#messages").scrollHeight;
  }
}

function persist(convo) {
  const c = currentConvos();
  const i = c.findIndex((x) => x.id === convo.id);
  if (i >= 0) c[i] = convo;
  saveConvos(c);
}

// ---------- per-chat documents ----------
function renderAttachments() {
  const wrap = $("#attachments");
  const convo = getConvo();
  const docs = (convo && convo.docs) || [];
  if (!docs.length) { wrap.hidden = true; wrap.innerHTML = ""; return; }
  wrap.hidden = false;
  wrap.innerHTML = docs.map((d) => `
    <span class="chip-file" data-src="${escapeHtml(d.source)}">
      <span class="cf-ic">📄</span>
      <span class="cf-name" title="${escapeHtml(d.source)}">${escapeHtml(d.source)}</span>
      <button class="cf-del" title="Remove from chat" aria-label="Remove">✕</button>
    </span>`).join("");
  $$(".chip-file .cf-del", wrap).forEach((b) => {
    b.addEventListener("click", () => removeAttachment(b.closest(".chip-file").dataset.src));
  });
}

function setUploadStatus(kind, text) {
  const s = $("#upload-status");
  if (!text) { s.hidden = true; s.textContent = ""; return; }
  s.hidden = false;
  s.className = "upload-status" + (kind ? " " + kind : "");
  s.textContent = text;
}

async function uploadFiles(files) {
  const convo = getConvo();
  if (!convo) return;
  const list = [...files];
  for (const file of list) {
    setUploadStatus("", `Uploading ${file.name}…`);
    const form = new FormData();
    form.append("file", file);
    form.append("collection", convo.id);
    try {
      const r = await fetch("/api/ingest", { method: "POST", body: form });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Upload failed");
      // record on the convo (dedupe by filename)
      convo.docs = (convo.docs || []).filter((d) => d.source !== data.source);
      convo.docs.push({ source: data.source, chunks: data.chunks_added });
      persist(convo);
      renderAttachments();
      renderHistory();
      setUploadStatus("ok", `✓ Added ${data.source} to this chat`);
    } catch (e) {
      setUploadStatus("err", `✕ ${e.message}`);
    }
  }
  setTimeout(() => setUploadStatus("", ""), 2600);
}

async function removeAttachment(source) {
  const convo = getConvo();
  if (!convo) return;
  try {
    await fetch(`/api/documents/${encodeURIComponent(source)}?collection=${encodeURIComponent(convo.id)}`, { method: "DELETE" });
  } catch {}
  convo.docs = (convo.docs || []).filter((d) => d.source !== source);
  persist(convo);
  renderAttachments();
  renderHistory();
  if (!convo.messages.length) renderMessages();
}

// ---------- theme ----------
function effectiveTheme() {
  return document.documentElement.dataset.theme ||
    (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("peit_theme", theme);
  syncThemeUI(theme);
  // Keep the animated background legible against the new theme.
  if (vantaBg && vantaBg.setOptions) {
    try { vantaBg.setOptions({ color: bgColorForTheme() }); } catch (_e) { /* ignore */ }
  }
}
function syncThemeUI(theme) {
  const dark = theme === "dark";
  const ic = $("#menu-theme-ic"), label = $("#menu-theme-label");
  if (ic) ic.innerHTML = dark ? ICON_SUN : ICON_MOON;
  if (label) label.textContent = dark ? "Light mode" : "Dark mode";
  $$("#theme-seg button").forEach((b) => b.classList.toggle("active", b.dataset.theme === theme));
}

// ---------- profile menu + modals ----------
function toggleProfileMenu(force) {
  const menu = $("#profile-menu");
  const open = force !== undefined ? force : menu.hidden;
  menu.hidden = !open;
  $("#profile-btn").classList.toggle("open", open);
}
function openModal(id) { $("#" + id).hidden = false; }
function closeModal(id) { $("#" + id).hidden = true; }

function openAccount() {
  const u = store.user();
  $("#account-avatar").textContent = initials(displayName(u));
  $("#account-name-h").textContent = displayName(u);
  $("#account-email-h").textContent = u.email;
  $("#account-name").value = u.name || displayName(u);
  $("#account-email").value = u.email;
  $("#account-saved").hidden = true;
  openModal("account-modal");
}

function saveAccount(e) {
  e.preventDefault();
  const u = store.user();
  const name = $("#account-name").value.trim() || displayName(u);
  u.name = name;
  store.setUser(u);
  const accounts = store.accounts();
  if (accounts[u.email]) { accounts[u.email].name = name; store.setAccounts(accounts); }
  // reflect everywhere
  $("#user-name").textContent = name;
  $("#user-avatar").textContent = initials(name);
  $("#account-avatar").textContent = initials(name);
  $("#account-name-h").textContent = name;
  renderMessages();
  $("#account-saved").hidden = false;
  setTimeout(() => ($("#account-saved").hidden = true), 1600);
}

function openSettings() {
  openModal("settings-modal");
}

// ---------- sidebar (mobile drawer) ----------
function openSidebar() { $("#app-sidebar").classList.add("open"); $("#sidebar-scrim").hidden = false; }
function closeSidebar() { $("#app-sidebar")?.classList.remove("open"); const s = $("#sidebar-scrim"); if (s) s.hidden = true; }

// ---------- sidebar (desktop collapse) ----------
function setSidebarCollapsed(collapsed) {
  $("#view-app").classList.toggle("collapsed", collapsed);
  localStorage.setItem("peit_sidebar_collapsed", collapsed ? "1" : "0");
}
function applySidebarCollapsed() {
  setSidebarCollapsed(localStorage.getItem("peit_sidebar_collapsed") === "1");
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

  // collapse / expand the sidebar (desktop)
  $("#sidebar-collapse").addEventListener("click", () => setSidebarCollapsed(true));
  $("#sidebar-expand").addEventListener("click", () => setSidebarCollapsed(false));

  // per-chat uploads
  $("#attach-btn").addEventListener("click", () => $("#file-input").click());
  $("#file-input").addEventListener("change", () => {
    if ($("#file-input").files.length) uploadFiles($("#file-input").files);
    $("#file-input").value = "";
  });
  // drag & drop onto the message area uploads into the current chat
  const main = $(".app-main");
  ["dragover", "dragenter"].forEach((ev) => main.addEventListener(ev, (e) => { e.preventDefault(); main.classList.add("dragging"); }));
  ["dragleave", "drop"].forEach((ev) => main.addEventListener(ev, (e) => { e.preventDefault(); if (ev !== "dragover") main.classList.remove("dragging"); }));
  main.addEventListener("drop", (e) => { if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files); });

  // profile menu
  $("#profile-btn").addEventListener("click", (e) => { e.stopPropagation(); toggleProfileMenu(); });
  $("#profile-btn").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleProfileMenu(); } });
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#profile-menu") && !e.target.closest("#profile-btn")) toggleProfileMenu(false);
  });
  $("#menu-account").addEventListener("click", () => { toggleProfileMenu(false); openAccount(); });
  $("#menu-settings").addEventListener("click", () => { toggleProfileMenu(false); openSettings(); });
  $("#menu-theme").addEventListener("click", () => applyTheme(effectiveTheme() === "dark" ? "light" : "dark"));
  $("#menu-logout").addEventListener("click", async () => {
    try { await fetch("/api/auth/logout", { method: "POST" }); } catch {}
    store.clearUser();
    toggleProfileMenu(false);
    goHome();
  });

  // account modal
  $("#account-close").addEventListener("click", () => closeModal("account-modal"));
  $("#account-modal").addEventListener("click", (e) => { if (e.target.id === "account-modal") closeModal("account-modal"); });
  $("#account-form").addEventListener("submit", saveAccount);

  // settings modal
  $("#settings-close").addEventListener("click", () => closeModal("settings-modal"));
  $("#settings-modal").addEventListener("click", (e) => { if (e.target.id === "settings-modal") closeModal("settings-modal"); });
  $$("#theme-seg button").forEach((b) => b.addEventListener("click", () => applyTheme(b.dataset.theme)));
  $("#clear-all-chats").addEventListener("click", () => {
    if (!confirm("Delete every conversation on this device? This can't be undone.")) return;
    saveConvos([]);
    state.currentConvoId = null;
    closeModal("settings-modal");
    newChat();
  });

  // mobile sidebar
  $("#mobile-menu").addEventListener("click", openSidebar);
  $("#sidebar-close").addEventListener("click", closeSidebar);
  $("#sidebar-scrim").addEventListener("click", closeSidebar);
}

// ============================================================
//  INIT
// ============================================================
async function refreshProviders() {
  try {
    window.__oauthProviders = await (await fetch("/api/auth/providers")).json();
  } catch {
    window.__oauthProviders = { google: false, github: false };
  }
}

async function refreshSession() {
  try {
    const r = await fetch("/api/auth/me");
    if (r.ok) {
      const me = await r.json();
      if (me && me.email) {
        const existing = store.user();
        // keep any locally-edited display name for the same account
        const name = existing && existing.email === me.email && existing.name ? existing.name : me.name;
        store.setUser({ name, email: me.email, provider: me.provider });
        return;
      }
    }
  } catch {}
  const u = store.user();
  if (u && (u.provider === "google" || u.provider === "github")) store.clearUser();
}

function handleAuthQuery() {
  const params = new URLSearchParams(location.search);
  if (!params.has("auth")) return;
  const status = params.get("auth");
  history.replaceState(null, "", location.pathname);
  if (status === "error") {
    openAuth("login");
    $("#auth-error").textContent = "Sign-in failed. Please try again.";
  }
}

async function boot() {
  applyTheme(localStorage.getItem("peit_theme") || effectiveTheme());
  bindAuth();
  await Promise.all([refreshProviders(), refreshSession()]);
  if (store.user()) {
    showView("view-app");
    initApp();
  } else {
    showView("view-landing");
    updateNav();
    initLanding();
  }
  handleAuthQuery();
}

boot();
