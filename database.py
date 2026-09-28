"""SQLite persistence for articles and source health."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

DB_PATH = Path(__file__).resolve().parent / "data" / "veille.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guid TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'autre',
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    is_favorite INTEGER NOT NULL DEFAULT 0,
    is_read INTEGER NOT NULL DEFAULT 0,
    extra TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_fav ON articles(is_favorite);
CREATE INDEX IF NOT EXISTS idx_articles_read ON articles(is_read);

CREATE TABLE IF NOT EXISTS source_status (
    source_id TEXT PRIMARY KEY,
    last_ok TEXT,
    last_error TEXT,
    last_count INTEGER DEFAULT 0,
    ok INTEGER DEFAULT 1
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def row_to_article(row: aiosqlite.Row) -> dict[str, Any]:
    extra = {}
    try:
        extra = json.loads(row["extra"] or "{}")
    except json.JSONDecodeError:
        extra = {}
    return {
        "id": row["id"],
        "guid": row["guid"],
        "url": row["url"],
        "title": row["title"],
        "summary": row["summary"],
        "source_id": row["source_id"],
        "source_name": row["source_name"],
        "category": row["category"],
        "published_at": row["published_at"],
        "fetched_at": row["fetched_at"],
        "is_favorite": bool(row["is_favorite"]),
        "is_read": bool(row["is_read"]),
        "extra": extra,
    }


class Database:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA foreign_keys=ON")
        await self.db.executescript(SCHEMA)
        await self.db.commit()

    async def close(self) -> None:
        if self.db:
            await self.db.close()
            self.db = None

    async def insert_articles(self, articles: list[dict]) -> list[dict]:
        """Insert new articles. Returns the ones that were actually inserted."""
        assert self.db
        inserted: list[dict] = []
        now = utcnow()
        for art in articles:
            extra = art.get("extra") or {}
            if not isinstance(extra, str):
                extra = json.dumps(extra, ensure_ascii=False)
            try:
                cur = await self.db.execute(
                    """
                    INSERT INTO articles
                    (guid, url, title, summary, source_id, source_name,
                     category, published_at, fetched_at, extra)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        art["guid"],
                        art["url"],
                        art["title"],
                        art.get("summary") or "",
                        art["source_id"],
                        art["source_name"],
                        art.get("category") or "autre",
                        art.get("published_at"),
                        now,
                        extra,
                    ),
                )
                art_out = dict(art)
                art_out["id"] = cur.lastrowid
                art_out["fetched_at"] = now
                art_out["is_favorite"] = False
                art_out["is_read"] = False
                if not isinstance(art_out.get("extra"), dict):
                    try:
                        art_out["extra"] = json.loads(art_out.get("extra") or "{}")
                    except json.JSONDecodeError:
                        art_out["extra"] = {}
                inserted.append(art_out)
            except aiosqlite.IntegrityError:
                continue
        await self.db.commit()
        return inserted

    async def list_articles(
        self,
        *,
        category: str | None = None,
        source_id: str | None = None,
        q: str | None = None,
        favorites: bool = False,
        unread: bool = False,
        offset: int = 0,
        limit: int = 30,
    ) -> tuple[list[dict], int]:
        assert self.db
        where = ["1=1"]
        params: list[Any] = []
        if category and category not in ("all", "tous"):
            where.append("category = ?")
            params.append(category)
        if source_id:
            where.append("source_id = ?")
            params.append(source_id)
        if favorites:
            where.append("is_favorite = 1")
        if unread:
            where.append("is_read = 0")
        if q:
            where.append("(title LIKE ? OR summary LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like])
        clause = " AND ".join(where)
        cur = await self.db.execute(
            f"SELECT COUNT(*) AS n FROM articles WHERE {clause}", params
        )
        total = int((await cur.fetchone())["n"])
        cur = await self.db.execute(
            f"""
            SELECT * FROM articles
            WHERE {clause}
            ORDER BY COALESCE(published_at, fetched_at) DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        )
        rows = await cur.fetchall()
        return [row_to_article(r) for r in rows], total

    async def get_article(self, article_id: int) -> dict | None:
        assert self.db
        cur = await self.db.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,)
        )
        row = await cur.fetchone()
        return row_to_article(row) if row else None

    async def toggle_favorite(self, article_id: int) -> dict | None:
        assert self.db
        await self.db.execute(
            "UPDATE articles SET is_favorite = 1 - is_favorite WHERE id = ?",
            (article_id,),
        )
        await self.db.commit()
        return await self.get_article(article_id)

    async def set_read(self, article_id: int, is_read: bool = True) -> dict | None:
        assert self.db
        await self.db.execute(
            "UPDATE articles SET is_read = ? WHERE id = ?",
            (1 if is_read else 0, article_id),
        )
        await self.db.commit()
        return await self.get_article(article_id)

    async def mark_all_read(self, category: str | None = None) -> int:
        assert self.db
        if category and category not in ("all", "tous"):
            cur = await self.db.execute(
                "UPDATE articles SET is_read = 1 WHERE is_read = 0 AND category = ?",
                (category,),
            )
        else:
            cur = await self.db.execute(
                "UPDATE articles SET is_read = 1 WHERE is_read = 0"
            )
        await self.db.commit()
        return cur.rowcount or 0

    async def stats(self) -> dict:
        assert self.db
        cur = await self.db.execute(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN is_favorite = 1 THEN 1 ELSE 0 END) AS favorites,
              SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END) AS unread
            FROM articles
            """
        )
        row = await cur.fetchone()
        cur = await self.db.execute(
            "SELECT category, COUNT(*) AS n FROM articles GROUP BY category"
        )
        cats = {r["category"]: r["n"] for r in await cur.fetchall()}
        cur = await self.db.execute(
            "SELECT source_id, COUNT(*) AS n FROM articles GROUP BY source_id"
        )
        sources = {r["source_id"]: r["n"] for r in await cur.fetchall()}
        return {
            "total": int(row["total"] or 0),
            "favorites": int(row["favorites"] or 0),
            "unread": int(row["unread"] or 0),
            "by_category": cats,
            "by_source": sources,
        }

    async def set_source_status(
        self, source_id: str, ok: bool, count: int = 0, error: str | None = None
    ) -> None:
        assert self.db
        now = utcnow()
        await self.db.execute(
            """
            INSERT INTO source_status (source_id, last_ok, last_error, last_count, ok)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
              last_ok = excluded.last_ok,
              last_error = excluded.last_error,
              last_count = excluded.last_count,
              ok = excluded.ok
            """,
            (source_id, now if ok else None, error, count, 1 if ok else 0),
        )
        await self.db.commit()

    async def source_statuses(self) -> dict[str, dict]:
        assert self.db
        cur = await self.db.execute("SELECT * FROM source_status")
        rows = await cur.fetchall()
        return {
            r["source_id"]: {
                "last_ok": r["last_ok"],
                "last_error": r["last_error"],
                "last_count": r["last_count"],
                "ok": bool(r["ok"]),
            }
            for r in rows
        }

    async def prune(self, keep: int = 1200, per_source: int = 40) -> int:
        assert self.db
        cur = await self.db.execute(
            """
            DELETE FROM articles
            WHERE is_favorite = 0
              AND id NOT IN (
                SELECT id FROM (
                  SELECT id,
                    ROW_NUMBER() OVER (
                      PARTITION BY source_id
                      ORDER BY COALESCE(published_at, fetched_at) DESC
                    ) AS rn
                  FROM articles
                )
                WHERE rn <= ?
              )
            """,
            (per_source,),
        )
        n = cur.rowcount or 0
        cur = await self.db.execute(
            """
            DELETE FROM articles
            WHERE is_favorite = 0
              AND id NOT IN (
                SELECT id FROM articles
                ORDER BY COALESCE(published_at, fetched_at) DESC
                LIMIT ?
              )
            """,
            (keep,),
        )
        await self.db.commit()
        return n + (cur.rowcount or 0)
