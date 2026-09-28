"""Veille — personal IT news aggregator."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from database import Database
from fetcher import Fetcher
from sources import SOURCES
from categorizer import CATEGORIES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("veille")

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

db = Database()
subscribers: list[asyncio.Queue] = []
fetcher: Fetcher | None = None
scheduler = AsyncIOScheduler()


async def broadcast(event: dict) -> None:
    dead: list[asyncio.Queue] = []
    payload = event
    for q in list(subscribers):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        if q in subscribers:
            subscribers.remove(q)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global fetcher
    await db.connect()
    fetcher = Fetcher(db, broadcast)
    scheduler.add_job(
        fetcher.run_once,
        "interval",
        minutes=4,
        id="fetch",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    asyncio.create_task(_initial_fetch())
    log.info("Veille started — fetching sources in background")
    yield
    scheduler.shutdown(wait=False)
    await db.close()


async def _initial_fetch():
    await asyncio.sleep(0.4)
    try:
        await fetcher.run_once()
    except Exception:
        log.exception("initial fetch failed")


app = FastAPI(title="Veille", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/articles")
async def list_articles(
    category: str | None = None,
    source: str | None = None,
    q: str | None = None,
    favorites: bool = False,
    unread: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=80),
):
    items, total = await db.list_articles(
        category=category,
        source_id=source,
        q=q,
        favorites=favorites,
        unread=unread,
        offset=offset,
        limit=limit,
    )
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(items) < total,
    }


@app.post("/api/articles/{article_id}/favorite")
async def favorite(article_id: int):
    art = await db.toggle_favorite(article_id)
    if not art:
        raise HTTPException(404, "Article introuvable")
    return art


@app.post("/api/articles/{article_id}/read")
async def mark_read(article_id: int, unread: bool = False):
    art = await db.set_read(article_id, is_read=not unread)
    if not art:
        raise HTTPException(404, "Article introuvable")
    return art


@app.post("/api/read-all")
async def read_all(category: str | None = None):
    n = await db.mark_all_read(category)
    return {"updated": n}


@app.get("/api/stats")
async def stats():
    s = await db.stats()
    s["last_run"] = fetcher.last_run if fetcher else None
    s["fetching"] = fetcher.running if fetcher else False
    return s


@app.get("/api/sources")
async def sources():
    statuses = await db.source_statuses()
    out = []
    for src in SOURCES:
        st = statuses.get(src["id"], {})
        out.append(
            {
                "id": src["id"],
                "name": src["name"],
                "site": src["site"],
                "default_category": src["default_category"],
                "color": src["color"],
                "lang": src["lang"],
                "ok": st.get("ok"),
                "last_ok": st.get("last_ok"),
                "last_error": st.get("last_error"),
                "last_count": st.get("last_count", 0),
            }
        )
    return {"sources": out, "categories": CATEGORIES}


@app.post("/api/refresh")
async def refresh():
    if not fetcher:
        raise HTTPException(503, "Fetcher indisponible")
    result = await fetcher.run_once()
    return result


@app.get("/api/stream")
async def stream():
    async def gen():
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        subscribers.append(q)
        try:
            yield "event: hello\ndata: {\"ok\": true}\n\n"
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if q in subscribers:
                subscribers.remove(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
