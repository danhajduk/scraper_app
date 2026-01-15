# scraper_app/scrape/fapnation.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper_app.config import SUPPORTED_EXTERNAL_DOMAINS
from scraper_app.scrape.http import fetch_html
from scraper_app.utils import (
    domain,
    iso_to_pretty_date,
    looks_like_file_url,
    normalize_url,
)


def _normalize_domain(d: str) -> str:
    return (d or "").lower().removeprefix("www.")


def collect_external_links_from_fapnation_info(
    soup: BeautifulSoup,
    page_url: str,
) -> List[str]:
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

    out: List[str] = []
    seen: set[str] = set()
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _normalize_iso_to_z(iso: str) -> str:
    """
    Convert a datetime-ish string to strict UTC Zulu ISO if possible.
    Returns "" if it can't parse.
    """
    iso = (iso or "").strip()
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""


def _extract_updated_iso(soup: BeautifulSoup) -> str:
    """
    Fap-nation usually exposes a datetime in <time> or OG/meta fields.
    """
    # 1) <time datetime="...">
    time_tag = (
        soup.find("time", class_="entry-date published")
        or soup.find("time", class_="entry-date published updated")
        or soup.find("time")
    )
    if time_tag:
        iso = _normalize_iso_to_z((time_tag.get("datetime") or "").strip())
        if iso:
            return iso

    # 2) meta[property="article:modified_time"] etc
    meta = (
        soup.find("meta", attrs={"property": "article:modified_time"})
        or soup.find("meta", attrs={"property": "article:published_time"})
    )
    if meta and meta.get("content"):
        iso = _normalize_iso_to_z(str(meta["content"]).strip())
        if iso:
            return iso

    # 3) Last-ditch: try to find "Updated:" text and parse nothing (leave empty)
    # We'll let pretty be derived from any successfully parsed ISO; otherwise caller can show "N/A".
    return ""


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

    # Your fetch_html currently returns "soup or None" (per existing code usage).
    # If it returns raw HTML in your environment, this keeps it resilient.
    if soup is None:
        return "", "", "", [], "fetch_failed"
    if isinstance(soup, str):
        soup = BeautifulSoup(soup, "html.parser")

    # Title
    h1 = soup.find("h1")
    raw_title = h1.get_text(" ", strip=True) if h1 else ""

    # Updated timestamp (ISO Z)
    updated_utc_iso = _extract_updated_iso(soup)

    # Pretty date derived from ISO
    pretty = iso_to_pretty_date(updated_utc_iso) if updated_utc_iso else "N/A"

    # External links
    links = collect_external_links_from_fapnation_info(soup, url)

    return raw_title, updated_utc_iso, pretty, links, ""
