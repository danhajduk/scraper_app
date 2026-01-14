# scraper_app/cli.py
from __future__ import annotations

import argparse
import os
from pathlib import Path

from scraper_app.config import DEFAULT_CACHE_FILE, DEFAULT_URLS_FILE
from scraper_app.scrape.orchestrator import scrape_all
from scraper_app.ui.app import ScrapeApp
from scraper_app.utils import safe_read_text_path, normalize_url, game_id_from_url


def read_urls(urls_file: Path) -> list[tuple[str, str]]:
    """
    Supports:
      - url
      - game_id|url
    Returns:
      list of (game_id, url)
    """
    if not urls_file.exists():
        raise FileNotFoundError(f"URLs file not found: {urls_file}")

    items: list[tuple[str, str]] = []
    for line in safe_read_text_path(urls_file).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        gid = ""
        url = line

        if "|" in line:
            gid, url = line.split("|", 1)
            gid = gid.strip()
            url = url.strip()

        url = normalize_url(url)
        if not url:
            continue

        if not gid:
            gid = game_id_from_url(url)

        items.append((gid, url))

    # de-dupe by URL (keep first occurrence)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for gid, url in items:
        if url in seen:
            continue
        seen.add(url)
        out.append((gid, url))

    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape game pages and optionally show a Textual UI.")
    p.add_argument("--urls", default=DEFAULT_URLS_FILE, help="Path to URL list file (default: urls.txt)")
    p.add_argument("--cache", default=DEFAULT_CACHE_FILE, help="CSV cache output (default: results.csv)")
    p.add_argument("--cookie", default=os.environ.get("ITCH_COOKIE", ""), help="Cookie header for gated pages")
    p.add_argument("--ui", action="store_true", help="Launch Textual UI")
    p.add_argument("--print-all", action="store_true", help="Print every row during scrape")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    urls_file = Path(args.urls).expanduser().resolve()
    cache_file = Path(args.cache).expanduser().resolve()
    cookie = (args.cookie or "").strip()

    urls = read_urls(urls_file)

    if args.ui:
        # UI mode
        app = ScrapeApp(cache_file=cache_file, urls=urls, cookie=cookie)
        app.run()
        return

    # CLI scrape mode
    scrape_all(
        urls=urls,
        cache_file=cache_file,
        cookie=cookie,
        print_updates_only=not args.print_all,
        progress_cb=None,
    )


if __name__ == "__main__":
    main()
