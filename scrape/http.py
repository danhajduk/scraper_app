# scraper_app/scrape/http.py
from __future__ import annotations

import time
from typing import Optional

import cloudscraper
from bs4 import BeautifulSoup

from scraper_app.config import UA


def fetch_html(
    url: str,
    *,
    cookie: str = "",
    sleep_sec: float = 0.0,
    timeout: int = 30,
) -> Optional[BeautifulSoup]:
    """
    Fetch a URL and return a BeautifulSoup object, or None on failure.

    This preserves current behavior:
    - cloudscraper for Cloudflare sites
    - optional Cookie header
    - minimal retry logic (single attempt)
    """

    headers = {
        "User-Agent": UA,
    }
    if cookie:
        headers["Cookie"] = cookie

    try:
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "linux", "mobile": False}
        )

        resp = scraper.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()

        if sleep_sec:
            time.sleep(sleep_sec)

        return BeautifulSoup(resp.text, "html.parser")

    except Exception:
        return None
