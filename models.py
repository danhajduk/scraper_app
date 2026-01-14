# scraper_app/models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class GameInfo:
    """
    Row model for CSV export + UI display.

    Mirrors the columns written to results.csv in the current monolith.
    """
    url: str
    source: str
    game_id: str
    title: str
    raw_title: str
    version: str
    last_update: str
    updated_utc_iso: str
    is_recent: str
    change_status: str
    external_links: str


@dataclass
class ScrapeResult:
    """
    Internal convenience object (optional, but useful once we split scrapers).

    Represents the raw extraction from a single page before we compute
    recency / change_status / formatting.
    """
    raw_title: str
    updated_utc_iso: str
    last_update_pretty: str
    external_links: list[str]
    error: str = ""  # empty means OK
