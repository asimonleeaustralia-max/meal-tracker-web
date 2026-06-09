#!/usr/bin/env python3
"""Generate any missing locale JSON files (parallel)."""
from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from deep_translator import GoogleTranslator

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "services/web-frontend/public/locales"

SUPPORTED = [
    "en", "zh", "hi", "es", "ar", "fr", "bn", "pt", "ru", "ur", "id", "de", "ja",
    "sw", "mr", "te", "tr", "ta", "vi", "ko", "it", "th", "gu", "pl", "uk", "ml",
    "kn", "or", "my", "pa", "ro", "nl", "el", "cs", "sv", "hu", "he", "da", "fi",
    "nb", "sk", "bg", "hr", "sr", "lt", "sl", "lv", "et", "ms", "fa",
]

TARGETS = {
    "zh": "zh-CN", "nb": "no", "he": "iw",
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
    return text


def translate_key(args: tuple[str, str, str]) -> tuple[str, str]:
    key, raw, gt = args
    protected, tokens = protect(raw)
    for attempt in range(3):
        try:
            out = GoogleTranslator(source="en", target=gt).translate(protected)
            return key, restore(out, tokens)
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return key, raw


def generate(lang: str, en: dict[str, str]) -> None:
    gt = TARGETS.get(lang, lang)
    print(f"{lang}: start ({gt})")
    jobs = [(k, v, gt) for k, v in en.items()]
    out: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(translate_key, job) for job in jobs]
        done = 0
        for fut in as_completed(futures):
            key, val = fut.result()
            out[key] = val
            done += 1
            if done % 40 == 0:
                print(f"  {lang}: {done}/{len(jobs)}")
    (LOCALES / f"{lang}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{lang}: done ({len(out)} keys)")


def main() -> None:
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    missing = [l for l in SUPPORTED if l != "en" and not (LOCALES / f"{l}.json").exists()]
    if not missing:
        print("All locales present.")
        return
    print("Missing:", ", ".join(missing))
    for lang in missing:
        generate(lang, en)
    print("Finished.")


if __name__ == "__main__":
    main()
