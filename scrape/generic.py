# scraper_app/scrape/generic.py
from __future__ import annotations

from typing import Tuple, List


def scrape_generic_page(
    url: str,
    *,
    cookie: str = "",
) -> Tuple[str, str, str, List[str], str]:
    """
    Generic fallback scraper.

    Used when no site-specific scraper exists.
    Returns empty fields and no error.
    """

    return "", "", "", [], ""
