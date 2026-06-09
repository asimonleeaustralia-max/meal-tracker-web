// MacrosSimple web frontend. All API calls go through the gateway.

const API = "/api";
const t = (key, params) => I18n.t(key, params);

/** Inline SVG icons — class "icon" picks up sizing from CSS. */
const ICONS = {
  settings: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="2"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  edit: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  delete: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><polyline points="3 6 5 6 21 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><line x1="10" y1="11" x2="10" y2="17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="14" y1="11" x2="14" y2="17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
};

function iconHtml(name) {
  return ICONS[name] || "";
}

const tokens = {
  get access()  { return sessionStorage.getItem("at"); },
  get refresh() { return sessionStorage.getItem("rt"); },
  get sessionId() { return sessionStorage.getItem("sid"); },
  set(at, rt, sid) {
    sessionStorage.setItem("at", at);
    sessionStorage.setItem("rt", rt);
    if (sid) sessionStorage.setItem("sid", sid);
  },
  clear() {
    sessionStorage.removeItem("at");
    sessionStorage.removeItem("rt");
    sessionStorage.removeItem("sid");
  },
};

let _isAdmin = false;
let _activityHeartbeat = null;

const Activity = {
  async track(eventType, extra = {}) {
    if (!tokens.access) return;
    try {
      await api("/auth/activity", {
        method: "POST",
        body: JSON.stringify({
          session_id: tokens.sessionId || null,
          event_type: eventType,
          path: extra.path ?? null,
          language: extra.language ?? I18n.getLanguage(),
          bytes_saved: extra.bytes_saved ?? null,
          metadata: extra.metadata ?? null,
        }),
      });
    } catch { /* best-effort */ }
  },
  trackTab(name) {
    this.track("tab_switch", { path: name });
  },
  startHeartbeat() {
    this.stopHeartbeat();
    _activityHeartbeat = setInterval(() => this.track("heartbeat"), 60000);
  },
  stopHeartbeat() {
    if (_activityHeartbeat) {
      clearInterval(_activityHeartbeat);
      _activityHeartbeat = null;
    }
  },
};

const HISTORY_PAGE_SIZE = 20;
let _currentUser = null;
let _historyPage = 0;

const UserPrefs = {
  key(userId) { return `macrossimple_prefs_${userId}`; },
  load(userId) {
    if (!userId) return {};
    try {
      const raw = localStorage.getItem(this.key(userId));
      return raw ? JSON.parse(raw) : {};
    } catch { return {}; }
  },
  save(userId, partial) {
    if (!userId) return;
    try {
      localStorage.setItem(this.key(userId), JSON.stringify({ ...this.load(userId), ...partial }));
    } catch { /* ignore */ }
  },
};

function saveUserPref(key, value) {
  if (!_currentUser?.id) return;
  UserPrefs.save(_currentUser.id, { [key]: value });
}

async function loadUserAndPrefs() {
  if (!tokens.access) {
    _currentUser = null;
    return null;
  }
  try {
    const r = await api("/auth/me");
    if (!r.ok) return null;
    const user = await r.json();
    const sameUser = _currentUser?.id === user.id;
    _currentUser = user;
    if (sameUser) return user;
    const prefs = UserPrefs.load(user.id);
    if (prefs.language) {
      await I18n.setLanguage(prefs.language);
    } else {
      saveUserPref("language", I18n.getLanguage());
    }
    applyReportPrefs(prefs);
    syncLanguageSelects();
    return user;
  } catch {
    return null;
  }
}

function applyReportPrefs(prefs) {
  const periodSel = document.getElementById("report-period");
  const nutrientsSel = document.getElementById("report-nutrients");
  if (prefs.reportPeriod && periodSel) periodSel.value = prefs.reportPeriod;
  if (prefs.reportNutrients && nutrientsSel) nutrientsSel.value = prefs.reportNutrients;
  const custom = periodSel?.value === "custom";
  const fromWrap = document.getElementById("report-custom-from-wrap");
  const toWrap = document.getElementById("report-custom-to-wrap");
  if (fromWrap) fromWrap.hidden = !custom;
  if (toWrap) toWrap.hidden = !custom;
}

// ---- OAuth fragment handling ----
(function handleOAuthFragment() {
  if (!location.hash) return;
  const frag = new URLSearchParams(location.hash.slice(1));
  const at = frag.get("access_token");
  const rt = frag.get("refresh_token");
  const sid = frag.get("session_id");
  if (at && rt) {
    tokens.set(at, rt, sid);
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
      throw new Error(t("session_expired"));
    }
  }
  return resp;
}

// ---- UI rendering ----
function render() {
  const authed = !!tokens.access;
  if (!authed) {
    Activity.stopHeartbeat();
    _isAdmin = false;
    const adminTab = document.getElementById("admin-tab-btn");
    if (adminTab) adminTab.hidden = true;
  }
  document.getElementById("auth-section").hidden = authed;
  document.getElementById("app-section").hidden = !authed;
  const bar = document.getElementById("user-bar");
  bar.textContent = authed ? "" : "";
  if (authed) {
    bar.innerHTML = `
      <div class="user-bar-actions">
        <button type="button" id="header-admin-btn" class="ghost admin-header-btn" hidden>Admin</button>
        <button type="button" id="header-settings-btn" class="icon-btn" title="${escape(t("open_settings"))}" aria-label="${escape(t("open_settings"))}">${iconHtml("settings")}</button>
        <button type="button" id="logout-btn" class="ghost" data-i18n="sign_out">Sign out</button>
      </div>`;
    I18n.applyStaticTranslations(bar);
    document.getElementById("header-settings-btn").onclick = () => switchToTab("settings");
    document.getElementById("header-admin-btn").onclick = () => {
      const adminTab = document.querySelector('.tabs .tab[data-tab="admin"]');
      if (adminTab) adminTab.click();
      else switchToTab("admin");
    };
    document.getElementById("logout-btn").onclick = async () => {
      await Activity.track("logout");
      Activity.stopHeartbeat();
      _currentUser = null;
      _isAdmin = false;
      tokens.clear();
      render();
    };
    void (async () => {
      await loadUserAndPrefs();
      await checkAdminAccess();
      Activity.track("page_view", { path: "app" });
      if (!_activityHeartbeat) Activity.startHeartbeat();
    })();
    refreshMeals();
    MealDateTime.init();
    MealDateTime.setNow();
    initGuessToggles();
    initNutrientValidation();
  }
}

// ---- Login + signup ----
function setAuthLoading(busy) {
  const form = document.getElementById("login-form");
  const loadingEl = document.getElementById("login-loading");
  const submitBtn = document.getElementById("login-submit-btn");
  const signupBtn = document.getElementById("signup-btn");
  form.querySelectorAll("input").forEach((el) => { el.disabled = busy; });
  if (submitBtn) submitBtn.disabled = busy;
  if (signupBtn) signupBtn.disabled = busy;
  document.querySelectorAll("#auth-section .oauth-btn").forEach((a) => {
    if (busy) a.setAttribute("aria-disabled", "true");
    else a.removeAttribute("aria-disabled");
  });
  if (loadingEl) loadingEl.hidden = !busy;
  form.setAttribute("aria-busy", busy ? "true" : "false");
}

document.querySelectorAll("#auth-section .oauth-btn").forEach((a) => {
  a.addEventListener("click", () => {
    document.getElementById("login-error").hidden = true;
    setAuthLoading(true);
  });
});

document.getElementById("login-form").onsubmit = async (e) => {
  e.preventDefault();
  document.getElementById("login-error").hidden = true;
  const fd = new FormData(e.target);
  const body = { email: fd.get("email"), password: fd.get("password") };
  setAuthLoading(true);
  try {
    const r = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) return showError(await niceError(r));
    const p = await r.json();
    tokens.set(p.access_token, p.refresh_token, p.session_id);
    render();
  } finally {
    setAuthLoading(false);
  }
};

document.getElementById("signup-btn").onclick = async () => {
  const form = document.getElementById("login-form");
  document.getElementById("login-error").hidden = true;
  const fd = new FormData(form);
  const body = { email: fd.get("email"), password: fd.get("password") };
  setAuthLoading(true);
  try {
    const r = await fetch(`${API}/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) return showError(await niceError(r));
    const p = await r.json();
    tokens.set(p.access_token, p.refresh_token, p.session_id);
    render();
  } finally {
    setAuthLoading(false);
  }
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
function loadingHtml(messageKey = "loading") {
  return `<div class="content-loading" aria-live="polite">
    <span class="content-spinner" aria-hidden="true"></span>
    <span>${escape(t(messageKey))}</span>
  </div>`;
}
function num(v, d = 1) { return v == null ? "0" : Number(v).toFixed(d); }

let _editingMealId = null;
let _toastTimer = null;

function showMealToast(message, type = "success") {
  const el = document.getElementById("add-meal-toast");
  if (!el) return;
  el.textContent = message;
  el.className = `header-toast ${type}`;
  el.hidden = false;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.hidden = true; }, 4000);
}

function setMealFormMode(editing) {
  const badge = document.getElementById("meal-form-badge");
  const saveBtn = document.getElementById("save-meal-btn");
  const saveKey = editing ? "save_changes" : "save_meal";
  if (badge) {
    if (editing) {
      badge.textContent = t("edit_meal");
      badge.hidden = false;
    } else {
      badge.hidden = true;
    }
  }
  if (saveBtn) {
    saveBtn.dataset.i18nTitle = saveKey;
    saveBtn.dataset.i18nAria = saveKey;
    saveBtn.title = t(saveKey);
    saveBtn.setAttribute("aria-label", t(saveKey));
  }
}

function switchToTab(name) {
  const tabs = document.querySelectorAll(".tabs .tab");
  const panes = document.querySelectorAll(".tab-pane");
  const isOverlay = name === "settings";
  for (const tab of tabs) {
    const isAdmin = name === "admin" && tab.dataset.tab === "admin";
    tab.classList.toggle("active", !isOverlay && (tab.dataset.tab === name || isAdmin));
  }
  for (const p of panes) {
    const isThis = p.id === "tab-" + name;
    p.classList.toggle("active", isThis);
    p.hidden = !isThis;
  }
  if (name === "history") refreshMeals();
  if (name === "reports") renderReports();
  if (name === "settings") initSettings();
  if (name === "admin") renderAdmin();
  if (name !== "settings") Activity.trackTab(name);
}

function pad2(n) { return String(n).padStart(2, "0"); }

function dateToInputValue(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function timeToInputValue(d) {
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function parseMealDateTime(dateStr, timeStr) {
  if (!dateStr || !timeStr) return null;
  const d = new Date(`${dateStr}T${timeStr}`);
  return Number.isNaN(d.getTime()) ? null : d;
}

const MealDateTime = (() => {
  let wired = false;

  function syncHidden() {
    const form = document.getElementById("add-meal-form");
    const hidden = form?.querySelector('input[name="date"]');
    const dateEl = document.getElementById("meal-date-input");
    const timeEl = document.getElementById("meal-time-input");
    if (!hidden || !dateEl || !timeEl) return;
    const d = parseMealDateTime(dateEl.value, timeEl.value);
    hidden.value = d ? d.toISOString() : "";
  }

  function setFromDate(d) {
    const dateEl = document.getElementById("meal-date-input");
    const timeEl = document.getElementById("meal-time-input");
    if (!dateEl || !timeEl) return;
    dateEl.value = dateToInputValue(d);
    timeEl.value = timeToInputValue(d);
    syncHidden();
  }

  function setNow() {
    setFromDate(new Date());
  }

  function init() {
    if (wired) return;
    const dateEl = document.getElementById("meal-date-input");
    const timeEl = document.getElementById("meal-time-input");
    const nowBtn = document.getElementById("meal-datetime-now");
    if (!dateEl || !timeEl) return;
    wired = true;
    for (const el of [dateEl, timeEl]) {
      el.addEventListener("change", syncHidden);
      el.addEventListener("input", syncHidden);
    }
    nowBtn?.addEventListener("click", setNow);
  }

  return { init, setNow, setFromDate, syncHidden };
})();

function populateMealForm(meal) {
  const form = document.getElementById("add-meal-form");
  if (!form) return;
  form.reset();
  form.querySelector('[name="title"]').value = meal.title || "";
  if (meal.date) MealDateTime.setFromDate(new Date(meal.date));
  else MealDateTime.setNow();
  for (const el of form.elements) {
    if (!el.name) continue;
    if (el.type === "number" && meal[el.name] != null) {
      el.value = meal[el.name];
    } else if (el.type === "checkbox" && el.name.endsWith("_is_guess")) {
      el.checked = !!meal[el.name];
      const toggle = el.closest(".guess-toggle");
      if (toggle) {
        toggle.classList.toggle("is-guess", el.checked);
        const state = toggle.querySelector(".guess-state");
        if (state) state.textContent = el.checked ? t("guess") : t("accurate");
      }
    }
  }
  initGuessToggles();
  initNutrientValidation();
}

function buildMealPayload(form) {
  MealDateTime.syncHidden();
  const fd = new FormData(form);
  const payload = {
    title: fd.get("title"),
    date: new Date(fd.get("date")).toISOString(),
  };
  for (const el of form.elements) {
    if (!el.name) continue;
    if (el.type === "number") {
      const v = Number(el.value);
      if (el.name === "calories") {
        if (!Number.isNaN(v) && v > 0) payload.calories = v;
      } else if (!Number.isNaN(v) && v !== 0) {
        payload[el.name] = v;
      }
    } else if (el.type === "checkbox" && el.name.endsWith("_is_guess")) {
      payload[el.name] = el.checked;
    }
  }
  return payload;
}

function resetMealForm() {
  _editingMealId = null;
  setMealFormMode(false);
  const form = document.getElementById("add-meal-form");
  if (form) {
    form.reset();
    for (const d of form.querySelectorAll("details")) d.removeAttribute("open");
  }
  pendingPhotos = [];
  renderPhotoStrip();
  MealDateTime.setNow();
  initGuessToggles();
}

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
      alert(t("max_photos_meal", { n: MAX_PHOTOS }));
      fileInput.value = "";
      return;
    }
    const all = Array.from(fileInput.files);
    const files = all.slice(0, remaining);
    if (all.length > remaining) {
      alert(t("max_photos_add", { n: remaining, max: MAX_PHOTOS }));
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
function validateCalories(form) {
  const inp = form.querySelector('[name="calories"]');
  if (!inp) return true;
  const v = Number(inp.value);
  const ok = inp.value !== "" && !Number.isNaN(v) && v > 0;
  inp.classList.toggle("err", !ok);
  return ok;
}

MealDateTime.init();

document.getElementById("add-meal-form").onsubmit = async (e) => {
  e.preventDefault();
  const toast = document.getElementById("add-meal-toast");
  if (toast) toast.hidden = true;

  const form = e.target;
  MealDateTime.syncHidden();
  if (!validateCalories(form)) {
    showMealToast(t("calories_required"), "error");
    form.querySelector('[name="calories"]')?.focus();
    return;
  }
  const hiddenDate = form.querySelector('input[name="date"]');
  if (!hiddenDate?.value) {
    showMealToast(t("tooltip_date"), "error");
    return;
  }
  const payload = buildMealPayload(form);
  if (!payload.calories) {
    showMealToast(t("calories_required"), "error");
    return;
  }
  const isEdit = !!_editingMealId;

  const r = isEdit
    ? await api(`/meals/${_editingMealId}`, { method: "PUT", body: JSON.stringify(payload) })
    : await api("/meals", { method: "POST", body: JSON.stringify(payload) });

  if (!r.ok) {
    showMealToast(await niceError(r), "error");
    return;
  }
  const savedMeal = await r.json();

  let photoErrors = 0;
  if (!isEdit) {
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
  }

  const msg = isEdit
    ? t("changes_saved")
    : photoErrors > 0
      ? t("meal_saved_photos_failed", { n: photoErrors })
      : t("meal_saved");
  showMealToast(msg, "success");
  if (!isEdit) {
    const bytes = JSON.stringify(savedMeal).length + pendingPhotos.reduce((n, p) => n + (p.byte_size || 0), 0);
    Activity.track("meal_saved", { path: savedMeal.id, bytes_saved: bytes });
  }
  resetMealForm();
  refreshMeals();
};

// ---- Guess/accurate toggle wiring ----
function initGuessToggles() {
  for (const toggle of document.querySelectorAll(".guess-toggle")) {
    const cb = toggle.querySelector('input[type="checkbox"]');
    const state = toggle.querySelector(".guess-state");
    if (!cb || !state) continue;
    const update = () => {
      toggle.classList.toggle("is-guess", cb.checked);
      state.textContent = cb.checked ? t("guess") : t("accurate");
    };
    update();
    if (!toggle.dataset.wired) {
      toggle.dataset.wired = "1";
      toggle.addEventListener("click", (e) => {
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
          toggle.querySelector(".guess-state").textContent = t("accurate");
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
    inp.addEventListener("input", () => {
      checkNutrient(inp);
      if (inp.name === "calories") validateCalories(inp.closest("form"));
    });
    checkNutrient(inp);
  }
}

// Prevent input clicks inside macro <summary> from collapsing the details
for (const s of document.querySelectorAll("details.macro-group > summary")) {
  s.addEventListener("click", (e) => {
    if (
      e.target.tagName === "INPUT" ||
      e.target.closest(".guess-toggle") ||
      e.target.classList.contains("field-label")
    ) {
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
      if (name === "admin") renderAdmin();
      Activity.trackTab(name);
    });
  }
}
initTabs();

// ---- Meals list ----
let _mealsCache = [];
let _photosByMeal = {};
let _mealsFetchGen = 0;
let _reportsRenderGen = 0;

function startOfDay(d) { const x = new Date(d); x.setHours(0,0,0,0); return x; }

function renderDailyTotals(meals) {
  const today = startOfDay(new Date()).getTime();
  const todays = meals.filter(m => startOfDay(m.date).getTime() === today);
  const sum = (key) => todays.reduce((a, m) => a + (Number(m[key]) || 0), 0);
  const el = document.getElementById("daily-totals");
  if (!el) return;
  el.innerHTML = `
    <div class="totals-row">
      <span class="totals-label">${t("today")}</span>
      <span class="totals-num"><strong>${sum("calories").toFixed(0)}</strong> kcal</span>
      <span class="totals-num">P <strong>${sum("protein").toFixed(0)}g</strong></span>
      <span class="totals-num">C <strong>${sum("carbohydrates").toFixed(0)}g</strong></span>
      <span class="totals-num">F <strong>${sum("fat").toFixed(0)}g</strong></span>
      <span class="totals-meta">${todays.length} ${todays.length === 1 ? t("meals_one") : t("meals_many")}</span>
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

function updateHistoryPagination(meals) {
  const pag = document.getElementById("history-pagination");
  const info = document.getElementById("history-page-info");
  const prev = document.getElementById("history-prev");
  const next = document.getElementById("history-next");
  if (!pag) return;
  const totalPages = Math.max(1, Math.ceil(meals.length / HISTORY_PAGE_SIZE));
  if (_historyPage >= totalPages) _historyPage = totalPages - 1;
  pag.hidden = meals.length <= HISTORY_PAGE_SIZE;
  if (info) info.textContent = t("history_page", { current: _historyPage + 1, total: totalPages });
  if (prev) prev.disabled = _historyPage <= 0;
  if (next) next.disabled = _historyPage >= totalPages - 1;
}

async function refreshMeals() {
  const gen = ++_mealsFetchGen;
  const tbody = document.querySelector("#meals-table tbody");
  const dailyEl = document.getElementById("daily-totals");
  const refreshBtn = document.getElementById("refresh-meals");
  const pag = document.getElementById("history-pagination");

  if (tbody) tbody.innerHTML = `<tr><td colspan="8">${loadingHtml()}</td></tr>`;
  if (dailyEl) dailyEl.innerHTML = loadingHtml();
  if (pag) pag.hidden = true;
  if (refreshBtn) refreshBtn.disabled = true;

  try {
    const r = await api("/meals?limit=200");
    if (gen !== _mealsFetchGen) return;
    if (!r.ok) {
      const msg = t("load_data_failed");
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="8" class="muted" style="text-align:center;padding:16px;">${escape(msg)}</td></tr>`;
      }
      if (dailyEl) dailyEl.innerHTML = "";
      return;
    }
    const meals = await r.json();
    if (gen !== _mealsFetchGen) return;
    _mealsCache = meals;
    renderDailyTotals(meals);
    renderMealsPage();
  } catch {
    if (gen !== _mealsFetchGen) return;
    const msg = t("load_data_failed");
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="8" class="muted" style="text-align:center;padding:16px;">${escape(msg)}</td></tr>`;
    }
    if (dailyEl) dailyEl.innerHTML = "";
  } finally {
    if (gen === _mealsFetchGen && refreshBtn) refreshBtn.disabled = false;
  }
}

function renderMealsPage() {
  const meals = _mealsCache;
  const tbody = document.querySelector("#meals-table tbody");
  tbody.innerHTML = "";
  updateHistoryPagination(meals);

  if (meals.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="muted" style="text-align:center;padding:16px;">${escape(t("no_meals"))}</td></tr>`;
    return;
  }

  const start = _historyPage * HISTORY_PAGE_SIZE;
  const pageMeals = meals.slice(start, start + HISTORY_PAGE_SIZE);
  for (const m of pageMeals) {
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
      <td class="photos-cell"><span class="muted">…</span></td>
      <td class="col-actions">
        <div class="row-actions">
          <button type="button" class="icon-btn meal-edit-btn" title="${escape(t("edit_meal_btn"))}" aria-label="${escape(t("edit_meal_btn"))}">${iconHtml("edit")}</button>
          <button type="button" class="icon-btn icon-btn-danger meal-delete-btn" title="${escape(t("delete_meal_btn"))}" aria-label="${escape(t("delete_meal_btn"))}">${iconHtml("delete")}</button>
        </div>
      </td>`;

    tr.querySelector(".meal-edit-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      startEditMeal(m);
    });
    tr.querySelector(".meal-delete-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      deleteMeal(m);
    });
    tr.addEventListener("click", (e) => {
      if (e.target.closest(".row-actions")) return;
      toggleExpand(tr, m);
    });
    tbody.appendChild(tr);
  }
  loadMealPhotos(pageMeals);
}

async function loadMealPhotos(meals) {
  const results = await Promise.all(meals.map((m) => fetchPhotosForMeal(m.id)));
  for (let i = 0; i < meals.length; i++) {
    const m = meals[i];
    const photos = results[i] || [];
    _photosByMeal[m.id] = photos;
    const cell = document.querySelector(`#meals-table tr[data-meal-id="${m.id}"] .photos-cell`);
    if (cell) {
      cell.innerHTML = photos.length === 0
        ? '<span class="muted">—</span>'
        : `${photos.length}`;
    }
  }
}

function initHistoryPagination() {
  document.getElementById("history-prev")?.addEventListener("click", () => {
    if (_historyPage > 0) {
      _historyPage--;
      renderMealsPage();
    }
  });
  document.getElementById("history-next")?.addEventListener("click", () => {
    const totalPages = Math.ceil(_mealsCache.length / HISTORY_PAGE_SIZE);
    if (_historyPage < totalPages - 1) {
      _historyPage++;
      renderMealsPage();
    }
  });
}

function startEditMeal(meal) {
  _editingMealId = meal.id;
  setMealFormMode(true);
  populateMealForm(meal);
  pendingPhotos = [];
  renderPhotoStrip();
  switchToTab("log");
  document.getElementById("add-meal-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function deleteMeal(meal) {
  if (!confirm(t("delete_meal_confirm", { title: meal.title || t("delete_meal_this") }))) return;
  const r = await api(`/meals/${meal.id}`, { method: "DELETE" });
  if (!r.ok) {
    alert(t("delete_meal_failed"));
    return;
  }
  if (_editingMealId === meal.id) resetMealForm();
  delete _photosByMeal[meal.id];
  const expandRow = document.querySelector(`tr.meal-expand-row[data-meal-id="${meal.id}"]`);
  expandRow?.remove();
  await refreshMeals();
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
  td.colSpan = 8;
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
            <button type="button" class="photo-action photo-action-delete" data-action="delete" title="${escape(t("delete"))}">✕</button>
            ${idx > 0 ? `<button type="button" class="photo-action photo-action-left" data-action="left" title="${escape(t("move_left"))}">◀</button>` : ''}
            ${idx < photos.length - 1 ? `<button type="button" class="photo-action photo-action-right" data-action="right" title="${escape(t("move_right"))}">▶</button>` : ''}
          </div>
        `).join("")}
        <button type="button" class="photo-add-btn" data-meal-id="${meal.id}">${escape(t("add_photo_short"))}</button>
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
      if (!confirm(t("delete_photo_confirm"))) return;
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
    alert(t("delete_photo_failed"));
    return;
  }
  _photosByMeal[meal.id] = (_photosByMeal[meal.id] || []).filter(p => p.id !== photoId);
  renderExpandRow(meal);
  // Update the photo-count cell on the parent row
  const tr = document.querySelector(`tr[data-meal-id="${meal.id}"]`);
  if (tr) {
    const cell = tr.querySelector(".photos-cell");
    const n = _photosByMeal[meal.id].length;
    if (cell) cell.innerHTML = n === 0 ? '<span class="muted">—</span>' : `${n}`;
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
    alert(t("reorder_failed"));
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
      alert(t("max_photos_existing", { n: MAX_PHOTOS }));
      return;
    }
    const files = Array.from(input.files).slice(0, remaining);
    if (input.files.length > remaining) {
      alert(t("max_photos_add", { n: remaining, max: MAX_PHOTOS }));
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
          alert(t("upload_failed", { name: file.name }));
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
      if (cell) cell.innerHTML = n === 0 ? '<span class="muted">—</span>' : `${n}`;
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
    img.alt = t("failed_load_image");
  }
}

document.getElementById("refresh-meals").onclick = refreshMeals;

// ---- Reports tab ----
function getReportNutrientSets() {
  const n = (key, unit, decimals) => ({
    key,
    label: t(`nutrient_${key}`),
    unit,
    decimals,
  });
  return {
    macros: [
      n("calories", "kcal", 0),
      n("protein", "g", 0),
      n("carbohydrates", "g", 0),
      n("fat", "g", 0),
    ],
    extended: [
      n("calories", "kcal", 0),
      n("protein", "g", 0),
      n("carbohydrates", "g", 0),
      n("fat", "g", 0),
      n("sodium", "mg", 0),
      n("sugars", "g", 1),
      n("fibre", "g", 1),
      n("saturated_fat", "g", 1),
      n("starch", "g", 1),
    ],
    full: [
      n("calories", "kcal", 0),
      n("protein", "g", 0),
      n("carbohydrates", "g", 0),
      n("fat", "g", 0),
      n("sodium", "mg", 0),
      n("sugars", "g", 1),
      n("fibre", "g", 1),
      n("saturated_fat", "g", 1),
      n("monounsaturated_fat", "g", 1),
      n("polyunsaturated_fat", "g", 1),
      n("trans_fat", "g", 1),
      n("omega3", "g", 1),
      n("omega6", "g", 1),
      n("animal_protein", "g", 1),
      n("plant_protein", "g", 1),
      n("alcohol", "g", 1),
      n("caffeine", "mg", 0),
      n("vitamin_a", "mg", 2),
      n("vitamin_c", "mg", 0),
      n("vitamin_d", "mg", 2),
      n("calcium", "mg", 0),
      n("iron", "mg", 1),
      n("potassium", "mg", 0),
      n("magnesium", "mg", 0),
    ],
  };
}

function isoWeekStart(d) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  const day = (x.getDay() + 6) % 7;
  x.setDate(x.getDate() - day);
  return x;
}

function startOfMonth(d) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  x.setDate(1);
  return x;
}

function fmtShortDate(d) {
  return d.toLocaleDateString(I18n.getLocale(), { month: "short", day: "numeric", year: "numeric" });
}

function fmtMonthLabel(d) {
  return d.toLocaleDateString(I18n.getLocale(), { month: "long", year: "numeric" });
}

function bucketKeyForMeal(mealDate, period) {
  const d = new Date(mealDate);
  if (period === "week") return isoWeekStart(d).getTime();
  if (period === "month") return startOfMonth(d).getTime();
  return startOfDay(d).getTime();
}

function buildReportBuckets(period) {
  const now = new Date();
  const buckets = [];

  if (period === "week") {
    const thisWeek = isoWeekStart(now);
    for (let i = 0; i <= 7; i++) {
      const start = new Date(thisWeek);
      start.setDate(start.getDate() - i * 7);
      buckets.push({ start, key: start.getTime(), count: 0, totals: {} });
    }
  } else if (period === "month") {
    const thisMonth = startOfMonth(now);
    for (let i = 0; i <= 11; i++) {
      const start = new Date(thisMonth);
      start.setMonth(start.getMonth() - i);
      buckets.push({ start, key: start.getTime(), count: 0, totals: {} });
    }
  } else if (period === "day") {
    const today = startOfDay(now);
    for (let i = 0; i < 30; i++) {
      const start = new Date(today);
      start.setDate(start.getDate() - i);
      buckets.push({ start, key: start.getTime(), count: 0, totals: {} });
    }
  } else {
    const fromEl = document.getElementById("report-custom-from");
    const toEl = document.getElementById("report-custom-to");
    const from = fromEl?.value ? startOfDay(new Date(fromEl.value + "T00:00:00")) : null;
    const to = toEl?.value ? startOfDay(new Date(toEl.value + "T00:00:00")) : null;
    if (!from || !to || from > to) return [];
    const cur = new Date(from);
    while (cur <= to) {
      buckets.push({ start: new Date(cur), key: cur.getTime(), count: 0, totals: {} });
      cur.setDate(cur.getDate() + 1);
    }
    buckets.reverse();
  }
  return buckets;
}

function periodLabel(bucket, period, index) {
  if (period === "week") {
    return index === 0 ? t("this_week") : t("week_of", { date: fmtShortDate(bucket.start) });
  }
  if (period === "month") {
    return index === 0 ? t("this_month") : fmtMonthLabel(bucket.start);
  }
  if (period === "day") {
    const today = startOfDay(new Date()).getTime();
    return bucket.start.getTime() === today ? t("today_label") : fmtShortDate(bucket.start);
  }
  return fmtShortDate(bucket.start);
}

function avgPerDay(value, period, bucket) {
  if (period === "week") return value / 7;
  if (period === "month") {
    const end = new Date(bucket.start);
    end.setMonth(end.getMonth() + 1);
    end.setDate(0);
    const days = end.getDate();
    return value / days;
  }
  return value;
}

function renderNutrientGrid(totals, nutrients) {
  return `
    <div class="report-nutrient-grid">
      ${nutrients.map((n) => {
        const v = Number(totals[n.key]) || 0;
        const shown = v.toFixed(n.decimals);
        return `<div class="report-nutrient-item"><span>${n.label}</span><span>${shown} ${n.unit}</span></div>`;
      }).join("")}
    </div>
  `;
}

function getReportFilterState() {
  const period = document.getElementById("report-period")?.value || "week";
  const nutrientSet = document.getElementById("report-nutrients")?.value || "macros";
  const nutrientSets = getReportNutrientSets();
  const nutrients = nutrientSets[nutrientSet] || nutrientSets.macros;
  return { period, nutrientSet, nutrients };
}

function buildReportView(meals) {
  const { period, nutrientSet, nutrients } = getReportFilterState();
  const buckets = buildReportBuckets(period);
  if (buckets.length === 0) {
    return { period, nutrientSet, nutrients, buckets: [], effectivePeriod: period === "custom" ? "day" : period };
  }

  const effectivePeriod = period === "custom" ? "day" : period;
  const bucketMap = new Map(buckets.map((b) => [b.key, b]));
  for (const m of meals) {
    const key = bucketKeyForMeal(m.date, effectivePeriod);
    const bucket = bucketMap.get(key);
    if (!bucket) continue;
    bucket.count += 1;
    for (const n of nutrients) {
      bucket.totals[n.key] = (bucket.totals[n.key] || 0) + (Number(m[n.key]) || 0);
    }
  }
  return { period, nutrientSet, nutrients, buckets, effectivePeriod };
}

function reportPeriodRows(view) {
  const { period, nutrients, buckets, effectivePeriod } = view;
  return buckets.map((b, i) => {
    const cal = b.totals.calories || 0;
    const avg = avgPerDay(cal, effectivePeriod, b);
    return {
      label: periodLabel(b, effectivePeriod, i),
      start: b.start.toISOString().slice(0, 10),
      meals: b.count,
      totals: Object.fromEntries(
        nutrients.map((n) => [n.key, Number((b.totals[n.key] || 0).toFixed(n.decimals))])
      ),
      avg_kcal_per_day: Number(avg.toFixed(0)),
    };
  });
}

async function ensureReportMeals() {
  if (_mealsCache && _mealsCache.length > 0) return _mealsCache;
  const r = await api("/meals?limit=500");
  if (!r.ok) throw new Error(t("load_data_failed"));
  _mealsCache = await r.json();
  return _mealsCache;
}

async function renderReports() {
  const el = document.getElementById("reports-content");
  if (!el) return;
  const gen = ++_reportsRenderGen;
  const needsFetch = !_mealsCache || _mealsCache.length === 0;

  if (needsFetch) el.innerHTML = loadingHtml();

  let meals;
  if (needsFetch) {
    try {
      meals = await ensureReportMeals();
      if (gen !== _reportsRenderGen) return;
    } catch {
      if (gen !== _reportsRenderGen) return;
      el.innerHTML = `<p class="report-summary-empty">${escape(t("load_data_failed"))}</p>`;
      return;
    }
  } else {
    meals = _mealsCache;
  }

  const view = buildReportView(meals);
  if (gen !== _reportsRenderGen) return;

  if (view.buckets.length === 0) {
    el.innerHTML = `<p class="report-summary-empty">${escape(t("report_empty_range"))}</p>`;
    return;
  }

  const maxCal = Math.max(1, ...view.buckets.map((b) => b.totals.calories || 0));

  if (view.buckets.every((b) => b.count === 0)) {
    el.innerHTML = `<p class="report-summary-empty">${escape(t("report_no_meals"))}</p>`;
    return;
  }

  const { period, nutrients, buckets, effectivePeriod } = view;
  if (gen !== _reportsRenderGen) return;
  el.innerHTML = `
    <div class="reports-periods">
      ${buckets.map((b, i) => {
        const cal = b.totals.calories || 0;
        const pct = (cal / maxCal) * 100;
        const avg = avgPerDay(cal, effectivePeriod, b);
        const primary = nutrients.slice(0, 4);
        return `
          <div class="report-period ${i === 0 ? "current" : ""}">
            <div class="report-period-header">
              <span class="report-period-label">${periodLabel(b, effectivePeriod, i)}</span>
              <span class="report-period-meta">${b.count} ${b.count === 1 ? t("meals_one") : t("meals_many")}</span>
            </div>
            <div class="report-bar"><div class="report-bar-fill" style="width:${pct}%"></div></div>
            <div class="report-period-stats">
              ${primary.map((n) => {
                const v = b.totals[n.key] || 0;
                return `<span>${n.label} <strong>${v.toFixed(n.decimals)}</strong> ${n.unit}</span>`;
              }).join("")}
              <span class="muted">${avg.toFixed(0)}${t("day_avg_kcal")}</span>
            </div>
            ${renderNutrientGrid(b.totals, nutrients)}
          </div>
        `;
      }).join("")}
    </div>
  `;
}

async function exportReportData() {
  const btn = document.getElementById("report-export-btn");
  const format = document.getElementById("report-export-format")?.value || "csv";
  if (btn) btn.disabled = true;
  try {
    const meals = await ensureReportMeals();
    const view = buildReportView(meals);
    if (view.buckets.length === 0) {
      alert(t("report_empty_range"));
      return;
    }
    if (view.buckets.every((b) => b.count === 0)) {
      alert(t("report_no_meals"));
      return;
    }

    const rows = reportPeriodRows(view);
    const date = new Date().toISOString().slice(0, 10);
    const fromEl = document.getElementById("report-custom-from");
    const toEl = document.getElementById("report-custom-to");

    if (format === "json") {
      const payload = {
        exported_at: new Date().toISOString(),
        app: "MacrosSimple",
        filters: {
          period: view.period,
          nutrients: view.nutrientSet,
          from: view.period === "custom" ? fromEl?.value || null : null,
          to: view.period === "custom" ? toEl?.value || null : null,
        },
        periods: rows,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `macrossimple-report-${date}.json`;
      a.click();
      URL.revokeObjectURL(url);
      return;
    }

    const headers = [
      "Period",
      "Start date",
      "Meals",
      ...view.nutrients.map((n) => `${n.label} (${n.unit})`),
      "Avg kcal/day",
    ];
    const dataRows = rows.map((row) => [
      row.label,
      row.start,
      row.meals,
      ...view.nutrients.map((n) => row.totals[n.key] ?? 0),
      row.avg_kcal_per_day,
    ]);
    if (format === "excel") {
      downloadExcel(`macrossimple-report-${date}.xls`, headers, dataRows);
      return;
    }
    downloadCsv(`macrossimple-report-${date}.csv`, rowsToCsv(headers, dataRows));
  } catch (e) {
    alert(t("export_failed", { msg: e.message || e }));
  } finally {
    if (btn) btn.disabled = false;
  }
}

function initReportsControls() {
  const periodSel = document.getElementById("report-period");
  const fromWrap = document.getElementById("report-custom-from-wrap");
  const toWrap = document.getElementById("report-custom-to-wrap");
  const fromInput = document.getElementById("report-custom-from");
  const toInput = document.getElementById("report-custom-to");

  const today = startOfDay(new Date());
  const monthAgo = new Date(today);
  monthAgo.setDate(monthAgo.getDate() - 30);
  if (fromInput && !fromInput.value) fromInput.value = monthAgo.toISOString().slice(0, 10);
  if (toInput && !toInput.value) toInput.value = today.toISOString().slice(0, 10);

  function syncCustomVisibility() {
    const custom = periodSel?.value === "custom";
    if (fromWrap) fromWrap.hidden = !custom;
    if (toWrap) toWrap.hidden = !custom;
  }

  periodSel?.addEventListener("change", () => {
    syncCustomVisibility();
    saveUserPref("reportPeriod", periodSel.value);
    renderReports();
  });
  document.getElementById("report-nutrients")?.addEventListener("change", (e) => {
    saveUserPref("reportNutrients", e.target.value);
    renderReports();
  });
  fromInput?.addEventListener("change", renderReports);
  toInput?.addEventListener("change", renderReports);
  syncCustomVisibility();

  document.getElementById("report-export-btn")?.addEventListener("click", exportReportData);
  document.getElementById("export-json-btn")?.addEventListener("click", exportUserDataJson);
}

async function exportUserDataJson() {
  const btn = document.getElementById("export-json-btn");
  if (btn) btn.disabled = true;
  try {
    const r = await api("/meals?limit=1000");
    if (!r.ok) throw new Error(await niceError(r));
    const meals = await r.json();
    const photoResults = await Promise.all(
      meals.map(async (m) => {
        try {
          const pr = await api(`/photos/by-meal/${m.id}`);
          return pr.ok ? await pr.json() : [];
        } catch {
          return [];
        }
      })
    );
    const exportData = {
      exported_at: new Date().toISOString(),
      app: "MacrosSimple",
      version: 1,
      meals: meals.map((m, i) => ({
        ...m,
        photos: photoResults[i] || [],
      })),
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `macrossimple-export-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert(t("export_failed", { msg: e.message || e }));
  } finally {
    if (btn) btn.disabled = false;
  }
}

let _languageSelectSyncing = false;

function compareLanguageLabels(a, b) {
  try {
    return a[1].label.localeCompare(b[1].label, undefined, { sensitivity: "base" });
  } catch (_) {
    return a[1].label < b[1].label ? -1 : a[1].label > b[1].label ? 1 : 0;
  }
}

async function onLanguageSelectChange(ev) {
  if (_languageSelectSyncing) return;
  const sel = ev.target;
  const code = sel?.value;
  if (!code) return;
  await I18n.setLanguage(code);
  saveUserPref("language", code);
  Activity.track("language_change", { language: code, path: "settings" });
}

function setSelectLanguageValue(sel, lang) {
  sel.value = lang;
  if (sel.value === lang) return;
  for (const opt of sel.options) {
    if (opt.value === lang) {
      opt.selected = true;
      return;
    }
  }
}

function populateLanguageSelect(sel) {
  if (!sel) return;
  if (!sel.dataset.populated) {
    sel.addEventListener("change", onLanguageSelectChange);
    sel.addEventListener("input", onLanguageSelectChange);
    sel.dataset.populated = "1";
  }
  const entries = Object.entries(I18n.SUPPORTED).sort(compareLanguageLabels);

  _languageSelectSyncing = true;
  try {
    sel.innerHTML = "";
    for (const [code, meta] of entries) {
      const opt = document.createElement("option");
      opt.value = code;
      opt.textContent = meta.label;
      sel.appendChild(opt);
    }
    setSelectLanguageValue(sel, I18n.getLanguage());
  } finally {
    _languageSelectSyncing = false;
  }
}

function syncLanguageSelects() {
  const lang = I18n.getLanguage();
  const sel = document.getElementById("language-select-settings");
  if (!sel) return;
  _languageSelectSyncing = true;
  try {
    setSelectLanguageValue(sel, lang);
  } finally {
    _languageSelectSyncing = false;
  }
}

let _appVersionPromise = null;

function getAppVersion() {
  const meta = document.querySelector('meta[name="app-version"]')?.content;
  if (meta && meta !== "dev") return meta;
  return null;
}

function loadAppVersion() {
  const fromMeta = getAppVersion();
  if (fromMeta) return Promise.resolve(fromMeta);
  if (!_appVersionPromise) {
    _appVersionPromise = fetch("/version.json")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => data?.version || "unknown")
      .catch(() => "unknown");
  }
  return _appVersionPromise;
}

function initSettings() {
  populateLanguageSelect(document.getElementById("language-select-settings"));
  const acct = document.getElementById("settings-account-email");
  if (acct) {
    if (_currentUser?.email) {
      acct.textContent = `Signed in as ${_currentUser.email}`;
      acct.hidden = false;
    } else {
      acct.hidden = true;
    }
  }
  const labelEl = document.getElementById("settings-version-label");
  if (labelEl) labelEl.textContent = t("settings_version");
  const verEl = document.getElementById("settings-app-version");
  if (verEl) {
    loadAppVersion().then((v) => { verEl.textContent = v; });
  }
}

function refreshUIAfterLanguageChange() {
  I18n.applyLanguage();
  syncLanguageSelects();
  setMealFormMode(!!_editingMealId);
  const labelEl = document.getElementById("settings-version-label");
  if (labelEl) labelEl.textContent = t("settings_version");
  const activeTab = document.querySelector(".tabs .tab.active")?.dataset.tab;
  if (activeTab === "history" && tokens.access) refreshMeals();
  if (activeTab === "reports") renderReports();
  const settingsBtn = document.getElementById("header-settings-btn");
  if (settingsBtn) {
    settingsBtn.title = t("open_settings");
    settingsBtn.setAttribute("aria-label", t("open_settings"));
  }
  const logout = document.getElementById("logout-btn");
  if (logout) logout.textContent = t("sign_out");
}

I18n.onLanguageChange(refreshUIAfterLanguageChange);

function formatBytes(n) {
  if (n == null || n === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let v = Number(n);
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(i ? 1 : 0)} ${units[i]}`;
}

function formatDuration(sec) {
  if (sec == null) return "—";
  const s = Number(sec);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m < 60) return `${m}m ${r}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

function formatDateTime(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

let _adminCache = { users: [], sessions: [], activity: [] };
let _adminExportBound = false;

function csvCell(value) {
  if (value == null) return "";
  const s = String(value);
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function rowsToCsv(headers, rows) {
  const lines = [headers.map(csvCell).join(",")];
  for (const row of rows) lines.push(row.map(csvCell).join(","));
  return lines.join("\r\n");
}

function downloadCsv(filename, csv) {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function xmlEscape(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function excelCell(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return `<Cell><Data ss:Type="Number">${value}</Data></Cell>`;
  }
  return `<Cell><Data ss:Type="String">${xmlEscape(value ?? "")}</Data></Cell>`;
}

function rowsToSpreadsheetXml(headers, rows, sheetName) {
  const headerRow = `<Row>${headers.map(excelCell).join("")}</Row>`;
  const bodyRows = rows.map((row) => `<Row>${row.map(excelCell).join("")}</Row>`).join("");
  return `<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="${xmlEscape(sheetName)}">
  <Table>
   ${headerRow}
   ${bodyRows}
  </Table>
 </Worksheet>
</Workbook>`;
}

function downloadExcel(filename, headers, rows) {
  const xml = rowsToSpreadsheetXml(headers, rows, "Report");
  const blob = new Blob([xml], { type: "application/vnd.ms-excel" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function exportAdminTable(kind) {
  const date = new Date().toISOString().slice(0, 10);
  if (kind === "users") {
    const headers = ["Email", "Logins", "Last login", "Method", "Session time (s)", "Events", "Meals", "Data saved (bytes)", "Language", "Last IP"];
    const rows = _adminCache.users.map((u) => [
      u.email || u.user_id,
      u.login_count,
      u.last_login_at || "",
      u.last_login_method || "",
      u.total_session_seconds ?? "",
      u.activity_event_count,
      u.meal_count,
      u.data_bytes_saved ?? "",
      u.preferred_language || "",
      u.last_ip || "",
    ]);
    downloadCsv(`admin-users-${date}.csv`, rowsToCsv(headers, rows));
  } else if (kind === "sessions") {
    const headers = ["Time", "Email", "Method", "IP", "Language", "Duration (s)", "Client"];
    const rows = _adminCache.sessions.map((s) => [
      s.logged_in_at || "",
      s.user_email || s.user_id,
      s.login_method || "",
      s.ip_address || "",
      s.language || "",
      s.duration_seconds ?? "",
      s.client || "",
    ]);
    downloadCsv(`admin-sessions-${date}.csv`, rowsToCsv(headers, rows));
  } else if (kind === "activity") {
    const headers = ["Time", "Email", "Event", "Path", "IP", "Language", "Bytes"];
    const rows = _adminCache.activity.map((e) => [
      e.created_at || "",
      e.user_email || e.user_id,
      e.event_type || "",
      e.path || "",
      e.ip_address || "",
      e.language || "",
      e.bytes_saved ?? "",
    ]);
    downloadCsv(`admin-activity-${date}.csv`, rowsToCsv(headers, rows));
  }
}

function initAdminExportButtons() {
  if (_adminExportBound) return;
  _adminExportBound = true;
  document.querySelector(".admin-card")?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-admin-export]");
    if (!btn) return;
    exportAdminTable(btn.dataset.adminExport);
  });
}

function updateAdminChrome() {
  const tab = document.getElementById("admin-tab-btn");
  const headerBtn = document.getElementById("header-admin-btn");
  if (tab) tab.hidden = !_isAdmin;
  if (headerBtn) headerBtn.hidden = !_isAdmin;
}

async function checkAdminAccess() {
  if (!tokens.access) {
    _isAdmin = false;
    updateAdminChrome();
    return;
  }
  _isAdmin = !!_currentUser?.is_admin;
  if (!_isAdmin) {
    try {
      const r = await api("/auth/admin/check");
      _isAdmin = r.ok;
    } catch {
      _isAdmin = false;
    }
  }
  updateAdminChrome();
}

async function renderAdmin() {
  if (!_isAdmin) return;
  initAdminExportButtons();
  const overviewEl = document.getElementById("admin-overview");
  try {
    const [ovR, usersR, sessR, actR] = await Promise.all([
      api("/auth/admin/overview"),
      api("/auth/admin/users"),
      api("/auth/admin/sessions?limit=50"),
      api("/auth/admin/activity?limit=50"),
    ]);
    if (!ovR.ok) throw new Error(await niceError(ovR));
    const ov = await ovR.json();
    overviewEl.innerHTML = [
      ["Users", ov.total_users],
      ["Total logins", ov.total_logins],
      ["Activity events", ov.total_activity_events],
      ["Active sessions", ov.active_sessions],
      ["Logins (24h)", ov.logins_24h],
      ["Events (24h)", ov.events_24h],
      ["Unique IPs (24h)", ov.unique_ips_24h],
    ].map(([label, val]) => `
      <div class="admin-stat">
        <div class="admin-stat-value">${escape(String(val))}</div>
        <div class="admin-stat-label">${escape(label)}</div>
      </div>`).join("");

    const users = usersR.ok ? await usersR.json() : [];
    const sessions = sessR.ok ? await sessR.json() : [];
    const activity = actR.ok ? await actR.json() : [];
    _adminCache = { users, sessions, activity };

    const usersBody = document.querySelector("#admin-users-table tbody");
    usersBody.innerHTML = users.map((u) => `
      <tr>
        <td>${escape(u.email || u.user_id)}</td>
        <td>${u.login_count}</td>
        <td>${escape(formatDateTime(u.last_login_at))}</td>
        <td>${escape(u.last_login_method || "—")}</td>
        <td>${formatDuration(u.total_session_seconds)}</td>
        <td>${u.activity_event_count}</td>
        <td>${u.meal_count}</td>
        <td>${formatBytes(u.data_bytes_saved)}</td>
        <td>${escape(u.preferred_language || "—")}</td>
        <td>${escape(u.last_ip || "—")}</td>
      </tr>`).join("");

    const sessBody = document.querySelector("#admin-sessions-table tbody");
    sessBody.innerHTML = sessions.map((s) => `
      <tr>
        <td>${escape(formatDateTime(s.logged_in_at))}</td>
        <td>${escape(s.user_email || s.user_id)}</td>
        <td>${escape(s.login_method)}</td>
        <td>${escape(s.ip_address || "—")}</td>
        <td>${escape(s.language || "—")}</td>
        <td>${formatDuration(s.duration_seconds)}</td>
        <td>${escape(s.client)}</td>
      </tr>`).join("");

    const actBody = document.querySelector("#admin-activity-table tbody");
    actBody.innerHTML = activity.map((e) => `
      <tr>
        <td>${escape(formatDateTime(e.created_at))}</td>
        <td>${escape(e.user_email || e.user_id)}</td>
        <td>${escape(e.event_type)}</td>
        <td>${escape(e.path || "—")}</td>
        <td>${escape(e.ip_address || "—")}</td>
        <td>${escape(e.language || "—")}</td>
        <td>${e.bytes_saved != null ? formatBytes(e.bytes_saved) : "—"}</td>
      </tr>`).join("");
  } catch (e) {
    overviewEl.innerHTML = `<p class="error">${escape(e.message || String(e))}</p>`;
  }
}

(async function bootstrap() {
  await I18n.initLanguage();
  initSettings();
  initReportsControls();
  initHistoryPagination();
  if (tokens.access) {
    await loadUserAndPrefs();
    await checkAdminAccess();
    Activity.startHeartbeat();
  }
  render();
})();
