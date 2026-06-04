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
    if (typeof initNutrientValidation === "function") initNutrientValidation();
    if (typeof initGuessToggles === "function") initGuessToggles();
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

  // Auto-fill the Add a meal form with the predicted nutrition.
  const fillBtn = document.getElementById("fill-from-analysis");
  if (fillBtn) fillBtn.click();

  // Scroll back up to the form so the user can review/edit before saving.
  const form = document.getElementById("add-meal-form");
  if (form) form.scrollIntoView({ behavior: "smooth", block: "start" });
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

  const form = e.target;
  const fd = new FormData(form);

  // Build payload from every form field. Numeric fields go in only if non-zero;
  // is_guess flags only if the field is present (form has checkboxes for them).
  const payload = {
    title: fd.get("title"),
    date: new Date(fd.get("date")).toISOString(),
  };
  const productName = fd.get("product_name");
  if (productName) payload.product_name = productName;

  // Walk every number/checkbox input on the form and include non-default values.
  for (const el of form.elements) {
    if (!el.name) continue;
    if (el.type === "number") {
      const v = Number(el.value);
      if (!Number.isNaN(v) && v !== 0) payload[el.name] = v;
    } else if (el.type === "checkbox" && el.name.endsWith("_is_guess")) {
      payload[el.name] = el.checked;
    }
  }

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
  form.reset();
  // Re-collapse all detail panels after a save
  for (const d of form.querySelectorAll("details")) d.removeAttribute("open");
  setDefaultMealDate();
  refreshMeals();
};

// Reset button — also collapses detail panels
const resetBtn = document.getElementById("reset-meal-form");
if (resetBtn) {
  resetBtn.onclick = () => {
    const form = document.getElementById("add-meal-form");
    form.reset();
    for (const d of form.querySelectorAll("details")) d.removeAttribute("open");
    setDefaultMealDate();
    document.getElementById("add-meal-error").hidden = true;
    document.getElementById("add-meal-success").hidden = true;
  };
}

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


// ---- Guess/accurate toggle wiring ----
function initGuessToggles() {
  for (const t of document.querySelectorAll(".guess-toggle")) {
    const cb = t.querySelector('input[type="checkbox"]');
    const state = t.querySelector(".guess-state");
    if (!cb || !state) continue;
    const update = () => {
      t.classList.toggle("is-guess", cb.checked);
      state.textContent = cb.checked ? "guess" : "accurate";
    };
    update();
    t.addEventListener("click", (e) => {
      if (e.target !== cb) cb.checked = !cb.checked;
      update();
    });
  }
}
initGuessToggles();

// When the user types a non-zero number, auto-flip toggle off "guess".
for (const inp of document.querySelectorAll('#add-meal-form input[type="number"]')) {
  inp.addEventListener("input", () => {
    const guessName = inp.name + "_is_guess";
    const cb = document.querySelector(`#add-meal-form input[name="${guessName}"]`);
    if (cb && cb.checked && Number(inp.value) !== 0) {
      cb.checked = false;
      const toggle = cb.closest(".guess-toggle");
      if (toggle) {
        toggle.classList.remove("is-guess");
        toggle.querySelector(".guess-state").textContent = "accurate";
      }
    }
  });
}


// ---- Nutrient validation: visual flags only, never blocks save ----
const NUTRIENT_LIMITS = {
  // field: { warn, err, unit }
  calories:            { warn: 5000,  err: 10000, unit: "kcal" },
  protein:             { warn: 300,   err: 600,   unit: "g" },
  carbohydrates:       { warn: 800,   err: 1500,  unit: "g" },
  fat:                 { warn: 400,   err: 800,   unit: "g" },
  sodium:              { warn: 5000,  err: 10000, unit: "mg" },
  starch:              { warn: 600,   err: 1200,  unit: "g" },
  sugars:              { warn: 300,   err: 600,   unit: "g" },
  fibre:               { warn: 100,   err: 200,   unit: "g" },
  monounsaturated_fat: { warn: 200,   err: 400,   unit: "g" },
  polyunsaturated_fat: { warn: 200,   err: 400,   unit: "g" },
  saturated_fat:       { warn: 100,   err: 200,   unit: "g" },
  trans_fat:           { warn: 10,    err: 30,    unit: "g" },
  omega3:              { warn: 10,    err: 30,    unit: "g" },
  omega6:              { warn: 30,    err: 60,    unit: "g" },
  animal_protein:      { warn: 300,   err: 600,   unit: "g" },
  plant_protein:       { warn: 300,   err: 600,   unit: "g" },
  protein_supplements: { warn: 100,   err: 300,   unit: "g" },
  a2_beta_casein:      { warn: 50,    err: 150,   unit: "g" },
  a1_beta_casein:      { warn: 50,    err: 150,   unit: "g" },
  alcohol:             { warn: 80,    err: 200,   unit: "g" },
  nicotine:            { warn: 20,    err: 50,    unit: "mg" },
  theobromine:         { warn: 1000,  err: 2000,  unit: "mg" },
  caffeine:            { warn: 600,   err: 1200,  unit: "mg" },
  taurine:             { warn: 3000,  err: 6000,  unit: "mg" },
  creatine:            { warn: 20,    err: 50,    unit: "g" },
  vitamin_a:           { warn: 3,     err: 10,    unit: "mg" },
  vitamin_b:           { warn: 100,   err: 500,   unit: "mg" },
  vitamin_c:           { warn: 2000,  err: 10000, unit: "mg" },
  vitamin_d:           { warn: 0.1,   err: 0.25,  unit: "mg" },
  vitamin_e:           { warn: 1000,  err: 1500,  unit: "mg" },
  vitamin_k:           { warn: 10,    err: 30,    unit: "mg" },
  calcium:             { warn: 2500,  err: 5000,  unit: "mg" },
  iron:                { warn: 45,    err: 100,   unit: "mg" },
  potassium:           { warn: 5000,  err: 10000, unit: "mg" },
  zinc:                { warn: 40,    err: 100,   unit: "mg" },
  magnesium:           { warn: 700,   err: 1500,  unit: "mg" },
  iodine:              { warn: 1.1,   err: 3,     unit: "mg" },
  phosphorus:          { warn: 4000,  err: 8000,  unit: "mg" },
};

function checkNutrient(inp) {
  const lim = NUTRIENT_LIMITS[inp.name];
  if (!lim) return;
  const v = Number(inp.value);
  inp.classList.remove("warn", "err");
  inp.removeAttribute("title");
  if (Number.isNaN(v) || v <= 0) return;
  if (v >= lim.err) {
    inp.classList.add("err");
    inp.title = `Implausibly high. Typical max is around ${lim.warn} ${lim.unit}.`;
  } else if (v >= lim.warn) {
    inp.classList.add("warn");
    inp.title = `Unusually high — sanity-check this value (typical max ~${lim.warn} ${lim.unit}).`;
  }
}

function initNutrientValidation() {
  for (const inp of document.querySelectorAll('#add-meal-form input[type="number"]')) {
    inp.addEventListener("input", () => checkNutrient(inp));
    checkNutrient(inp);  // run once on load in case the form is pre-filled
  }
}
initNutrientValidation();


// Prevent input/toggle clicks inside a macro <summary> from collapsing the details.
for (const s of document.querySelectorAll("details.macro-group > summary")) {
  s.addEventListener("click", (e) => {
    // Only the chevron region toggles; any click on an input or toggle stays put.
    if (e.target.tagName === "INPUT" ||
        e.target.closest(".guess-toggle") ||
        e.target.classList.contains("field-label")) {
      e.preventDefault();
      // But labels for the input WILL receive a click — focus the input instead.
      if (e.target.classList.contains("field-label")) {
        const inp = s.querySelector('input[type="number"]');
        if (inp) inp.focus();
      }
    }
  });
}

render();
