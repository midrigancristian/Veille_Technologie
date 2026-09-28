"""Catalog of IT sources for the personal tech watch."""

from datetime import datetime, timedelta, timezone

SOURCES = [
    {
        "id": "hn",
        "name": "Hacker News",
        "kind": "rss",
        "url": "https://hnrss.org/frontpage",
        "site": "https://news.ycombinator.com",
        "default_category": "dev",
        "color": "#ff6b2b",
        "lang": "en",
    },
    {
        "id": "developpez",
        "name": "Developpez.com",
        "kind": "rss",
        "url": "https://www.developpez.com/index/rss",
        "site": "https://www.developpez.com",
        "default_category": "dev",
        "color": "#3d8bd4",
        "lang": "fr",
    },
    {
        "id": "bleeping",
        "name": "BleepingComputer",
        "kind": "rss",
        "url": "https://www.bleepingcomputer.com/feed/",
        "site": "https://www.bleepingcomputer.com",
        "default_category": "cyber",
        "color": "#e11d48",
        "lang": "en",
    },
    {
        "id": "thn",
        "name": "The Hacker News",
        "kind": "rss",
        "url": "https://feeds.feedburner.com/TheHackersNews",
        "site": "https://thehackernews.com",
        "default_category": "cyber",
        "color": "#f59e0b",
        "lang": "en",
    },
    {
        "id": "kreb",
        "name": "Krebs on Security",
        "kind": "rss",
        "url": "https://krebsonsecurity.com/feed/",
        "site": "https://krebsonsecurity.com",
        "default_category": "cyber",
        "color": "#fb7185",
        "lang": "en",
    },
    {
        "id": "korben",
        "name": "Korben",
        "kind": "rss",
        "url": "https://korben.info/feed",
        "site": "https://korben.info",
        "default_category": "dev",
        "color": "#22c55e",
        "lang": "fr",
    },
    {
        "id": "linuxfr",
        "name": "LinuxFr",
        "kind": "rss",
        "url": "https://linuxfr.org/news.atom",
        "site": "https://linuxfr.org",
        "default_category": "sysadmin",
        "color": "#a3e635",
        "lang": "fr",
    },
    {
        "id": "nextink",
        "name": "Next",
        "kind": "rss",
        "url": "https://next.ink/feed/",
        "site": "https://next.ink",
        "default_category": "dev",
        "color": "#38bdf8",
        "lang": "fr",
    },
    {
        "id": "devto",
        "name": "Dev.to",
        "kind": "rss",
        "url": "https://dev.to/feed",
        "site": "https://dev.to",
        "default_category": "dev",
        "color": "#a78bfa",
        "lang": "en",
    },
    {
        "id": "lobsters",
        "name": "Lobsters",
        "kind": "rss",
        "url": "https://lobste.rs/rss",
        "site": "https://lobste.rs",
        "default_category": "dev",
        "color": "#f43f5e",
        "lang": "en",
    },
    {
        "id": "ars",
        "name": "Ars Technica",
        "kind": "rss",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "site": "https://arstechnica.com",
        "default_category": "dev",
        "color": "#f97316",
        "lang": "en",
    },
    {
        "id": "hf",
        "name": "Hugging Face",
        "kind": "rss",
        "url": "https://huggingface.co/blog/feed.xml",
        "site": "https://huggingface.co/blog",
        "default_category": "ia",
        "color": "#fbbf24",
        "lang": "en",
    },
    {
        "id": "github",
        "name": "GitHub Trending",
        "kind": "github",
        "url": "https://api.github.com/search/repositories",
        "site": "https://github.com/trending",
        "default_category": "dev",
        "color": "#e6edf3",
        "lang": "en",
    },
    {
        "id": "cloudflare",
        "name": "Cloudflare Blog",
        "kind": "rss",
        "url": "https://blog.cloudflare.com/rss/",
        "site": "https://blog.cloudflare.com",
        "default_category": "sysadmin",
        "color": "#f97316",
        "lang": "en",
    },
    {
        "id": "k8s",
        "name": "Kubernetes",
        "kind": "rss",
        "url": "https://kubernetes.io/feed.xml",
        "site": "https://kubernetes.io/blog",
        "default_category": "sysadmin",
        "color": "#326ce5",
        "lang": "en",
    },
    {
        "id": "netsec",
        "name": "r/netsec",
        "kind": "rss",
        "url": "https://www.reddit.com/r/netsec/.rss",
        "site": "https://www.reddit.com/r/netsec",
        "default_category": "cyber",
        "color": "#ef4444",
        "lang": "en",
    },
]


def source_by_id(source_id: str) -> dict | None:
    for src in SOURCES:
        if src["id"] == source_id:
            return src
    return None


def github_search_url() -> str:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    return (
        "https://api.github.com/search/repositories"
        f"?q=created:>{since}&sort=stars&order=desc&per_page=20"
    )
