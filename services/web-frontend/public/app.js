// MacrosSimple web frontend. All API calls go through the gateway.

const API = "https://mealtracker476a-gateway.kindgrass-8e900679.australiaeast.azurecontainerapps.io/api";

const tokens = {
  get access()  { return sessionStorage.getItem("at"); },
  get refresh() { return sessionStorage.getItem("rt"); },
  set(at, rt) { sessionStorage.setItem("at", at); sessionStorage.setItem("rt", rt); },
  clear() { sessionStorage.removeItem("at"); sessionStorage.removeItem("rt"); },
};

// ---- OAuth fragment handling ----
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
    initGuessToggles();
    initNutrientValidation();
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

// ---- Helpers ----
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
function num(v, d = 1) { return v == null ? "0" : Number(v).toFixed(d); }

// ---- Multi-photo upload UI ----
let pendingPhotos = [];  // [{ data_b64, thumb_b64, width, height, byte_size, name }]
const MAX_PHOTOS = 20;

async function resizePhotoToBase64(file, maxDim = 800, quality = 0.8) {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((res, rej) => {
      const i = new Image();
      i.onload = () => res(i);
      i.onerror = rej;
      i.src = url;
    });
    function encode(maxD, q) {
      const scale = Math.min(maxD / img.width, maxD / img.height, 1);
      const w = Math.max(1, Math.round(img.width * scale));
      const h = Math.max(1, Math.round(img.height * scale));
      const canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      canvas.getContext("2d").drawImage(img, 0, 0, w, h);
      const dataUrl = canvas.toDataURL("image/jpeg", q);
      return { data_b64: dataUrl.split(",")[1], width: w, height: h, size: dataUrl.length };
    }
    let main = encode(maxDim, quality);
    if (main.size > 600 * 1024) main = encode(640, 0.7);
    const thumb = encode(200, 0.7);
    return {
      data_b64: main.data_b64,
      thumb_b64: thumb.data_b64,
      width: main.width,
      height: main.height,
      byte_size: Math.round(main.size * 0.75),
    };
  } finally {
    URL.revokeObjectURL(url);
  }
}

function renderPhotoStrip() {
  const strip = document.getElementById("photo-strip");
  if (!strip) return;
  strip.innerHTML = "";
  if (pendingPhotos.length === 0) {
    strip.hidden = true;
    return;
  }
  strip.hidden = false;
  pendingPhotos.forEach((p, i) => {
    const div = document.createElement("div");
    div.className = "photo-thumb";
    div.innerHTML = `
      <img src="data:image/jpeg;base64,${p.thumb_b64 || p.data_b64}" alt="">
      <button type="button" class="photo-thumb-remove" aria-label="Remove">×</button>
    `;
    div.querySelector(".photo-thumb-remove").addEventListener("click", () => {
      pendingPhotos.splice(i, 1);
      renderPhotoStrip();
    });
    strip.appendChild(div);
  });
}

function initPhotoFlow() {
  const fileInput = document.getElementById("meal-photo");
  const addBtn = document.getElementById("photo-btn");
  if (!fileInput || !addBtn) return;
  addBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    const remaining = MAX_PHOTOS - pendingPhotos.length;
    if (remaining <= 0) {
      alert(`Maximum ${MAX_PHOTOS} photos per meal.`);
      fileInput.value = "";
      return;
    }
    const all = Array.from(fileInput.files);
    const files = all.slice(0, remaining);
    if (all.length > remaining) {
      alert(`Only added ${remaining} photo(s) — limit is ${MAX_PHOTOS} per meal.`);
    }
    for (const file of files) {
      try {
        const resized = await resizePhotoToBase64(file);
        pendingPhotos.push({ ...resized, name: file.name });
      } catch (e) {
        console.error("Failed to process photo", file.name, e);
      }
    }
    fileInput.value = "";
    renderPhotoStrip();
  });
}
initPhotoFlow();

// ---- Add meal form ----
function setDefaultMealDate() {
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
  const payload = {
    title: fd.get("title"),
    date: new Date(fd.get("date")).toISOString(),
  };
  for (const el of form.elements) {
    if (!el.name) continue;
    if (el.type === "number") {
      const v = Number(el.value);
      if (!Number.isNaN(v) && v !== 0) payload[el.name] = v;
    } else if (el.type === "checkbox" && el.name.endsWith("_is_guess")) {
      payload[el.name] = el.checked;
    }
  }

  const r = await api("/meals", { method: "POST", body: JSON.stringify(payload) });
  if (!r.ok) {
    errEl.textContent = await niceError(r);
    errEl.hidden = false;
    return;
  }
  const savedMeal = await r.json();

  // Upload pending photos
  let photoErrors = 0;
  for (const ph of pendingPhotos) {
    const pr = await api("/photos/inline", {
      method: "POST",
      body: JSON.stringify({
        meal_id: savedMeal.id,
        image_data_b64: ph.data_b64,
        thumb_data_b64: ph.thumb_b64,
        width: ph.width,
        height: ph.height,
        file_name_original: ph.name,
        byte_size_original: ph.byte_size,
      }),
    });
    if (!pr.ok) photoErrors++;
  }
  pendingPhotos = [];
  renderPhotoStrip();

  okEl.textContent = photoErrors > 0
    ? `Meal saved (${photoErrors} photo(s) failed).`
    : "Meal saved.";
  okEl.hidden = false;
  form.reset();
  for (const d of form.querySelectorAll("details")) d.removeAttribute("open");
  setDefaultMealDate();
  refreshMeals();
};

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
    if (!t.dataset.wired) {
      t.dataset.wired = "1";
      t.addEventListener("click", (e) => {
        if (e.target !== cb) cb.checked = !cb.checked;
        update();
      });
    }
  }
  // Auto-flip to "accurate" when user types a non-zero value
  for (const inp of document.querySelectorAll('#add-meal-form input[type="number"]')) {
    if (inp.dataset.autoFlip) continue;
    inp.dataset.autoFlip = "1";
    inp.addEventListener("input", () => {
      const cb = document.querySelector(`#add-meal-form input[name="${inp.name}_is_guess"]`);
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
}

// ---- Nutrient validation ----
const NUTRIENT_LIMITS = {
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
    inp.title = `Implausibly high. Typical max ~${lim.warn} ${lim.unit}.`;
  } else if (v >= lim.warn) {
    inp.classList.add("warn");
    inp.title = `Unusually high — sanity-check (typical max ~${lim.warn} ${lim.unit}).`;
  }
}
function initNutrientValidation() {
  for (const inp of document.querySelectorAll('#add-meal-form input[type="number"]')) {
    if (inp.dataset.validated) continue;
    inp.dataset.validated = "1";
    inp.addEventListener("input", () => checkNutrient(inp));
    checkNutrient(inp);
  }
}

// Prevent input clicks inside macro <summary> from collapsing the details
for (const s of document.querySelectorAll("details.macro-group > summary")) {
  s.addEventListener("click", (e) => {
    if (e.target.tagName === "INPUT" || e.target.closest(".guess-toggle") || e.target.classList.contains("field-label")) {
      e.preventDefault();
      if (e.target.classList.contains("field-label")) {
        const inp = s.querySelector('input[type="number"]');
        if (inp) inp.focus();
      }
    }
  });
}

// ---- Tabs ----
function initTabs() {
  const tabs = document.querySelectorAll(".tabs .tab");
  const panes = document.querySelectorAll(".tab-pane");
  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      const name = tab.dataset.tab;
      for (const t of tabs) t.classList.toggle("active", t === tab);
      for (const p of panes) {
        const isThis = p.id === "tab-" + name;
        p.classList.toggle("active", isThis);
        p.hidden = !isThis;
      }
      if (name === "history") refreshMeals();
      if (name === "reports") renderReports();
    });
  }
}
initTabs();

// ---- Meals list ----
let _mealsCache = [];
let _photosByMeal = {};

function startOfDay(d) { const x = new Date(d); x.setHours(0,0,0,0); return x; }

function renderDailyTotals(meals) {
  const today = startOfDay(new Date()).getTime();
  const todays = meals.filter(m => startOfDay(m.date).getTime() === today);
  const sum = (key) => todays.reduce((a, m) => a + (Number(m[key]) || 0), 0);
  const el = document.getElementById("daily-totals");
  if (!el) return;
  el.innerHTML = `
    <div class="totals-row">
      <span class="totals-label">Today</span>
      <span class="totals-num"><strong>${sum("calories").toFixed(0)}</strong> kcal</span>
      <span class="totals-num">P <strong>${sum("protein").toFixed(0)}g</strong></span>
      <span class="totals-num">C <strong>${sum("carbohydrates").toFixed(0)}g</strong></span>
      <span class="totals-num">F <strong>${sum("fat").toFixed(0)}g</strong></span>
      <span class="totals-meta">${todays.length} meal${todays.length === 1 ? "" : "s"}</span>
    </div>
  `;
}

async function fetchPhotosForMeal(mealId) {
  try {
    const r = await api(`/photos/by-meal/${mealId}`);
    if (!r.ok) return [];
    return await r.json();
  } catch { return []; }
}

async function refreshMeals() {
  const r = await api("/meals?limit=200");
  if (!r.ok) return;
  const meals = await r.json();
  _mealsCache = meals;
  const tbody = document.querySelector("#meals-table tbody");
  tbody.innerHTML = "";
  renderDailyTotals(meals);

  if (meals.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="muted" style="text-align:center;padding:16px;">No meals saved yet.</td></tr>';
    return;
  }
  for (const m of meals) {
    const tr = document.createElement("tr");
    tr.dataset.mealId = m.id;
    tr.className = "meal-row";
    tr.innerHTML = `
      <td>${m.date ? new Date(m.date).toLocaleString() : ""}</td>
      <td>${escape(m.title)}</td>
      <td>${num(m.calories, 0)}</td>
      <td>${num(m.protein, 1)}</td>
      <td>${num(m.carbohydrates, 1)}</td>
      <td>${num(m.fat, 1)}</td>
      <td class="photos-cell"><span class="muted">…</span></td>`;
    tr.addEventListener("click", () => toggleExpand(tr, m));
    tbody.appendChild(tr);
  }
  const results = await Promise.all(meals.map(m => fetchPhotosForMeal(m.id)));
  for (let i = 0; i < meals.length; i++) {
    const m = meals[i];
    const photos = results[i] || [];
    _photosByMeal[m.id] = photos;
    const cell = tbody.querySelector(`tr[data-meal-id="${m.id}"] .photos-cell`);
    if (cell) {
      cell.innerHTML = photos.length === 0
        ? '<span class="muted">—</span>'
        : `📷 ${photos.length}`;
    }
  }
}

function toggleExpand(tr, meal) {
  const next = tr.nextElementSibling;
  if (next && next.classList.contains("meal-expand-row")) {
    next.remove();
    tr.classList.remove("expanded");
    return;
  }
  tr.classList.add("expanded");
  const expandTr = document.createElement("tr");
  expandTr.className = "meal-expand-row";
  expandTr.dataset.mealId = meal.id;
  const td = document.createElement("td");
  td.colSpan = 7;
  expandTr.appendChild(td);
  tr.parentNode.insertBefore(expandTr, tr.nextSibling);
  renderExpandRow(meal);
}

function renderExpandRow(meal) {
  const expandTr = document.querySelector(`tr.meal-expand-row[data-meal-id="${meal.id}"]`);
  if (!expandTr) return;
  const td = expandTr.querySelector("td");
  const photos = _photosByMeal[meal.id] || [];
  td.innerHTML = `
    <div class="meal-expand">
      <div class="meal-expand-photos">
        ${photos.map((p, idx) => `
          <div class="photo-thumb" data-photo-id="${p.id}">
            <img src="data:image/jpeg;base64,${p.thumb_data_b64 || ''}" alt="">
            <button type="button" class="photo-action photo-action-delete" data-action="delete" title="Delete">✕</button>
            ${idx > 0 ? `<button type="button" class="photo-action photo-action-left" data-action="left" title="Move left">◀</button>` : ''}
            ${idx < photos.length - 1 ? `<button type="button" class="photo-action photo-action-right" data-action="right" title="Move right">▶</button>` : ''}
          </div>
        `).join("")}
        <button type="button" class="photo-add-btn" data-meal-id="${meal.id}">+ Add</button>
      </div>
    </div>
  `;

  // Wire up clicks
  td.querySelectorAll(".photo-thumb").forEach(div => {
    const pid = div.dataset.photoId;
    div.querySelector("img").addEventListener("click", (e) => {
      e.stopPropagation();
      openPhotoModal(pid);
    });
    const deleteBtn = div.querySelector('[data-action="delete"]');
    if (deleteBtn) deleteBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("Delete this photo?")) return;
      await deletePhoto(pid, meal);
    });
    const leftBtn = div.querySelector('[data-action="left"]');
    if (leftBtn) leftBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await movePhoto(pid, meal, -1);
    });
    const rightBtn = div.querySelector('[data-action="right"]');
    if (rightBtn) rightBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await movePhoto(pid, meal, 1);
    });
  });
  const addBtn = td.querySelector(".photo-add-btn");
  if (addBtn) addBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    addPhotosToMeal(meal);
  });
}

async function deletePhoto(photoId, meal) {
  const r = await api(`/photos/${photoId}`, { method: "DELETE" });
  if (!r.ok) {
    alert("Failed to delete photo.");
    return;
  }
  _photosByMeal[meal.id] = (_photosByMeal[meal.id] || []).filter(p => p.id !== photoId);
  renderExpandRow(meal);
  // Update the photo-count cell on the parent row
  const tr = document.querySelector(`tr[data-meal-id="${meal.id}"]`);
  if (tr) {
    const cell = tr.querySelector(".photos-cell");
    const n = _photosByMeal[meal.id].length;
    if (cell) cell.innerHTML = n === 0 ? '<span class="muted">—</span>' : `📷 ${n}`;
  }
}

async function movePhoto(photoId, meal, delta) {
  const photos = _photosByMeal[meal.id] || [];
  const idx = photos.findIndex(p => p.id === photoId);
  if (idx < 0) return;
  const newIdx = idx + delta;
  if (newIdx < 0 || newIdx >= photos.length) return;
  // Swap locally
  const reordered = [...photos];
  [reordered[idx], reordered[newIdx]] = [reordered[newIdx], reordered[idx]];
  // Send to backend
  const r = await api(`/photos/by-meal/${meal.id}/order`, {
    method: "PUT",
    body: JSON.stringify({ photo_ids: reordered.map(p => p.id) }),
  });
  if (!r.ok) {
    alert("Failed to reorder.");
    return;
  }
  _photosByMeal[meal.id] = reordered;
  renderExpandRow(meal);
}

async function addPhotosToMeal(meal) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.multiple = true;
  input.addEventListener("change", async () => {
    const existing = (_photosByMeal[meal.id] || []).length;
    const remaining = MAX_PHOTOS - existing;
    if (remaining <= 0) {
      alert(`This meal already has ${MAX_PHOTOS} photos (the maximum).`);
      return;
    }
    const files = Array.from(input.files).slice(0, remaining);
    if (input.files.length > remaining) {
      alert(`Only added ${remaining} photo(s) — limit is ${MAX_PHOTOS} per meal.`);
    }
    for (const file of files) {
      try {
        const resized = await resizePhotoToBase64(file);
        const r = await api("/photos/inline", {
          method: "POST",
          body: JSON.stringify({
            meal_id: meal.id,
            image_data_b64: resized.data_b64,
            thumb_data_b64: resized.thumb_b64,
            width: resized.width,
            height: resized.height,
            file_name_original: file.name,
            byte_size_original: resized.byte_size,
          }),
        });
        if (!r.ok) {
          alert(`Failed to upload ${file.name}`);
          continue;
        }
        const newPhoto = await r.json();
        // The list endpoint normally strips image_data_b64, but inline returns it. Strip to match.
        newPhoto.image_data_b64 = null;
        _photosByMeal[meal.id] = [...(_photosByMeal[meal.id] || []), newPhoto];
      } catch (e) {
        console.error("Photo upload failed", e);
      }
    }
    renderExpandRow(meal);
    // Update photo-count cell on the parent row
    const tr = document.querySelector(`tr[data-meal-id="${meal.id}"]`);
    if (tr) {
      const cell = tr.querySelector(".photos-cell");
      const n = (_photosByMeal[meal.id] || []).length;
      if (cell) cell.innerHTML = n === 0 ? '<span class="muted">—</span>' : `📷 ${n}`;
    }
  });
  input.click();
}

async function openPhotoModal(photoId) {
  let modal = document.getElementById("photo-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "photo-modal";
    modal.className = "photo-modal";
    modal.innerHTML = `<div class="photo-modal-backdrop"></div><div class="photo-modal-content"><img alt=""></div>`;
    modal.querySelector(".photo-modal-backdrop").addEventListener("click", () => modal.remove());
    document.body.appendChild(modal);
  }
  const img = modal.querySelector("img");
  img.src = "";
  try {
    const r = await api(`/photos/${photoId}`);
    if (!r.ok) throw new Error("fetch failed");
    const p = await r.json();
    img.src = `data:image/jpeg;base64,${p.image_data_b64}`;
  } catch (e) {
    img.alt = "Failed to load image";
  }
}

document.getElementById("refresh-meals").onclick = refreshMeals;

// ---- Reports tab ----
function isoWeekStart(d) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  const day = (x.getDay() + 6) % 7;
  x.setDate(x.getDate() - day);
  return x;
}
function fmtWeekLabel(d) {
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
async function renderReports() {
  const el = document.getElementById("reports-content");
  if (!el) return;
  el.innerHTML = "<p class=\"muted\">Loading…</p>";
  let meals = _mealsCache;
  if (!meals || meals.length === 0) {
    const r = await api("/meals?limit=500");
    if (r.ok) meals = await r.json();
    else meals = [];
  }
  const thisWeek = isoWeekStart(new Date());
  const weeks = [];
  for (let i = 0; i <= 7; i++) {
    const start = new Date(thisWeek);
    start.setDate(start.getDate() - i * 7);
    weeks.push({ start, calories: 0, protein: 0, carbohydrates: 0, fat: 0, count: 0 });
  }
  for (const m of meals) {
    const ws = isoWeekStart(new Date(m.date));
    const bucket = weeks.find(w => w.start.getTime() === ws.getTime());
    if (!bucket) continue;
    bucket.calories += Number(m.calories) || 0;
    bucket.protein += Number(m.protein) || 0;
    bucket.carbohydrates += Number(m.carbohydrates) || 0;
    bucket.fat += Number(m.fat) || 0;
    bucket.count += 1;
  }
  const maxCal = Math.max(1, ...weeks.map(w => w.calories));
  el.innerHTML = `
    <div class="reports-weeks">
      ${weeks.map((w, i) => {
        const label = (i === 0) ? "This week" : `Week of ${fmtWeekLabel(w.start)}`;
        const pct = (w.calories / maxCal) * 100;
        return `
          <div class="report-week ${i === 0 ? "current" : ""}">
            <div class="report-week-header">
              <span class="report-week-label">${label}</span>
              <span class="report-week-meta">${w.count} meal${w.count === 1 ? "" : "s"}</span>
            </div>
            <div class="report-bar"><div class="report-bar-fill" style="width:${pct}%"></div></div>
            <div class="report-week-stats">
              <span><strong>${w.calories.toFixed(0)}</strong> kcal</span>
              <span>P <strong>${w.protein.toFixed(0)}g</strong></span>
              <span>C <strong>${w.carbohydrates.toFixed(0)}g</strong></span>
              <span>F <strong>${w.fat.toFixed(0)}g</strong></span>
              <span class="muted">${(w.calories / 7).toFixed(0)}/day avg</span>
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

render();
