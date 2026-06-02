// Minimal vanilla-JS frontend. All API calls go through the gateway at /api/*.
// Tokens live in sessionStorage so they survive a reload but not a tab close.

const API = "https://mealtracker476a-gateway.kindgrass-8e900679.australiaeast.azurecontainerapps.io/api";

const tokens = {
  get access()  { return sessionStorage.getItem("at"); },
  get refresh() { return sessionStorage.getItem("rt"); },
  set(at, rt) { sessionStorage.setItem("at", at); sessionStorage.setItem("rt", rt); },
  clear() { sessionStorage.removeItem("at"); sessionStorage.removeItem("rt"); },
};

// ---- OAuth fragment handling ----
// On successful OAuth the callback redirects to /auth/success#access_token=...&refresh_token=...
(function handleOAuthFragment() {
  if (!location.hash) return;
  const frag = new URLSearchParams(location.hash.slice(1));
  const at = frag.get("access_token");
  const rt = frag.get("refresh_token");
  if (at && rt) {
    tokens.set(at, rt);
    history.replaceState(null, "", "/");
  }
})();

// ---- Fetch wrapper with auto-refresh on 401 ----
async function api(path, opts = {}) {
  const headers = new Headers(opts.headers || {});
  if (tokens.access) headers.set("Authorization", `Bearer ${tokens.access}`);
  if (opts.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  let resp = await fetch(`${API}${path}`, { ...opts, headers });
  if (resp.status === 401 && tokens.refresh) {
    const r = await fetch(`${API}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: tokens.refresh }),
    });
    if (r.ok) {
      const pair = await r.json();
      tokens.set(pair.access_token, pair.refresh_token);
      headers.set("Authorization", `Bearer ${pair.access_token}`);
      resp = await fetch(`${API}${path}`, { ...opts, headers });
    } else {
      tokens.clear();
      render();
      throw new Error("Session expired");
    }
  }
  return resp;
}

// ---- UI rendering ----
function render() {
  const authed = !!tokens.access;
  document.getElementById("auth-section").hidden = authed;
  document.getElementById("app-section").hidden = !authed;
  const bar = document.getElementById("user-bar");
  bar.textContent = authed ? "" : "";
  if (authed) {
    bar.innerHTML = `<button id="logout-btn" class="ghost">Sign out</button>`;
    document.getElementById("logout-btn").onclick = () => { tokens.clear(); render(); };
    refreshMeals();
  }
}

// ---- Login + signup ----
document.getElementById("login-form").onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = { email: fd.get("email"), password: fd.get("password") };
  const r = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) return showError(await niceError(r));
  const p = await r.json();
  tokens.set(p.access_token, p.refresh_token);
  render();
};

document.getElementById("signup-btn").onclick = async () => {
  const form = document.getElementById("login-form");
  const fd = new FormData(form);
  const body = { email: fd.get("email"), password: fd.get("password") };
  const r = await fetch(`${API}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) return showError(await niceError(r));
  const p = await r.json();
  tokens.set(p.access_token, p.refresh_token);
  render();
};

// ---- Vision: pick a photo, analyse, render predictions + nutrition ----
document.getElementById("analyze-btn").onclick = async () => {
  const fileEl = document.getElementById("meal-photo");
  const out = document.getElementById("analyze-output");
  if (!fileEl.files.length) { out.textContent = "Pick a photo first."; return; }
  out.textContent = "Analysing…";

  const b64 = await fileToBase64(fileEl.files[0]);
  const r = await api("/vision/analyze-meal", {
    method: "POST",
    body: JSON.stringify({ image_base64: b64, locale: "en" }),
  });
  if (!r.ok) { out.textContent = await niceError(r); return; }
  out.textContent = JSON.stringify(await r.json(), null, 2);
};

// ---- Meals list ----
async function refreshMeals() {
  const r = await api("/meals?limit=20");
  if (!r.ok) return;
  const meals = await r.json();
  const tbody = document.querySelector("#meals-table tbody");
  tbody.innerHTML = "";
  for (const m of meals) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${new Date(m.date).toLocaleString()}</td>
      <td>${escape(m.title)}</td>
      <td>${m.calories.toFixed(0)}</td>
      <td>${m.protein.toFixed(1)}</td>
      <td>${m.carbohydrates.toFixed(1)}</td>
      <td>${m.fat.toFixed(1)}</td>`;
    tbody.appendChild(tr);
  }
}
document.getElementById("refresh-meals").onclick = refreshMeals;

// ---- helpers ----
function fileToBase64(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result).split(",")[1]);
    r.onerror = rej;
    r.readAsDataURL(file);
  });
}
function showError(msg) {
  const el = document.getElementById("login-error");
  el.textContent = msg;
  el.hidden = false;
}
async function niceError(r) {
  try { const j = await r.json(); return j.detail || `${r.status} ${r.statusText}`; }
  catch { return `${r.status} ${r.statusText}`; }
}
function escape(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
}

render();
