# scraper_app/scrape/orchestrator.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple, Union

from ..config import RECENT_DAYS, ABANDONED_DAYS
from ..models import GameInfo
from ..sources import source_from_url
from ..storage.game_folders import merge_discovered_links, update_observations_latest
from ..utils import (
    _now_utc,
    _strip_na,
    game_id_from_url,
    iso_to_pretty_date,
    normalize_url,
    pretty_date_to_dt,
    split_bracket_version,
)

from ..scrape.fapnation import scrape_fapnation_page
from ..scrape.lewdgames import scrape_lewdgames_page
from ..scrape.itch import scrape_itch_page
from ..scrape.generic import scrape_generic_page


ProgressCB = Callable[[int, int, str], None]


@dataclass(frozen=True)
class ScrapeItem:
    """
    Folder-aware scrape request.

    folder_path/status are optional to keep the orchestrator usable
    while we transition the rest of the codebase.
    """
    url: str
    forced_game_id: str = ""
    folder_path: Optional[str] = None
    folder_status: Optional[str] = None  # "active" | "waiting"


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

    return scrape_generic_page(url, cookie=cookie)


def _coerce_items(urls: Union[list[tuple[str, str]], list[ScrapeItem]]) -> list[ScrapeItem]:
    """
    Backwards compatibility:
      old: [(forced_game_id, url), ...]
      new: [ScrapeItem(...), ...]
    """
    if not urls:
        return []
    first = urls[0]
    if isinstance(first, ScrapeItem):
        return list(urls)  # type: ignore[arg-type]

    out: list[ScrapeItem] = []
    for forced_gid, url in urls:  # type: ignore[assignment]
        out.append(ScrapeItem(url=url, forced_game_id=forced_gid))
    return out


def scrape_all(
    *,
    urls: Union[list[tuple[str, str]], list[ScrapeItem]],
    cache_file,
    cookie: str = "",
    print_updates_only: bool = True,
    progress_cb: Optional[ProgressCB] = None,
) -> list[GameInfo]:
    """
    Supports both:
      - list[(forced_game_id, url)]  (legacy)
      - list[ScrapeItem]             (folder-aware)
    """
    items = _coerce_items(urls)

    results: List[GameInfo] = []
    total = len(items)

    for idx, item in enumerate(items, start=1):
        url = normalize_url(item.url)
        src = source_from_url(url)

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

            # ✅ Folder-scoped persistence into url.json (never touches url.txt)
            if item.folder_path:
                # 1) Merge discovered links (tagged with source)
                try:
                    merge_discovered_links(
                        folder_path=item.folder_path,
                        discovered_links=links,
                        source=src,
                    )
                except Exception:
                    # Don't kill the scrape run because a metadata write failed
                    pass

                # 2) Update observations + recompute latest
                try:
                    update_observations_latest(
                        folder_path=item.folder_path,
                        source=src,
                        version=version,
                        last_update_iso=updated_iso or "",
                    )
                except Exception:
                    pass

        external_links = "|".join(links)

        info = GameInfo(
            url=url,
            source=src,
            game_id=(item.forced_game_id or game_id_from_url(url)),
            title=(clean_title or "N/A"),
            raw_title=(raw_title or "N/A"),
            version=version,
            last_update=pretty,
            updated_utc_iso=updated_iso,
            is_recent=is_recent,
            change_status=change_status,
            external_links=external_links,
        )

        # Optional: attach folder info if GameInfo gets those fields later
        if hasattr(info, "folder_path"):
            setattr(info, "folder_path", item.folder_path or "")
        if hasattr(info, "folder_status"):
            setattr(info, "folder_status", item.folder_status or "")

        results.append(info)

        if progress_cb:
            label = info.title if info.title and info.title != "N/A" else info.raw_title
            progress_cb(idx, total, f"Processed ({idx}/{total}) • {info.is_recent} • {info.change_status}\n{label}")

        # printing behavior handled elsewhere; keep placeholder to avoid changing behavior mid-migration
        if (not print_updates_only) or (info.change_status in ("New", "🔁 Updated") or err):
            pass


    if progress_cb:
        progress_cb(total, total, f"Done ({total}/{total}) ✅\nWrote: {cache_file}")

    return results
