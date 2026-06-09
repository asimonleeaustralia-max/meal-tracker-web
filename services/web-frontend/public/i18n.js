/**
 * Client-side i18n for MacrosSimple web UI.
 * Language: cookie (preferred) -> browser Accept-Language -> English.
 * Locale strings loaded from /locales/{code}.json on demand.
 */
(function (global) {
  const COOKIE_KEY = "macrossimple_lang";
  const COOKIE_MAX_AGE = 365 * 24 * 60 * 60;
  const LOCALE_VERSION = "40";
  const DEFAULT_LANG = "en";

  const SUPPORTED = {
    en: { label: "English", locale: "en" },
    zh: { label: "中文", locale: "zh-CN" },
    hi: { label: "हिन्दी", locale: "hi" },
    es: { label: "Español", locale: "es" },
    ar: { label: "العربية", locale: "ar" },
    fr: { label: "Français", locale: "fr" },
    bn: { label: "বাংলা", locale: "bn" },
    pt: { label: "Português", locale: "pt" },
    ru: { label: "Русский", locale: "ru" },
    ur: { label: "اردو", locale: "ur" },
    id: { label: "Bahasa Indonesia", locale: "id" },
    de: { label: "Deutsch", locale: "de" },
    ja: { label: "日本語", locale: "ja" },
    sw: { label: "Kiswahili", locale: "sw" },
    mr: { label: "मराठी", locale: "mr" },
    te: { label: "తెలుగు", locale: "te" },
    tr: { label: "Türkçe", locale: "tr" },
    ta: { label: "தமிழ்", locale: "ta" },
    vi: { label: "Tiếng Việt", locale: "vi" },
    ko: { label: "한국어", locale: "ko" },
    it: { label: "Italiano", locale: "it" },
    th: { label: "ไทย", locale: "th" },
    gu: { label: "ગુજરાતી", locale: "gu" },
    pl: { label: "Polski", locale: "pl" },
    uk: { label: "Українська", locale: "uk" },
    ml: { label: "മലയാളം", locale: "ml" },
    kn: { label: "ಕನ್ನಡ", locale: "kn" },
    or: { label: "ଓଡ଼ିଆ", locale: "or" },
    my: { label: "မြန်မာဘာသာ", locale: "my" },
    pa: { label: "ਪੰਜਾਬੀ", locale: "pa" },
    ro: { label: "Română", locale: "ro" },
    nl: { label: "Nederlands", locale: "nl" },
    el: { label: "Ελληνικά", locale: "el" },
    cs: { label: "Čeština", locale: "cs" },
    sv: { label: "Svenska", locale: "sv" },
    hu: { label: "Magyar", locale: "hu" },
    he: { label: "עברית", locale: "he" },
    da: { label: "Dansk", locale: "da" },
    fi: { label: "Suomi", locale: "fi" },
    nb: { label: "Norsk", locale: "nb" },
    sk: { label: "Slovenčina", locale: "sk" },
    bg: { label: "Български", locale: "bg" },
    hr: { label: "Hrvatski", locale: "hr" },
    sr: { label: "Српски", locale: "sr" },
    lt: { label: "Lietuvių", locale: "lt" },
    sl: { label: "Slovenščina", locale: "sl" },
    lv: { label: "Latviešu", locale: "lv" },
    et: { label: "Eesti", locale: "et" },
    ms: { label: "Bahasa Melayu", locale: "ms" },
    fa: { label: "فارسی", locale: "fa" },
  };

  const MESSAGES = {};
  const loading = new Map();
  let currentLang = DEFAULT_LANG;
  const listeners = [];

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : null;
  }

  function setCookie(name, value) {
    const secure = location.protocol === "https:" ? ";Secure" : "";
    document.cookie = `${name}=${encodeURIComponent(value)};path=/;max-age=${COOKIE_MAX_AGE};SameSite=Lax${secure}`;
  }

  function readStoredLanguage() {
    const fromCookie = getCookie(COOKIE_KEY);
    if (fromCookie) return fromCookie;
    try {
      const legacy = localStorage.getItem(COOKIE_KEY);
      if (legacy) {
        setCookie(COOKIE_KEY, legacy);
        return legacy;
      }
    } catch (_) { /* ignore */ }
    return null;
  }

  function detectBrowserLanguage() {
    const candidates = navigator.languages?.length
      ? navigator.languages
      : [navigator.language || DEFAULT_LANG];
    for (const tag of candidates) {
      const base = String(tag).toLowerCase().split("-")[0];
      if (SUPPORTED[base]) return base;
    }
    return DEFAULT_LANG;
  }

  function normalizeLang(code) {
    if (!code) return DEFAULT_LANG;
    const base = String(code).toLowerCase().split("-")[0];
    return SUPPORTED[base] ? base : DEFAULT_LANG;
  }

  async function loadLocale(lang) {
    const code = normalizeLang(lang);
    if (MESSAGES[code]) return MESSAGES[code];
    if (loading.has(code)) return loading.get(code);

    const promise = (async () => {
      try {
        const res = await fetch(`/locales/${code}.json?v=${LOCALE_VERSION}`);
        if (!res.ok) throw new Error(`locale ${code}: ${res.status}`);
        MESSAGES[code] = await res.json();
      } catch (_) {
        if (code !== DEFAULT_LANG) {
          await loadLocale(DEFAULT_LANG);
          MESSAGES[code] = { ...MESSAGES[DEFAULT_LANG] };
        } else {
          MESSAGES[code] = { app_title: "MacrosSimple" };
        }
      }
      loading.delete(code);
      return MESSAGES[code];
    })();

    loading.set(code, promise);
    return promise;
  }

  function getLanguage() {
    return currentLang;
  }

  function getLocale() {
    return SUPPORTED[currentLang]?.locale || "en";
  }

  function t(key, params) {
    const dict = MESSAGES[currentLang] || MESSAGES.en || {};
    const fallback = MESSAGES.en || {};
    let text = dict[key] ?? fallback[key] ?? key;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        text = text.replaceAll(`{${k}}`, String(v));
      }
    }
    return text;
  }

  async function setLanguage(lang) {
    const next = normalizeLang(lang);
    const changed = next !== currentLang;
    await loadLocale(next);
    if (changed) currentLang = next;
    setCookie(COOKIE_KEY, currentLang);
    try { localStorage.setItem(COOKIE_KEY, currentLang); } catch (_) { /* ignore */ }
    applyLanguage();
    if (changed) listeners.forEach((fn) => fn(currentLang));
  }

  function onLanguageChange(fn) {
    listeners.push(fn);
    return () => {
      const i = listeners.indexOf(fn);
      if (i >= 0) listeners.splice(i, 1);
    };
  }

  function applyStaticTranslations(root) {
    const scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.dataset.i18n;
      if (key) el.textContent = t(key);
    });
    scope.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    scope.querySelectorAll("[data-i18n-title]").forEach((el) => {
      el.title = t(el.dataset.i18nTitle);
    });
    scope.querySelectorAll("[data-i18n-aria]").forEach((el) => {
      el.setAttribute("aria-label", t(el.dataset.i18nAria));
    });
    scope.querySelectorAll("[data-tooltip-key]").forEach((el) => {
      const key = el.dataset.tooltipKey;
      if (key) {
        el.title = t(key);
        el.setAttribute("aria-label", t(key));
      }
    });
    scope.querySelectorAll("select[data-i18n-option]").forEach((sel) => {
      for (const opt of sel.options) {
        const k = opt.dataset.i18nKey;
        if (k) opt.textContent = t(k);
      }
    });
    document.title = t("app_title");
    document.documentElement.lang = getLocale();
    const rtl = ["ar", "he", "ur", "fa"];
    document.documentElement.dir = rtl.includes(currentLang) ? "rtl" : "ltr";
  }

  function applyFieldLabels() {
    document.querySelectorAll("#add-meal-form .field-row").forEach((row) => {
      const inp = row.querySelector('input[type="number"][name]');
      const lbl = row.querySelector(".field-label");
      if (!inp || !lbl) return;
      const key = `field_${inp.name}`;
      if (MESSAGES.en?.[key] || MESSAGES[currentLang]?.[key]) lbl.textContent = t(key);
    });
    document.querySelectorAll("#add-meal-form details > summary[data-i18n]").forEach((s) => {
      s.textContent = t(s.dataset.i18n);
    });
  }

  function applyLanguage() {
    applyStaticTranslations();
    applyFieldLabels();
    updateGuessToggleLabels();
  }

  function updateGuessToggleLabels() {
    document.querySelectorAll(".guess-toggle .guess-state").forEach((el) => {
      const cb = el.closest(".guess-toggle")?.querySelector('input[type="checkbox"]');
      if (cb) el.textContent = cb.checked ? t("guess") : t("accurate");
    });
  }

  async function initLanguage() {
    await loadLocale(DEFAULT_LANG);
    const stored = readStoredLanguage();
    currentLang = normalizeLang(stored || detectBrowserLanguage());
    await loadLocale(currentLang);
    applyLanguage();
  }

  global.I18n = {
    SUPPORTED,
    t,
    getLanguage,
    getLocale,
    setLanguage,
    onLanguageChange,
    applyLanguage,
    applyStaticTranslations,
    applyFieldLabels,
    updateGuessToggleLabels,
    initLanguage,
    loadLocale,
  };
})(window);
