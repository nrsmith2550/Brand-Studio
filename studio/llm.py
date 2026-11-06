"""Tiny client for a local Ollama server (https://ollama.com). No API keys, no tokens billed."""
from __future__ import annotations

import json
import re
import threading

import requests

from .config import load_settings, total_ram_gb

# Speed modes trade a little depth for a lot of time. Smaller prompts and context windows are the
# biggest win on laptops: the model has to read every character before it writes the first word.
SPEED_MODES = {
    "Fast": {"ctx": 4096, "digest_chars": 5000, "per_source": 5,
             "note": "Quickest. Reads the top ~5,000 characters of findings."},
    "Balanced": {"ctx": 6144, "digest_chars": 8000, "per_source": 8,
                 "note": "Middle ground."},
    "Thorough": {"ctx": 8192, "digest_chars": 12000, "per_source": 10,
                 "note": "Reads the most, slowest. Best with a bigger model."},
}
# Keep the model in memory between clicks so it doesn't reload each time. On 8 GB machines keep it
# only briefly, because the image model needs that memory.
LOW_MEMORY = total_ram_gb() <= 8.5
KEEP_ALIVE = "5m" if LOW_MEMORY else "30m"


class LLMError(RuntimeError):
    pass


def _base() -> tuple[str, str]:
    s = load_settings()
    return s["ollama_url"].rstrip("/"), s["text_model"]


def speed() -> dict:
    return SPEED_MODES.get(load_settings().get("speed", "Fast"), SPEED_MODES["Fast"])


def list_models() -> list[str]:
    url, _ = _base()
    try:
        r = requests.get(f"{url}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except requests.RequestException:
        return []


def health() -> str:
    url, model = _base()
    models = list_models()
    if not models:
        return (f"❌ Can't reach Ollama at {url}. Install it from ollama.com, then run: "
                f"`ollama pull {model}`")
    if not any(m == model or m.split(":")[0] == model.split(":")[0] for m in models):
        return f"⚠️ Ollama is running but `{model}` isn't downloaded. Run: `ollama pull {model}`"
    return f"✅ Ollama running · text model `{model}` ready"


def unload() -> None:
    """Free the text model's memory right away (called before image generation)."""
    url, model = _base()
    try:
        requests.post(f"{url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=30)
    except requests.RequestException:
        pass


def warmup() -> None:
    """Load the model into memory in the background so the first click is fast."""
    def _go():
        url, model = _base()
        try:
            requests.post(f"{url}/api/generate", json={"model": model, "keep_alive": KEEP_ALIVE}, timeout=300)
        except requests.RequestException:
            pass
    threading.Thread(target=_go, daemon=True).start()


def _payload(system, user, temperature, json_mode, num_ctx, stream):
    url, model = _base()
    p = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": stream,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": temperature, "num_ctx": num_ctx or speed()["ctx"]},
    }
    if json_mode:
        p["format"] = "json"
    return url, model, p


def chat(system: str, user: str, temperature: float = 0.7, json_mode: bool = False,
         num_ctx: int | None = None) -> str:
    url, model, payload = _payload(system, user, temperature, json_mode, num_ctx, False)
    try:
        r = requests.post(f"{url}/api/chat", json=payload, timeout=600)
        r.raise_for_status()
    except requests.RequestException as e:
        raise LLMError(f"Ollama request failed: {e}. Is Ollama running and is `{model}` pulled?") from e
    return r.json()["message"]["content"].strip()


def chat_stream(system: str, user: str, temperature: float = 0.7, json_mode: bool = False,
                num_ctx: int | None = None):
    """Yield the reply piece by piece as the local model writes it."""
    url, model, payload = _payload(system, user, temperature, json_mode, num_ctx, True)
    try:
        with requests.post(f"{url}/api/chat", json=payload, stream=True, timeout=600) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                d = json.loads(line)
                if "error" in d:
                    raise LLMError(f"Ollama error: {d['error']}")
                yield d.get("message", {}).get("content", "")
                if d.get("done"):
                    break
    except requests.RequestException as e:
        raise LLMError(f"Ollama request failed: {e}. Is Ollama running and is `{model}` pulled?") from e


def chat_json(system: str, user: str, temperature: float = 0.7):
    """Ask for JSON and parse it robustly (local models occasionally wrap it in prose)."""
    raw = chat(system, user, temperature=temperature, json_mode=True)
    return parse_json(raw)


def parse_json(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"(\{.*\}|\[.*\])", raw, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    raise LLMError("The model didn't return valid JSON. Try again, or switch to a larger model.")
