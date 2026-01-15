# scraper_app/models.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GameInfo:
    """
    Row model for UI display.

    Persistence is per-folder url.json; GameInfo is derived at runtime.
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

    folder_path: str = ""
    folder_status: str = ""  # "active" | "waiting"


@dataclass
class ScrapeResult:
    """
    Raw extraction from a single page before recency/change_status formatting.
    """
    raw_title: str
    updated_utc_iso: str
    last_update_pretty: str
    external_links: list[str]
    error: str = ""
