# scraper_app/scrape/lewdgames.py
from __future__ import annotations

from typing import Tuple, List


def scrape_lewdgames_page(
    url: str,
    *,
    cookie: str = "",
) -> Tuple[str, str, str, List[str], str]:
    """
    Scrape a lewdgames.to page.

    Currently minimal / placeholder:
    - No reliable update/version extraction implemented yet
    - Returns empty metadata and no error

    This exists so the orchestrator can call it
    without special-casing lewdgames everywhere.
    """

    # Future: implement actual scraping here
    return "", "", "", [], ""
