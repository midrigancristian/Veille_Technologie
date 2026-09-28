"""Fetch RSS feeds, GitHub trending, then categorize & store."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import httpx
from dateutil import parser as dateparser

from categorizer import categorize, is_noise, strip_html
from sources import SOURCES, github_search_url

log = logging.getLogger("veille.fetcher")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Veille/1.0"
)

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}


def normalize_url(url: str) -> str:
    if not url:
        return url
    try:
        p = urlparse(url.strip())
        query = [
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        ]
        path = p.path.rstrip("/") or "/"
        netloc = p.netloc.lower()
        return urlunparse((p.scheme or "https", netloc, path, "", urlencode(query), ""))
    except Exception:
        return url.strip()


def make_guid(url: str, title: str) -> str:
    raw = f"{normalize_url(url)}|{title.strip().lower()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def parse_date(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat(
                timespec="seconds"
            )
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    except Exception:
        pass
    try:
        dt = dateparser.parse(text)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return None


def excerpt(text: str, limit: int = 280) -> str:
    text = strip_html(text or "")
    if len(text) <= limit:
        return text
    cut = text[: limit + 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(".,;: ") + "…"


def _entry_url(entry: dict) -> str:
    if entry.get("link"):
        return entry["link"]
    for l in entry.get("links") or []:
        href = l.get("href")
        if href:
            return href
    return entry.get("id") or ""


def _entry_date(entry: dict) -> str | None:
    for key in ("published", "updated", "created"):
        parsed = parse_date(entry.get(key))
        if parsed:
            return parsed
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            try:
                dt = datetime(*st[:6], tzinfo=timezone.utc)
                return dt.isoformat(timespec="seconds")
            except Exception:
                pass
    return None


def parse_rss(content: bytes, source: dict) -> list[dict]:
    feed = feedparser.parse(content)
    articles: list[dict] = []
    for entry in feed.entries:
        title = strip_html(entry.get("title") or "").strip()
        url = _entry_url(entry)
        if not title or not url:
            continue
        summary_raw = (
            entry.get("summary")
            or entry.get("description")
            or (entry.get("content") or [{}])[0].get("value")
            or ""
        )
        summary = excerpt(summary_raw)
        if is_noise(title, summary):
            continue
        extra: dict[str, Any] = {}
        # hnrss comments / points
        comments = entry.get("comments")
        if comments:
            extra["comments_url"] = comments
        if entry.get("hnrss_points"):
            extra["points"] = int(str(entry["hnrss_points"]).split()[0] or 0)
        # look in tags / hn-specific
        for t in entry.get("tags") or []:
            term = (t.get("term") or "").lower()
            extra.setdefault("tags", []).append(term)

        category = categorize(title, summary, source.get("default_category", "autre"))
        articles.append(
            {
                "guid": make_guid(url, title),
                "url": normalize_url(url),
                "title": title,
                "summary": summary,
                "source_id": source["id"],
                "source_name": source["name"],
                "category": category,
                "published_at": _entry_date(entry),
                "extra": extra,
            }
        )
    return articles


def parse_github(payload: dict, source: dict) -> list[dict]:
    articles: list[dict] = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for repo in payload.get("items") or []:
        full = repo.get("full_name") or ""
        desc = repo.get("description") or ""
        html_url = repo.get("html_url") or ""
        if not full or not html_url:
            continue
        stars = repo.get("stargazers_count") or 0
        lang = repo.get("language") or ""
        title = f"{full} — {desc}" if desc else full
        title = title[:240]
        summary = excerpt(
            f"{desc} · ★ {stars:,} · {lang}".strip(" ·") if desc or lang else f"★ {stars:,}"
        )
        category = categorize(title, summary, source.get("default_category", "dev"))
        articles.append(
            {
                "guid": make_guid(html_url, full),
                "url": normalize_url(html_url),
                "title": title,
                "summary": summary,
                "source_id": source["id"],
                "source_name": source["name"],
                "category": category,
                "published_at": parse_date(repo.get("created_at")) or now,
                "extra": {
                    "stars": stars,
                    "language": lang,
                    "forks": repo.get("forks_count") or 0,
                },
            }
        )
    return articles


async def fetch_source(
    client: httpx.AsyncClient, src: dict
) -> tuple[list[dict], str | None]:
    try:
        if src["kind"] == "github":
            url = github_search_url()
            r = await client.get(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "Veille-Personal-Aggregator",
                },
            )
            if r.status_code != 200:
                return [], f"HTTP {r.status_code}"
            return parse_github(r.json(), src), None

        r = await client.get(src["url"])
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}"
        body = r.content.lstrip()
        looks_xml = body.startswith(
            (b"<?xml", b"<rss", b"<feed", b"<RDF", b"\xef\xbb\xbf<?xml")
        )
        ctype = r.headers.get("content-type", "")
        if (
            not looks_xml
            and "html" in ctype
            and "xml" not in ctype
            and "rss" not in ctype
            and "atom" not in ctype
        ):
            return [], "HTML instead of RSS"
        arts = await asyncio.to_thread(parse_rss, r.content, src)
        return arts[:35], None
    except httpx.TimeoutException:
        return [], "timeout"
    except Exception as exc:
        log.warning("fetch %s failed: %s", src["id"], exc)
        return [], str(exc)[:180]


async def harvest() -> tuple[list[dict], dict[str, dict], dict[str, str]]:
    """Fetch every source. Returns (articles, statuses, errors)."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, application/json, text/xml, */*",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    }
    timeout = httpx.Timeout(25.0, connect=10.0)
    articles: list[dict] = []
    statuses: dict[str, dict] = {}
    errors: dict[str, str] = {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    async with httpx.AsyncClient(
        headers=headers, timeout=timeout, follow_redirects=True
    ) as client:
        sem = asyncio.Semaphore(6)

        async def one(src: dict):
            async with sem:
                return src, await fetch_source(client, src)

        results = await asyncio.gather(
            *[one(s) for s in SOURCES], return_exceptions=True
        )

    for item in results:
        if isinstance(item, Exception):
            log.exception("source task failed: %s", item)
            continue
        src, (arts, err) = item
        if err:
            errors[src["id"]] = err
            statuses[src["id"]] = {
                "ok": False,
                "last_error": err,
                "last_count": 0,
                "last_ok": None,
            }
        else:
            statuses[src["id"]] = {
                "ok": True,
                "last_error": None,
                "last_count": len(arts),
                "last_ok": now,
            }
            for art in arts:
                art.setdefault("fetched_at", now)
                articles.append(art)

    articles.sort(
        key=lambda a: a.get("published_at") or a.get("fetched_at") or "",
        reverse=True,
    )
    return articles, statuses, errors


class Fetcher:
    def __init__(self, database, broadcaster):
        self.db = database
        self.broadcast = broadcaster
        self._lock = asyncio.Lock()
        self.last_run: str | None = None
        self.running = False
        self.last_new = 0

    async def run_once(self) -> dict:
        if self._lock.locked():
            return {"ok": False, "reason": "already_running", "inserted": 0}
        async with self._lock:
            self.running = True
            try:
                result = await self._run()
                return result
            finally:
                self.running = False

    async def _run(self) -> dict:
        articles, statuses, errors = await harvest()
        ok_count = 0
        for src in SOURCES:
            st = statuses.get(src["id"]) or {"ok": False, "last_error": "no data", "last_count": 0}
            if st.get("ok"):
                ok_count += 1
                await self.db.set_source_status(src["id"], ok=True, count=st.get("last_count") or 0)
            else:
                await self.db.set_source_status(
                    src["id"], ok=False, error=st.get("last_error") or errors.get(src["id"])
                )

        inserted_all = await self.db.insert_articles(articles) if articles else []
        await self.db.prune()
        self.last_run = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.last_new = len(inserted_all)
        inserted_all.sort(
            key=lambda a: a.get("published_at") or a.get("fetched_at") or "",
            reverse=True,
        )
        if inserted_all:
            await self.broadcast(
                {
                    "type": "new",
                    "count": len(inserted_all),
                    "articles": inserted_all[:40],
                }
            )
        await self.broadcast(
            {
                "type": "status",
                "last_run": self.last_run,
                "inserted": len(inserted_all),
                "ok_sources": ok_count,
                "errors": errors,
            }
        )
        log.info(
            "fetch done: +%s articles, %s/%s sources OK",
            len(inserted_all),
            ok_count,
            len(SOURCES),
        )
        return {
            "ok": True,
            "inserted": len(inserted_all),
            "ok_sources": ok_count,
            "errors": errors,
            "last_run": self.last_run,
        }
