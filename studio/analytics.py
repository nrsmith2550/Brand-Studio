"""Learn what works for YOUR account from an analytics export.

Works with CSV/XLSX exports from Instagram (Meta Business Suite → Insights → Content → Export),
TikTok (Analytics → Content → Download), or any spreadsheet you keep yourself. Column names are
matched loosely, so "Publish time", "Date posted", "Likes", "Reactions", "Reach", "Views" etc. all work.
"""
from __future__ import annotations

import re
from collections import defaultdict

import pandas as pd

ALIASES = {
    "date": ["publish time", "publish_time", "date posted", "posted", "date", "time", "created", "post time"],
    "type": ["post type", "type", "format", "media type", "content type"],
    "caption": ["description", "caption", "title", "text", "post"],
    "likes": ["likes", "reactions", "hearts"],
    "comments": ["comments"],
    "shares": ["shares", "reposts"],
    "saves": ["saves", "saved", "bookmarks"],
    "reach": ["reach", "views", "impressions", "plays", "video views"],
    "followers_gained": ["follows", "followers gained", "new followers"],
}


def _find(cols: list[str], names: list[str]) -> str | None:
    low = {c.lower().strip(): c for c in cols}
    for n in names:
        if n in low:
            return low[n]
    for n in names:
        for lc, orig in low.items():
            if n in lc:
                return orig
    return None


def load(path: str) -> pd.DataFrame:
    if str(path).lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(path)
    else:
        try:
            df = pd.read_csv(path)
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding="utf-16", sep=None, engine="python")
    return normalize(df)


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    cols = list(df.columns)
    out = pd.DataFrame()
    used = set()
    for key, names in ALIASES.items():
        c = _find([x for x in cols if x not in used], names)
        if c is not None:
            out[key] = df[c]
            used.add(c)
    for k in ["likes", "comments", "shares", "saves", "reach", "followers_gained"]:
        if k in out:
            out[k] = pd.to_numeric(out[k].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
        else:
            out[k] = 0
    if "date" in out:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
    if "caption" not in out:
        out["caption"] = ""
    out["caption"] = out["caption"].fillna("").astype(str)
    if "type" not in out:
        out["type"] = "unknown"
    out["type"] = out["type"].fillna("unknown").astype(str).str.strip().str.title()
    out["engagement"] = out["likes"] + out["comments"] + 2 * out["shares"] + 2 * out["saves"]
    out["eng_rate"] = (out["engagement"] / out["reach"].where(out["reach"] > 0)) * 100
    return out


def _rank(df: pd.DataFrame, key: str, metric: str, min_n: int = 2) -> pd.DataFrame:
    g = df.groupby(key)[metric].agg(["mean", "count"]).reset_index()
    g = g[g["count"] >= min_n].sort_values("mean", ascending=False)
    g["mean"] = g["mean"].round(2)
    return g.rename(columns={"mean": f"avg_{metric}", "count": "posts"})


def analyze(df: pd.DataFrame) -> dict:
    metric = "eng_rate" if df["eng_rate"].notna().sum() >= max(3, len(df) // 2) else "engagement"
    res: dict = {"posts": len(df), "metric": metric}
    res["by_type"] = _rank(df, "type", metric, 1)

    if "date" in df and df["date"].notna().any():
        d = df.dropna(subset=["date"]).copy()
        d["weekday"] = d["date"].dt.day_name()
        d["hour"] = d["date"].dt.hour
        res["by_weekday"] = _rank(d, "weekday", metric)
        res["by_hour"] = _rank(d, "hour", metric)

    # hashtags
    tag_scores = defaultdict(list)
    for cap, val in zip(df["caption"], df[metric]):
        for t in set(re.findall(r"#\w+", cap.lower())):
            tag_scores[t].append(val)
    tags = [(t, round(sum(v) / len(v), 2), len(v)) for t, v in tag_scores.items() if len(v) >= 2]
    res["hashtags"] = pd.DataFrame(sorted(tags, key=lambda x: -x[1])[:15],
                                   columns=["hashtag", f"avg_{metric}", "posts"])

    # caption length
    lens = df["caption"].str.len()
    df = df.assign(cap_len=pd.cut(lens, [-1, 60, 150, 400, 10_000],
                                  labels=["very short (<60)", "short (60-150)", "medium (150-400)", "long (400+)"]))
    res["by_caption_length"] = _rank(df.astype({"cap_len": str}), "cap_len", metric, 1)

    # question / CTA effect
    df = df.assign(has_question=df["caption"].str.contains(r"\?"))
    res["question_effect"] = _rank(df.astype({"has_question": str}), "has_question", metric, 1)

    top = df.sort_values(metric, ascending=False).head(5)
    res["top_posts"] = top[["type", "caption", "likes", "comments", "shares", "saves", "reach", metric]].assign(
        caption=top["caption"].str.slice(0, 120))
    bottom = df.sort_values(metric, ascending=True).head(3)
    res["bottom_posts"] = bottom[["type", "caption", metric]].assign(caption=bottom["caption"].str.slice(0, 120))
    return res


def summary_text(res: dict) -> str:
    """Plain-text summary the LLM can reason over."""
    m = res["metric"]
    label = "engagement rate %" if m == "eng_rate" else "engagement (likes+comments+2×shares+2×saves)"
    parts = [f"Account analytics over {res['posts']} posts. Metric: {label}."]

    def block(title, key):
        df = res.get(key)
        if df is not None and len(df):
            parts.append(f"{title}:\n" + df.head(8).to_string(index=False))

    block("By post format", "by_type")
    block("By weekday", "by_weekday")
    block("By hour posted (24h)", "by_hour")
    block("Hashtags (used 2+ times)", "hashtags")
    block("By caption length", "by_caption_length")
    block("Caption asks a question?", "question_effect")
    block("Top posts", "top_posts")
    block("Weakest posts", "bottom_posts")
    return "\n\n".join(parts)


def summary_markdown(res: dict) -> str:
    m = res["metric"]
    out = [f"### Your account: {res['posts']} posts analysed",
           f"Ranking by **{'engagement rate (%)' if m == 'eng_rate' else 'total engagement'}**."]

    def best(key, label):
        df = res.get(key)
        if df is not None and len(df):
            out.append(f"- **Best {label}:** {df.iloc[0, 0]} (avg {df.iloc[0, 1]}, {int(df.iloc[0, 2])} posts)")

    best("by_type", "format")
    best("by_weekday", "day")
    best("by_hour", "hour to post")
    best("by_caption_length", "caption length")
    best("hashtags", "hashtag")
    return "\n".join(out)
