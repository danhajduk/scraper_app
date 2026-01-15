# scraper_app/scrape/orchestrator.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List, Optional, Tuple, Union

from ..config import RECENT_DAYS, ABANDONED_DAYS
from ..models import GameInfo
from ..sources import source_from_url
from ..storage.game_folders import (
    merge_discovered_links,
    update_observations_latest,
    read_observation,
    update_title_from_raw
)
from ..utils import (
    _now_utc,
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
    url: str
    forced_game_id: str = ""
    folder_path: Optional[str] = None
    folder_status: Optional[str] = None  # "active" | "waiting"


def _dt_to_iso_z(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def classify_recency(updated_iso: str) -> str:
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
    cookie: str = "",
    print_updates_only: bool = True,
    progress_cb: Optional[ProgressCB] = None,
) -> list[GameInfo]:
    items = _coerce_items(urls)

    results: list[GameInfo] = []
    total = len(items)

    for idx, item in enumerate(items, start=1):
        url = normalize_url(item.url)
        src = source_from_url(url)

        prev_ver = ""
        prev_iso = ""
        if item.folder_path:
            prev_ver, prev_iso = read_observation(folder_path=item.folder_path, source=src)

        if progress_cb:
            progress_cb(idx, total, f"Fetching ({idx}/{total})\n{url}")

        raw_title, updated_iso, pretty, links, err = scrape_one(url, cookie=cookie)
        if item.folder_path:
            try:
                update_title_from_raw(folder_path=item.folder_path, raw_title=clean_title or raw_title)
            except Exception:
                pass
        
        version, clean_title = split_bracket_version(raw_title or "")

        # If scraper didn't provide ISO but did provide pretty, synthesize ISO
        if (not updated_iso) and pretty:
            dt = pretty_date_to_dt(pretty)
            if dt:
                updated_iso = _dt_to_iso_z(dt)

        if err:
            # Keep display from previous observation if available
            if prev_iso:
                updated_iso = prev_iso
                pretty = iso_to_pretty_date(prev_iso)
            if prev_ver and (not version):
                version = prev_ver

            is_recent = classify_recency(updated_iso) if updated_iso else "❌ Old"
            change_status = "ERROR"
            links = []
        else:
            if updated_iso:
                pretty = iso_to_pretty_date(updated_iso)
            pretty = pretty or "N/A"

            is_recent = classify_recency(updated_iso) if updated_iso else "❌ Old"

            if not prev_iso and updated_iso:
                change_status = "New"
            elif prev_iso and updated_iso and updated_iso > prev_iso:
                change_status = "🔁 Updated"
            else:
                change_status = "Unchanged"

            # Persist into url.json
            if item.folder_path:
                try:
                    merge_discovered_links(
                        folder_path=item.folder_path,
                        discovered_links=links,
                        source=src,
                    )
                except Exception:
                    pass

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
            folder_path=item.folder_path or "",
            folder_status=item.folder_status or "",
        )

        results.append(info)

        if progress_cb:
            label = info.title if info.title and info.title != "N/A" else info.raw_title
            progress_cb(idx, total, f"Processed ({idx}/{total}) • {info.is_recent} • {info.change_status}\n{label}")

        if (not print_updates_only) or (info.change_status in ("New", "🔁 Updated") or err):
            pass

    if progress_cb:
        progress_cb(total, total, f"Done ({total}/{total}) ✅")

    return results
