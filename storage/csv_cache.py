# scraper_app/storage/csv_cache.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pandas as pd

from scraper_app.config import CSV_COLUMNS
from scraper_app.models import GameInfo


def load_previous(cache_file: Path) -> Dict[str, dict]:
    """
    Load previous CSV cache and index by URL.

    Returns:
      { url -> row_dict }
    """
    if not cache_file.exists():
        return {}

    try:
        df = pd.read_csv(cache_file)
    except Exception:
        return {}

    out: Dict[str, dict] = {}
    for _, row in df.iterrows():
        url = str(row.get("url", "")).strip()
        if url:
            out[url] = row.to_dict()
    return out


def write_cache(cache_file: Path, results: List[GameInfo]) -> None:
    """
    Write results to CSV in a stable column order.
    """
    rows = []
    for info in results:
        rows.append(
            {
                "url": info.url,
                "source": info.source,
                "game_id": info.game_id,
                "title": info.title,
                "raw_title": info.raw_title,
                "last_update": info.last_update,
                "updated_utc_iso": info.updated_utc_iso,
                "version": info.version,
                "is_recent": info.is_recent,
                "change_status": info.change_status,
                "external_links": info.external_links,
            }
        )

    df = pd.DataFrame(rows, columns=CSV_COLUMNS)
    df.to_csv(cache_file, index=False)
