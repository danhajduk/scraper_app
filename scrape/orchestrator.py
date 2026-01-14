# scraper_app/scrape/orchestrator.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from scraper_app.config import RECENT_DAYS, ABANDONED_DAYS
from scraper_app.models import GameInfo
from scraper_app.sources import source_from_url
from scraper_app.storage.csv_cache import load_previous, write_cache
from scraper_app.utils import (
    _now_utc,
    _strip_na,
    game_id_from_url,
    iso_to_pretty_date,
    normalize_url,
    pretty_date_to_dt,
    split_bracket_version,
)

from scraper_app.scrape.fapnation import scrape_fapnation_page
from scraper_app.scrape.lewdgames import scrape_lewdgames_page
from scraper_app.scrape.itch import scrape_itch_page
from scraper_app.scrape.generic import scrape_generic_page


ProgressCB = Callable[[int, int, str], None]


def _dt_to_iso_z(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def classify_recency(updated_iso: str) -> str:
    """
    Returns:
      ✅ Recent / ❌ Old / ⚠️ Abandoned
    """
    try:
        dt = datetime.fromisoformat((updated_iso or "").replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return "❌ Old"

    age_days = (_now_utc() - dt).days
    if age_days <= RECENT_DAYS:
        return "✅ Recent"
    if age_days >= ABANDONED_DAYS:
        return "⚠️ Abandoned"
    return "❌ Old"


def compute_change_status(prev_row: Optional[Dict[str, str]], new_pretty_date: str) -> str:
    if prev_row is None:
        return "New"

    prev_date = _strip_na(prev_row.get("last_update"))
    if not prev_date:
        return "New"

    if prev_date == new_pretty_date:
        return "Unchanged"

    old_dt = pretty_date_to_dt(prev_date)
    new_dt = pretty_date_to_dt(new_pretty_date)

    # If we can compare, do it properly
    if old_dt and new_dt and new_dt > old_dt:
        return "🔁 Updated"

    # If it changed but we can't compare (or went backwards), still flag as Updated
    if prev_date != new_pretty_date:
        return "🔁 Updated"

    return "Unchanged"


def scrape_one(url: str, *, cookie: str = "") -> Tuple[str, str, str, List[str], str]:
    """
    Returns:
      raw_title,
      updated_utc_iso,
      pretty_date,
      external_links,
      error_message
    """
    src = source_from_url(url)

    if src == "fap-nation":
        return scrape_fapnation_page(url, cookie=cookie)

    if src == "lewdgames.to":
        return scrape_lewdgames_page(url, cookie=cookie)

    if src == "itch.io":
        return scrape_itch_page(url, cookie=cookie)

    # everything else
    return scrape_generic_page(url, cookie=cookie)


def scrape_all(
    *,
    urls: list[tuple[str, str]],
    cache_file,
    cookie: str = "",
    print_updates_only: bool = True,
    progress_cb: Optional[ProgressCB] = None,
) -> list[GameInfo]:
    """
    urls: list of (forced_game_id, url)
    """
    prev = load_previous(cache_file)
    results: List[GameInfo] = []
    total = len(urls)

    for idx, (forced_gid, url) in enumerate(urls, start=1):
        url = normalize_url(url)
        prev_row = prev.get(url)

        if progress_cb:
            progress_cb(idx, total, f"Fetching ({idx}/{total})\n{url}")

        raw_title, updated_iso, pretty, links, err = scrape_one(url, cookie=cookie)
        version, clean_title = split_bracket_version(raw_title or "")

        # If scraper didn't provide ISO but did provide pretty, synthesize ISO
        if (not updated_iso) and pretty:
            dt = pretty_date_to_dt(pretty)
            if dt:
                updated_iso = _dt_to_iso_z(dt)

        if err:
            # fallback to previous row if available
            is_recent = "❌ Old"
            change_status = "ERROR"

            if prev_row:
                updated_iso = _strip_na(prev_row.get("updated_utc_iso"))
                pretty = _strip_na(prev_row.get("last_update")) or "N/A"
                clean_title = _strip_na(prev_row.get("title")) or clean_title
                version = _strip_na(prev_row.get("version")) or version

            links = []
        else:
            # Normalize pretty date if ISO exists
            if updated_iso:
                pretty = iso_to_pretty_date(updated_iso)

            is_recent = classify_recency(updated_iso) if updated_iso else "❌ Old"
            pretty = pretty or "N/A"
            change_status = compute_change_status(prev_row, pretty)

        external_links = "|".join(links)

        info = GameInfo(
            url=url,
            source=source_from_url(url),
            game_id=(forced_gid or game_id_from_url(url)),
            title=(clean_title or "N/A"),
            raw_title=(raw_title or "N/A"),
            version=version,
            last_update=pretty,
            updated_utc_iso=updated_iso,
            is_recent=is_recent,
            change_status=change_status,
            external_links=external_links,
        )
        results.append(info)

        if progress_cb:
            label = info.title if info.title and info.title != "N/A" else info.raw_title
            progress_cb(idx, total, f"Processed ({idx}/{total}) • {info.is_recent} • {info.change_status}\n{label}")

        # Optional: CLI printing can stay here for parity with your monolith
        if (not print_updates_only) or (info.change_status in ("New", "🔁 Updated") or err):
            # intentionally simple; UI uses progress_cb anyway
            pass

    write_cache(cache_file, results)

    if progress_cb:
        progress_cb(total, total, f"Done ({total}/{total}) ✅\nWrote: {cache_file}")

    return results
