"""Free, key-less research sources.

- Web + news search via DuckDuckGo (the `ddgs` package)
- Reddit public JSON (top posts of the week from fashion subreddits)
- RSS feeds from fashion / streetwear publications
- Any page you paste a link to (competitor site, article, lookbook)

Everything fails soft: if one source is down or rate-limited, the rest still run.
Note: Instagram and TikTok don't offer free public data access and block scraping, so for
those platforms use your own analytics export (see analytics.py) plus notes you paste in.
"""
from __future__ import annotations

import html
import json
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

from .config import DATA_DIR

UA = {"User-Agent": "Mozilla/5.0 (local brand-studio research tool)"}


def _clean(text: str, limit: int = 300) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


# ---------------------------------------------------------------- web search
def web_search(query: str, max_results: int = 8, news: bool = False) -> list[dict]:
    try:
        try:
            from ddgs import DDGS  # current package name
        except ImportError:
            from duckduckgo_search import DDGS  # older name
        with DDGS() as d:
            rows = d.news(query, max_results=max_results) if news else d.text(query, max_results=max_results)
        out = []
        for r in rows or []:
            out.append({
                "source": "news" if news else "web",
                "title": _clean(r.get("title", ""), 160),
                "url": r.get("url") or r.get("href") or "",
                "snippet": _clean(r.get("body", "") or r.get("excerpt", "")),
                "date": r.get("date", ""),
            })
        return out
    except Exception as e:  # noqa: BLE001 — network sources fail in many ways
        return [{"source": "web", "error": f"Search failed for '{query}': {e}"}]


# ---------------------------------------------------------------- reddit
def reddit_top(subreddit: str, period: str = "week", limit: int = 15) -> list[dict]:
    sub = subreddit.strip().removeprefix("r/")
    url = f"https://www.reddit.com/r/{sub}/top.json?t={period}&limit={limit}"
    try:
        r = requests.get(url, headers=UA, timeout=15)
        r.raise_for_status()
        out = []
        for child in r.json()["data"]["children"]:
            p = child["data"]
            out.append({
                "source": f"r/{sub}",
                "title": _clean(p.get("title", ""), 200),
                "url": "https://reddit.com" + p.get("permalink", ""),
                "snippet": _clean(p.get("selftext", ""), 250),
                "score": p.get("score", 0),
                "comments": p.get("num_comments", 0),
            })
        return out
    except Exception as e:  # noqa: BLE001
        return [{"source": f"r/{sub}", "error": f"Reddit unavailable for r/{sub}: {e}"}]


# ---------------------------------------------------------------- rss
def rss(feed_url: str, limit: int = 12) -> list[dict]:
    try:
        r = requests.get(feed_url, headers=UA, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        out = []
        for it in items[:limit]:
            def g(tag):
                el = it.find(tag)
                if el is None:
                    el = it.find("{http://www.w3.org/2005/Atom}" + tag)
                return (el.text or el.get("href", "")) if el is not None else ""
            out.append({
                "source": re.sub(r"^https?://(www\.)?", "", feed_url).split("/")[0],
                "title": _clean(g("title"), 200),
                "url": g("link"),
                "snippet": _clean(g("description") or g("summary")),
                "date": g("pubDate") or g("updated"),
            })
        return out
    except Exception as e:  # noqa: BLE001
        return [{"source": feed_url, "error": f"Feed failed: {e}"}]


# ---------------------------------------------------------------- any page
def fetch_page(url: str, limit: int = 4000) -> dict:
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
        body = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", r.text)
        title = re.search(r"(?is)<title>(.*?)</title>", body)
        return {"source": "page", "url": url, "title": _clean(title.group(1) if title else url, 160),
                "snippet": _clean(body, limit)}
    except Exception as e:  # noqa: BLE001
        return {"source": "page", "url": url, "error": f"Couldn't load {url}: {e}"}


# ---------------------------------------------------------------- orchestrate
CACHE_FILE = DATA_DIR / "research_cache.json"


def _cache_load() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _fetch(kind: str, arg: str, per_source: int):
    if kind == "web":
        return web_search(arg, per_source)
    if kind == "news":
        return web_search(arg, per_source, news=True)
    if kind == "reddit":
        return reddit_top(arg, limit=per_source + 5)
    if kind == "rss":
        return rss(arg, limit=per_source + 5)
    return [fetch_page(arg)]


def _label(kind: str, arg: str) -> str:
    if kind == "rss":
        arg = re.sub(r"^https?://(www\.)?", "", arg).split("/")[0]
    return {"web": "web: ", "news": "news: ", "reddit": "r/", "rss": "", "page": ""}[kind] + arg[:40]


def gather(keywords: list[str], subreddits: list[str], feeds: list[str], urls: list[str],
           use_web=True, use_news=True, use_reddit=True, use_rss=True, progress=None,
           per_source: int = 8, cache_hours: float = 6) -> dict:
    """Fetch every source at the same time (much faster than one by one) and reuse anything
    fetched in the last `cache_hours` hours (0 = always fetch fresh)."""
    steps = []
    if use_web:
        steps += [("web", k) for k in keywords]
    if use_news:
        steps += [("news", k) for k in keywords]
    if use_reddit:
        steps += [("reddit", s) for s in subreddits]
    if use_rss:
        steps += [("rss", f) for f in feeds]
    steps += [("page", u) for u in urls]

    cache, now = _cache_load(), time.time()
    results: dict[tuple, list] = {}
    todo = []
    for kind, arg in steps:
        hit = cache.get(f"{kind}|{arg}")
        if cache_hours and hit and now - hit["t"] < cache_hours * 3600 and not any("error" in f for f in hit["rows"]):
            results[(kind, arg)] = hit["rows"]
        else:
            todo.append((kind, arg))
    cached = len(results)
    total = max(len(steps), 1)
    if progress:
        progress(cached / total, desc=f"{cached} of {len(steps)} sources reused from earlier · fetching {len(todo)}…")

    if todo:
        # Network-bound, so several at once is safe
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_fetch, k, a, per_source): (k, a) for k, a in todo}
            done = cached
            for fut in as_completed(futures):
                kind, arg = futures[fut]
                try:
                    rows = fut.result()
                except Exception as e:  # noqa: BLE001
                    rows = [{"source": kind, "error": f"{_label(kind, arg)} failed: {e}"}]
                results[(kind, arg)] = rows
                if not any("error" in f for f in rows):
                    cache[f"{kind}|{arg}"] = {"t": now, "rows": rows}
                done += 1
                if progress:
                    progress(done / total, desc=f"Source {done} of {len(steps)} done · {_label(kind, arg)}")
        try:
            CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
        except OSError:
            pass

    findings = [f for kind, arg in steps for f in results.get((kind, arg), [])]
    ok = [f for f in findings if "error" not in f]
    errors = [f["error"] for f in findings if "error" in f]
    # de-duplicate by URL / title
    seen, unique = set(), []
    for f in ok:
        key = f.get("url") or f.get("title")
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    # Reddit posts with the most engagement first, then everything else
    unique.sort(key=lambda f: f.get("score", 0) + 3 * f.get("comments", 0), reverse=True)
    return {"when": datetime.now().isoformat(timespec="minutes"), "findings": unique, "errors": errors,
            "cached": cached, "fetched": len(todo)}


def findings_digest(findings: list[dict], max_chars: int = 12000) -> str:
    """Turn findings into a compact text block for the LLM."""
    lines, total = [], 0
    for f in findings:
        eng = f" [{f['score']} upvotes, {f['comments']} comments]" if "score" in f else ""
        line = f"- ({f['source']}){eng} {f['title']} — {f.get('snippet','')[:220]}"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)


def findings_markdown(findings: list[dict], limit: int = 60) -> str:
    rows = []
    for f in findings[:limit]:
        eng = f" · ⬆{f['score']} 💬{f['comments']}" if "score" in f else ""
        title = f["title"] or f["url"]
        link = f"[{title}]({f['url']})" if f.get("url") else title
        rows.append(f"- **{f['source']}**{eng} — {link}")
    return "\n".join(rows) or "_No findings._"
