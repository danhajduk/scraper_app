# scraper_app/scrape/itch.py
from __future__ import annotations

from typing import Tuple, List


def scrape_itch_page(
    url: str,
    *,
    cookie: str = "",
) -> Tuple[str, str, str, List[str], str]:
    """
    Scrape an itch.io game page.

    Current behavior:
    - No scraping implemented yet
    - Exists as a structured hook for future expansion

    Returns:
      raw_title,
      updated_utc_iso,
      pretty_date,
      external_links,
      error_message
    """

    # itch.io scraping can be added later if needed
    return "", "", "", [], ""
