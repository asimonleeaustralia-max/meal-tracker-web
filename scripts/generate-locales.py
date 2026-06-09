#!/usr/bin/env python3
"""Generate locale JSON files from en.json using Google Translate."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from deep_translator import GoogleTranslator

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "services/web-frontend/public/locales"

# App code -> Google Translate target code
TARGETS = {
    "hi": "hi", "es": "es", "ar": "ar", "bn": "bn", "pt": "pt", "ru": "ru",
    "ur": "ur", "id": "id", "ja": "ja", "sw": "sw", "mr": "mr", "te": "te",
    "tr": "tr", "ta": "ta", "vi": "vi", "ko": "ko", "it": "it", "gu": "gu",
    "pl": "pl", "uk": "uk", "ml": "ml", "kn": "kn", "or": "or", "my": "my",
    "pa": "pa", "ro": "ro", "nl": "nl", "el": "el", "cs": "cs", "sv": "sv",
    "hu": "hu", "he": "iw", "da": "da", "fi": "fi", "nb": "no", "sk": "sk",
    "bg": "bg", "hr": "hr", "sr": "sr", "lt": "lt", "sl": "sl", "lv": "lv",
    "et": "et", "ms": "ms", "fa": "fa",
}

PLACEHOLDER_RE = re.compile(r"\{[^}]+\}")


def protect(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def repl(m: re.Match[str]) -> str:
        tokens.append(m.group(0))
        return f"__PH{len(tokens) - 1}__"

    return PLACEHOLDER_RE.sub(repl, text), tokens


def restore(text: str, tokens: list[str]) -> str:
    for i, tok in enumerate(tokens):
        text = text.replace(f"__PH{i}__", tok)
        text = text.replace(f"__PH{i} __", tok)
        text = text.replace(f"__PH{i}__", tok)
    return text


def translate_obj(en: dict[str, str], target: str) -> dict[str, str]:
    translator = GoogleTranslator(source="en", target=target)
    out: dict[str, str] = {}
    keys = list(en.keys())
    for i, key in enumerate(keys):
        raw = en[key]
        protected, tokens = protect(raw)
        try:
            translated = translator.translate(protected)
            out[key] = restore(translated, tokens)
        except Exception as exc:
            print(f"  warn {key}: {exc}", file=sys.stderr)
            out[key] = raw
        if (i + 1) % 25 == 0:
            print(f"    {i + 1}/{len(keys)}")
            time.sleep(0.3)
        else:
            time.sleep(0.05)
    return out


def merge_existing(lang: str, en: dict[str, str]) -> dict[str, str]:
    path = LOCALES / f"{lang}.json"
    if not path.exists():
        return {}
    existing = json.loads(path.read_text(encoding="utf-8"))
    return {k: existing[k] for k in en if k in existing}


def main() -> None:
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    LOCALES.mkdir(parents=True, exist_ok=True)

    # Fill gaps in hand-translated locales
    for lang in ("de", "fr", "th", "zh"):
        existing = merge_existing(lang, en)
        missing = [k for k in en if k not in existing]
        if not missing:
            print(f"{lang}: complete ({len(existing)} keys)")
            continue
        print(f"{lang}: translating {len(missing)} missing keys")
        partial = {k: en[k] for k in missing}
        gt = "de" if lang == "de" else "fr" if lang == "fr" else "th" if lang == "th" else "zh-CN"
        added = translate_obj(partial, gt)
        existing.update(added)
        (LOCALES / f"{lang}.json").write_text(
            json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{lang}: done ({len(existing)} keys)")

    for lang, gt in TARGETS.items():
        out_path = LOCALES / f"{lang}.json"
        if out_path.exists() and len(json.loads(out_path.read_text())) >= len(en) - 2:
            print(f"{lang}: skip (exists)")
            continue
        print(f"{lang}: translating {len(en)} keys -> {gt}")
        translated = translate_obj(en, gt)
        out_path.write_text(json.dumps(translated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{lang}: done")
        time.sleep(0.5)

    print("All locales generated.")


if __name__ == "__main__":
    main()
