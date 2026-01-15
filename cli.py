# scraper_app/cli.py
from __future__ import annotations

import argparse
import os
from pathlib import Path

from scraper_app.config import DEFAULT_ACTIVE_ROOT, DEFAULT_WAITING_ROOT
from scraper_app.scrape.orchestrator import scrape_all, ScrapeItem
from scraper_app.storage.game_folders import collect_urls_from_library
from scraper_app.ui.app import ScrapeApp


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape game pages and optionally show a Textual UI.")
    p.add_argument("--cookie", default=os.environ.get("ITCH_COOKIE", ""), help="Cookie header for gated pages")
    p.add_argument("--ui", action="store_true", help="Launch Textual UI")
    p.add_argument("--print-all", action="store_true", help="Print every row during scrape")

    p.add_argument("--active-root", default=str(DEFAULT_ACTIVE_ROOT), help="Active library root")
    p.add_argument("--waiting-root", default=str(DEFAULT_WAITING_ROOT), help="Waiting library root")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cookie = (args.cookie or "").strip()

    active_root = Path(args.active_root).expanduser().resolve()
    waiting_root = Path(args.waiting_root).expanduser().resolve()

    if args.ui:
        app = ScrapeApp(active_root=active_root, waiting_root=waiting_root, cookie=cookie)
        app.run()
        return

    folder_items = collect_urls_from_library(active_root=active_root, waiting_root=waiting_root)
    scrape_items = [
        ScrapeItem(
            url=it.url,
            forced_game_id=it.forced_game_id,
            folder_path=str(it.folder),
            folder_status=it.status,
        )
        for it in folder_items
    ]

    scrape_all(
        urls=scrape_items,
        cookie=cookie,
        print_updates_only=not args.print_all,
        progress_cb=None,
    )


if __name__ == "__main__":
    main()
