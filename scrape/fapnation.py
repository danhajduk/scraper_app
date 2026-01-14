# scraper_app/scrape/fapnation.py
from __future__ import annotations

from typing import List, Tuple

from bs4 import BeautifulSoup
from urllib.parse import urljoin

from scraper_app.utils import (
    normalize_url,
    domain,
    looks_like_file_url,
)
from scraper_app.config import SUPPORTED_EXTERNAL_DOMAINS
from scraper_app.scrape.http import fetch_html


def _normalize_domain(d: str) -> str:
    return (d or "").lower().removeprefix("www.")


def collect_external_links_from_fapnation_info(
    soup: BeautifulSoup,
    page_url: str,
) -> List[str]:
    """
    Collect external links from the fap-nation info/content block.
    Uses SUPPORTED_EXTERNAL_DOMAINS exclusively.
    """
    links: List[str] = []
    wrappers = soup.select("div.wpb_wrapper a[href]") or soup.select("a[href]")
    supported = [_normalize_domain(x) for x in SUPPORTED_EXTERNAL_DOMAINS]

    for a in wrappers:
        href = (a.get("href") or "").strip()
        if not href:
            continue

        href = urljoin(page_url, href)
        href = normalize_url(href)

        if looks_like_file_url(href):
            continue

        d = _normalize_domain(domain(href))
        if not d:
            continue

        if any(d == s or d.endswith("." + s) for s in supported):
            links.append(href)

    # de-dup, preserve order
    out: List[str] = []
    seen = set()
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def scrape_fapnation_page(
    url: str,
    *,
    cookie: str = "",
) -> Tuple[str, str, str, List[str], str]:
    """
    Scrape a single fap-nation page.

    Returns:
      raw_title,
      updated_utc_iso,
      pretty_date,
      external_links,
      error_message (empty string if OK)
    """
    soup = fetch_html(url, cookie=cookie)
    if soup is None:
        return "", "", "", [], "fetch_failed"

    # Title
    h1 = soup.select_one("h1")
    raw_title = h1.get_text(strip=True) if h1 else ""

    # Last update date
    updated_utc_iso = ""
    pretty = ""

    # Common fap-nation patterns (kept conservative)
    date_el = soup.find(string=lambda s: s and "Updated" in s)
    if date_el:
        parent = date_el.parent
        if parent:
            pretty = parent.get_text(strip=True).replace("Updated:", "").strip()

    # External links
    links = collect_external_links_from_fapnation_info(soup, url)

    return raw_title, updated_utc_iso, pretty, links, ""
