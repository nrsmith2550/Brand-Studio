"""Brand profile + app settings, stored as plain JSON next to the app."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # where the code lives
# Where YOUR data lives (brand profile, settings, database, images, research cache).
# Defaults to the project folder; set BRAND_STUDIO_DATA to keep data elsewhere (tests use a temp dir).
DATA_DIR = Path(os.environ.get("BRAND_STUDIO_DATA", ROOT)).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True)
BRAND_FILE = DATA_DIR / "brand.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
OUTPUT_DIR = DATA_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

DEFAULT_BRAND = {
    "name": "Your Brand",
    "handle": "@yourbrand",
    "one_liner": "Streetwear made in small batches for people who skate, create and stay up late.",
    "products": "Heavyweight tees, hoodies, cargo pants, caps",
    "price_point": "Mid ($35-$120)",
    "audience": "18-30, urban, into skate, music and thrifting; values quality and limited drops",
    "voice": "Confident, playful, a little underground. Short sentences. No corporate speak.",
    "words_to_avoid": "cheap, fast fashion, guys",
    "values": "Small batch, ethically made, community-first",
    "competitors": "Brands you admire or compete with, comma separated",
    "platforms": ["Instagram", "TikTok"],
    "core_hashtags": "#streetwear #smallbrand",
    "colors": {"primary": "#111111", "secondary": "#F2EDE4", "accent": "#E4572E"},
    "visual_style": "35mm film look, natural light, urban backdrops, candid poses, muted tones with one pop of accent color",
    "font_path": "",
    "logo_path": "",
}

DEFAULT_SETTINGS = {
    "ollama_url": "http://localhost:11434",
    "text_model": "llama3.1:8b",
    "image_model": "sdxl-base",
    "speed": "Fast",
    "research_keywords": "streetwear trends, graphic tee trends, fashion tiktok trends",
    "subreddits": "streetwear, malefashionadvice, femalefashionadvice, smallbusiness",
    "rss_feeds": "https://hypebeast.com/feed\nhttps://www.highsnobiety.com/feed/",
}


def _load(path: Path, default: dict) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            merged = {**default, **data}
            if isinstance(default.get("colors"), dict):
                merged["colors"] = {**default["colors"], **data.get("colors", {})}
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return json.loads(json.dumps(default))


def load_brand() -> dict:
    return _load(BRAND_FILE, DEFAULT_BRAND)


def save_brand(brand: dict) -> None:
    BRAND_FILE.write_text(json.dumps(brand, indent=2), encoding="utf-8")


def load_settings() -> dict:
    return _load(SETTINGS_FILE, DEFAULT_SETTINGS)


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def total_ram_gb() -> float:
    """Physical memory in GB (works on macOS, Linux and Windows)."""
    try:
        import os
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3
    except (ValueError, OSError, AttributeError):
        try:
            import ctypes

            class M(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("p", ctypes.c_ulong), ("t", ctypes.c_ulonglong),
                            ("a", ctypes.c_ulonglong)] + [(f"x{i}", ctypes.c_ulonglong) for i in range(5)]
            m = M(); m.l = ctypes.sizeof(M)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.t / 1024**3
        except Exception:  # noqa: BLE001
            return 16.0


def split_list(text: str) -> list[str]:
    """Split comma / newline separated text into a clean list."""
    if not text:
        return []
    parts = [p.strip() for chunk in text.split("\n") for p in chunk.split(",")]
    return [p for p in parts if p]


def brand_brief(brand: dict) -> str:
    """Compact brand description injected into every LLM prompt."""
    c = brand.get("colors", {})
    return (
        f"BRAND: {brand['name']} ({brand.get('handle','')})\n"
        f"What it is: {brand.get('one_liner','')}\n"
        f"Products: {brand.get('products','')} | Price point: {brand.get('price_point','')}\n"
        f"Audience: {brand.get('audience','')}\n"
        f"Voice: {brand.get('voice','')}\n"
        f"Never use these words: {brand.get('words_to_avoid','')}\n"
        f"Values: {brand.get('values','')}\n"
        f"Competitors / inspiration: {brand.get('competitors','')}\n"
        f"Platforms: {', '.join(brand.get('platforms', []))}\n"
        f"Core hashtags: {brand.get('core_hashtags','')}\n"
        f"Visual style: {brand.get('visual_style','')}\n"
        f"Brand colors: primary {c.get('primary')}, secondary {c.get('secondary')}, accent {c.get('accent')}"
    )
