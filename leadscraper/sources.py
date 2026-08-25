"""Where emails come from: DuckDuckGo search, job boards, and company sites.

All keyless. Each source returns raw text; emails.extract() pulls addresses out.
"""

from __future__ import annotations

import random
import re
import time
from urllib.parse import urljoin, urlparse

import requests

from . import emails as em
from .config import PAGE_SLEEP

try:
    from ddgs import DDGS
except Exception:  # pragma: no cover
    try:
        from duckduckgo_search import DDGS
    except Exception:
        DDGS = None

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

CONTACT_PATHS = ["/", "/contact", "/contact-us", "/about", "/about-us",
                 "/team", "/our-team", "/leadership", "/management", "/people",
                 "/who-we-are", "/company", "/careers", "/jobs"]


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": random.choice(USER_AGENTS),
                      "Accept-Language": "en-US,en;q=0.9"})
    return s


def fetch(sess, url, timeout=12) -> str | None:
    try:
        r = sess.get(url, timeout=timeout, allow_redirects=True)
        return r.text if r.status_code == 200 else None
    except requests.RequestException:
        return None


def search_available() -> bool:
    return DDGS is not None


def ddg(query: str, max_results: int = 15) -> list[tuple[str, str]]:
    """Return (url, snippet) pairs from DuckDuckGo."""
    if DDGS is None:
        return []
    try:
        with DDGS() as d:
            rows = list(d.text(query, max_results=max_results))
        out = []
        for r in rows:
            url = r.get("href") or r.get("link") or r.get("url") or ""
            body = r.get("body") or r.get("snippet") or ""
            if url:
                out.append((url, body))
        return out
    except Exception:
        return []


def board_remoteok(sess) -> set[str]:
    found: set[str] = set()
    try:
        r = sess.get("https://remoteok.com/api", timeout=15)
        if r.status_code == 200:
            for job in r.json():
                if isinstance(job, dict):
                    found |= em.extract(job.get("description", "") or "")
    except Exception:
        pass
    return found


def board_feeds(sess) -> set[str]:
    """Keyless JSON job feeds (Remotive, Arbeitnow, Jobicy) — emails in descriptions."""
    found: set[str] = set()
    feeds = [
        ("https://remotive.com/api/remote-jobs", "jobs", ("description",)),
        ("https://www.arbeitnow.com/api/job-board-api", "data", ("description",)),
        ("https://jobicy.com/api/v2/remote-jobs", "jobs", ("jobDescription", "jobExcerpt")),
    ]
    for url, key, fields in feeds:
        try:
            r = sess.get(url, timeout=20)
            if r.status_code != 200:
                continue
            for job in (r.json().get(key) or [])[:120]:
                if isinstance(job, dict):
                    for f in fields:
                        found |= em.extract(job.get(f, "") or "")
        except Exception:
            continue
    return found


def board_weworkremotely(sess) -> set[str]:
    found: set[str] = set()
    html = fetch(sess, "https://weworkremotely.com/categories/remote-programming-jobs.rss")
    if not html:
        return found
    for link in re.findall(r"(https://weworkremotely\.com/remote-jobs/[^\]<\s]+)", html)[:8]:
        page = fetch(sess, link)
        if page:
            found |= em.extract(page)
        time.sleep(random.uniform(*PAGE_SLEEP))
    return found
