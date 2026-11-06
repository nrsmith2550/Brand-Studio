"""Local SQLite storage: history of everything generated, plus the Ideas library."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

from .config import DATA_DIR

DB = DATA_DIR / "studio.db"
STATUSES = ["New", "Favorite", "Used", "Archived"]


def _conn():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, kind TEXT, created TEXT, title TEXT, body TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS ideas (
        id INTEGER PRIMARY KEY, created TEXT, title TEXT, format TEXT, platform TEXT, goal TEXT,
        status TEXT DEFAULT 'New', notes TEXT DEFAULT '', used_on TEXT DEFAULT '', data TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    if not c.execute("SELECT 1 FROM meta WHERE k='ideas_migrated'").fetchone():
        _migrate(c)
        c.execute("INSERT INTO meta VALUES ('ideas_migrated', '1')")
        c.commit()
    return c


def _migrate(c):
    """Copy ideas saved by earlier versions (whole batches in `items`) into the library."""
    for created, title, body in c.execute("SELECT created, title, body FROM items WHERE kind='ideas' ORDER BY id").fetchall():
        try:
            batch = json.loads(body)
        except json.JSONDecodeError:
            continue
        parts = [p.strip() for p in title.split("·")]
        platform = parts[1] if len(parts) > 1 else ""
        goal = parts[2] if len(parts) > 2 else ""
        for d in batch if isinstance(batch, list) else []:
            if isinstance(d, dict):
                c.execute("INSERT INTO ideas (created, title, format, platform, goal, data) VALUES (?,?,?,?,?,?)",
                          (created, str(d.get("title", "Idea"))[:200], str(d.get("format", "")), platform, goal,
                           json.dumps(d)))


# ---------------------------------------------------------------- history
def save(kind: str, title: str, body) -> None:
    with _conn() as c:
        c.execute("INSERT INTO items (kind, created, title, body) VALUES (?,?,?,?)",
                  (kind, datetime.now().isoformat(timespec="minutes"), title[:200],
                   body if isinstance(body, str) else json.dumps(body)))


def latest(kind: str) -> str:
    with _conn() as c:
        row = c.execute("SELECT body FROM items WHERE kind=? ORDER BY id DESC LIMIT 1", (kind,)).fetchone()
    return row[0] if row else ""


def history(limit: int = 50) -> list[list]:
    with _conn() as c:
        rows = c.execute("SELECT id, kind, created, title FROM items ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [list(r) for r in rows]


def get(item_id: int) -> str:
    with _conn() as c:
        row = c.execute("SELECT kind, body FROM items WHERE id=?", (int(item_id or 0),)).fetchone()
    if not row:
        return "_Not found._"
    kind, body = row
    if kind == "ideas":
        from .strategist import ideas_markdown
        return ideas_markdown(json.loads(body))
    return body


# ---------------------------------------------------------------- ideas library
def save_ideas(ideas: list[dict], platform: str = "", goal: str = "", status: str = "New") -> list[int]:
    ids = []
    now = datetime.now().isoformat(timespec="minutes")
    with _conn() as c:
        for d in ideas:
            cur = c.execute("INSERT INTO ideas (created, title, format, platform, goal, status, data) VALUES (?,?,?,?,?,?,?)",
                            (now, str(d.get("title", "Idea"))[:200], str(d.get("format", "")), platform, goal, status,
                             json.dumps(d)))
            ids.append(cur.lastrowid)
    return ids


def list_ideas(status: str = "All active", query: str = "", limit: int = 300) -> list[list]:
    sql = "SELECT id, status, title, format, platform, goal, created, used_on FROM ideas WHERE 1=1"
    args: list = []
    if status == "All active":
        sql += " AND status != 'Archived'"
    elif status and status != "Everything":
        sql += " AND status = ?"
        args.append(status)
    if query:
        sql += " AND (title LIKE ? OR data LIKE ? OR notes LIKE ?)"
        args += [f"%{query}%"] * 3
    sql += " ORDER BY CASE status WHEN 'Favorite' THEN 0 WHEN 'New' THEN 1 WHEN 'Used' THEN 2 ELSE 3 END, id DESC LIMIT ?"
    args.append(limit)
    with _conn() as c:
        rows = c.execute(sql, args).fetchall()
    star = {"Favorite": "⭐ Favorite", "Used": "✅ Used", "Archived": "🗄 Archived", "New": "🆕 New"}
    return [[r[0], star.get(r[1], r[1]), r[2], r[3], r[4], r[5], (r[6] or "")[:10], r[7] or ""] for r in rows]


def get_idea(idea_id) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT id, created, title, format, platform, goal, status, notes, used_on, data FROM ideas WHERE id=?",
                        (int(idea_id or 0),)).fetchone()
    if not row:
        return None
    meta = dict(zip(["id", "created", "title", "format", "platform", "goal", "status", "notes", "used_on"], row[:9]))
    data = json.loads(row[9] or "{}")
    return {**data, "_meta": meta}


def set_status(idea_id, status: str) -> None:
    used_on = date.today().isoformat() if status == "Used" else None
    with _conn() as c:
        if used_on:
            c.execute("UPDATE ideas SET status=?, used_on=? WHERE id=?", (status, used_on, int(idea_id)))
        else:
            c.execute("UPDATE ideas SET status=? WHERE id=?", (status, int(idea_id)))


def set_notes(idea_id, notes: str) -> None:
    with _conn() as c:
        c.execute("UPDATE ideas SET notes=? WHERE id=?", (notes, int(idea_id)))


def titles_with_status(status: str, limit: int = 25) -> list[str]:
    with _conn() as c:
        rows = c.execute("SELECT title, data FROM ideas WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)).fetchall()
    out = []
    for title, data in rows:
        hook = (json.loads(data or "{}").get("hook") or "")[:90]
        out.append(f"{title}: {hook}" if hook else title)
    return out


def counts() -> dict:
    with _conn() as c:
        return dict(c.execute("SELECT status, COUNT(*) FROM ideas GROUP BY status").fetchall())
