#!/usr/bin/env python3
"""Build a static snapshot of the feed for GitHub Pages."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from categorizer import CATEGORIES  # noqa: E402
from fetcher import harvest  # noqa: E402
from sources import SOURCES  # noqa: E402


def copy_frontend(out: Path) -> None:
    static_src = ROOT / "static"
    static_dst = out / "static"
    static_dst.mkdir(parents=True, exist_ok=True)
    for name in ("styles.css", "app.js", "favicon.svg"):
        shutil.copy2(static_src / name, static_dst / name)
    shutil.copy2(static_src / "index.html", out / "index.html")
    (out / ".nojekyll").write_text("", encoding="utf-8")


async def build(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    articles, statuses, errors = await harvest()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload_articles = []
    by_cat: dict[str, int] = {}
    by_src: dict[str, int] = {}
    for i, art in enumerate(articles, start=1):
        art = dict(art)
        art["id"] = i
        art.setdefault("is_favorite", False)
        art.setdefault("is_read", False)
        extra = art.get("extra") or {}
        if not isinstance(extra, dict):
            extra = {}
        art["extra"] = extra
        payload_articles.append(art)
        by_cat[art.get("category") or "autre"] = by_cat.get(art.get("category") or "autre", 0) + 1
        by_src[art["source_id"]] = by_src.get(art["source_id"], 0) + 1

    sources_out = []
    for src in SOURCES:
        st = statuses.get(src["id"], {})
        sources_out.append(
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

    data = {
        "generated_at": now,
        "articles": payload_articles,
        "sources": sources_out,
        "categories": CATEGORIES,
        "stats": {
            "total": len(payload_articles),
            "favorites": 0,
            "unread": len(payload_articles),
            "by_category": by_cat,
            "by_source": by_src,
            "last_run": now,
            "fetching": False,
        },
        "errors": errors,
    }
    copy_frontend(out)
    (out / "articles.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=None), encoding="utf-8"
    )
    print(
        f"Wrote {len(payload_articles)} articles → {out / 'articles.json'} "
        f"({sum(1 for s in sources_out if s.get('ok'))}/{len(SOURCES)} sources OK)"
    )
    if errors:
        print("Errors:", errors)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "_site"))
    args = parser.parse_args()
    asyncio.run(build(Path(args.out)))


if __name__ == "__main__":
    main()
