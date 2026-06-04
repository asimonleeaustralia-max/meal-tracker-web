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
    setDefaultMealDate();
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
  const result = await r.json();
  lastAnalysis = result;
  out.textContent = JSON.stringify(result, null, 2);
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
    const num = (v, d=1) => (v == null ? "0" : Number(v).toFixed(d));
    tr.innerHTML = `
      <td>${m.date ? new Date(m.date).toLocaleString() : ""}</td>
      <td>${escape(m.title)}</td>
      <td>${num(m.calories, 0)}</td>
      <td>${num(m.protein, 1)}</td>
      <td>${num(m.carbohydrates, 1)}</td>
      <td>${num(m.fat, 1)}</td>`;
    tbody.appendChild(tr);
  }
  // Show a hint when the list is empty
  if (meals.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="color:var(--muted);text-align:center;padding:16px;">No meals saved yet.</td></tr>';
  }
  console.log(`refreshMeals: ${meals.length} meals returned`);
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


// ---- Add meal form ----
// Cache the most recent vision analysis so the user can pre-fill from it.
let lastAnalysis = null;

function setDefaultMealDate() {
  // Default the date input to "now" in the user's local timezone.
  const now = new Date();
  const tz = now.getTimezoneOffset() * 60000;
  const local = new Date(now - tz).toISOString().slice(0, 16);
  const el = document.querySelector('#add-meal-form input[name="date"]');
  if (el && !el.value) el.value = local;
}

document.getElementById("add-meal-form").onsubmit = async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("add-meal-error");
  const okEl = document.getElementById("add-meal-success");
  errEl.hidden = true; okEl.hidden = true;

  const fd = new FormData(e.target);
  // datetime-local has no timezone — append :00 seconds and let backend parse as local-as-UTC.
  // For a single-user web app this is fine; iOS app uses real timezone-aware dates.
  const payload = {
    title: fd.get("title"),
    date: new Date(fd.get("date")).toISOString(),
    calories: Number(fd.get("calories")) || 0,
    protein: Number(fd.get("protein")) || 0,
    carbohydrates: Number(fd.get("carbohydrates")) || 0,
    fat: Number(fd.get("fat")) || 0,
  };

  const r = await api("/meals", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    errEl.textContent = await niceError(r);
    errEl.hidden = false;
    return;
  }
  okEl.textContent = "Meal saved.";
  okEl.hidden = false;
  e.target.reset();
  setDefaultMealDate();
  refreshMeals();
};

document.getElementById("fill-from-analysis").onclick = () => {
  if (!lastAnalysis || !lastAnalysis.nutrition) {
    showAddMealError("Run an analysis first, then click this to pre-fill.");
    return;
  }
  // Sum per-100g nutrition * estimated_grams / 100 across each predicted food.
  let cals = 0, prot = 0, carb = 0, fat = 0;
  const nutByLabel = Object.fromEntries(
    (lastAnalysis.nutrition.foods || []).map(f => [f.label, f.per_100g])
  );
  for (const pred of (lastAnalysis.predictions || [])) {
    const n = nutByLabel[pred.label];
    if (!n) continue;
    const grams = pred.estimated_grams || 100;
    cals += (n.calories || 0) * grams / 100;
    prot += (n.protein || 0) * grams / 100;
    carb += (n.carbohydrates || 0) * grams / 100;
    fat  += (n.fat || 0) * grams / 100;
  }
  const form = document.getElementById("add-meal-form");
  if (cals > 0 || prot > 0 || carb > 0 || fat > 0) {
    form.elements.calories.value = cals.toFixed(0);
    form.elements.protein.value = prot.toFixed(1);
    form.elements.carbohydrates.value = carb.toFixed(1);
    form.elements.fat.value = fat.toFixed(1);
    const titleSuggestion = (lastAnalysis.predictions || [])
      .map(p => p.label).slice(0, 3).join(", ");
    if (!form.elements.title.value && titleSuggestion) {
      form.elements.title.value = titleSuggestion;
    }
  } else {
    showAddMealError("Last analysis had no matched nutrition data — try again or enter manually.");
  }
};

function showAddMealError(msg) {
  const el = document.getElementById("add-meal-error");
  el.textContent = msg;
  el.hidden = false;
  document.getElementById("add-meal-success").hidden = true;
}

render();
