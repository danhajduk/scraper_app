# scraper_app/storage/game_folders.py
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from ..config import URL_JSON_NAME, URL_TXT_NAME, URL_JSON_SCHEMA_VERSION, DISCOVERED_PRUNE_DAYS
from ..utils import normalize_url, game_id_from_url, safe_read_text_path
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..scrape.orchestrator import ScrapeItem


@dataclass(frozen=True)
class FolderUrlItem:
    folder: Path
    status: str  # "active" | "waiting"
    url: str
    forced_game_id: str


def _now_iso_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_url_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_url_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _bootstrap_from_txt(txt_path: Path, json_path: Path, *, status: str) -> dict:
    """
    Parse url.txt -> create url.json (do NOT delete txt).
    """
    links: list[str] = []
    raw = safe_read_text_path(txt_path)
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        url = normalize_url(line)
        if url:
            links.append(url)

    # de-dupe while preserving order
    seen: set[str] = set()
    links_dedup: list[str] = []
    for u in links:
        if u in seen:
            continue
        seen.add(u)
        links_dedup.append(u)

    # Derive game_id from first manual link if possible
    gid = game_id_from_url(links_dedup[0]) if links_dedup else ""

    data = {
        "game_id": gid or "",
        "status": status,
        "manual": {
            "links": links_dedup,
            "source_file": "url.txt",
        },
        "discovered": [],
        "observations": {},
        "latest": {},
        "updated_at": _now_iso_z(),
    }
    _write_url_json_atomic(json_path, data)
    return data


def _get_folder_urls(folder: Path, *, status: str) -> tuple[list[str], dict] | tuple[None, None]:
    """
    Returns (manual_urls, json_data) or (None, None) if folder isn't a game.
    """
    json_path = folder / URL_JSON_NAME
    txt_path = folder / URL_TXT_NAME

    if json_path.exists():
        data = _load_url_json(json_path)
        manual = data.get("manual") or {}
        links = manual.get("links") if isinstance(manual, dict) else []
        if not isinstance(links, list):
            links = []

        # normalize + de-dupe
        out: list[str] = []
        seen: set[str] = set()
        for u in links:
            u2 = normalize_url(str(u))
            if not u2 or u2 in seen:
                continue
            seen.add(u2)
            out.append(u2)

        return out, data

    if txt_path.exists():
        data = _bootstrap_from_txt(txt_path, json_path, status=status)
        manual = data.get("manual") or {}
        links = manual.get("links") if isinstance(manual, dict) else []
        return list(links) if isinstance(links, list) else [], data

    return None, None

def _iter_candidate_folders(root: Path) -> Iterable[Path]:
    """
    Walk library tree and yield any folder that contains url.json OR url.txt.
    """
    if not root.exists():
        return
    for p in root.rglob("*"):
        if not p.is_dir():
            continue
        if (p / URL_JSON_NAME).exists() or (p / URL_TXT_NAME).exists():
            yield p


def collect_urls_from_library(*, active_root: Path, waiting_root: Path) -> list[FolderUrlItem]:
    """
    Returns folder-aware URL items.
    """
    items: list[FolderUrlItem] = []

    for status, root in (("active", active_root), ("waiting", waiting_root)):
        for folder in _iter_candidate_folders(root):
            manual_urls, _data = _get_folder_urls(folder, status=status)
            if not manual_urls:
                continue

            for url in manual_urls:
                gid = game_id_from_url(url)
                items.append(
                    FolderUrlItem(
                        folder=folder,
                        status=status,
                        url=url,
                        forced_game_id=gid,
                    )
                )

    # De-dupe by URL (keep first occurrence)
    out: list[FolderUrlItem] = []
    seen: set[str] = set()
    for it in items:
        if it.url in seen:
            continue
        seen.add(it.url)
        out.append(it)

    return out

def merge_discovered_links(*, folder_path: str, discovered_links: list[str], source: str = "") -> None:
    """
    Merge discovered external links into url.json for a given folder.

    - Only modifies url.json if it exists.
    - Never reads/uses url.txt.
    - Writes discovered entries as:
        {url, source, first_seen, last_seen}
    - Prunes by last_seen vs DISCOVERED_PRUNE_DAYS.
    """
    folder = Path(folder_path)
    json_path = folder / URL_JSON_NAME
    if not json_path.exists():
        return

    data = _load_url_json(json_path)

    manual = data.get("manual") or {}
    manual_links = manual.get("links") if isinstance(manual, dict) else []
    if not isinstance(manual_links, list):
        manual_links = []
    manual_set = {normalize_url(str(u)) for u in manual_links if normalize_url(str(u))}

    discovered = data.get("discovered") or []
    if not isinstance(discovered, list):
        discovered = []

    # Index existing discovered by normalized url
    idx: dict[str, dict] = {}
    for entry in discovered:
        if not isinstance(entry, dict):
            continue
        u = normalize_url(str(entry.get("url", "")))
        if not u:
            continue
        e = dict(entry)
        e["url"] = u
        idx[u] = e

    # Normalize + dedupe incoming
    incoming: list[str] = []
    seen_in: set[str] = set()
    for raw in (discovered_links or []):
        u = normalize_url(str(raw))
        if not u or u in seen_in:
            continue
        seen_in.add(u)
        incoming.append(u)

    now_iso = _now_iso_z()
    changed = False

    for u in incoming:
        if u in manual_set:
            continue

        if u in idx:
            idx[u]["last_seen"] = now_iso
            if source and not idx[u].get("source"):
                idx[u]["source"] = source
            changed = True
        else:
            idx[u] = {
                "url": u,
                "source": source or "",
                "first_seen": now_iso,
                "last_seen": now_iso,
            }
            changed = True

    # Prune by last_seen
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(DISCOVERED_PRUNE_DAYS))
    kept: list[dict] = []
    for entry in idx.values():
        last_seen_raw = str(entry.get("last_seen", "")).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(last_seen_raw).astimezone(timezone.utc)
        except Exception:
            kept.append(entry)  # keep broken timestamps rather than delete
            continue

        if dt >= cutoff:
            kept.append(entry)
        else:
            changed = True

    kept.sort(key=lambda e: str(e.get("url", "")))

    if not changed:
        return

    # Ensure required top-level keys exist
    data.setdefault("game_id", "")
    data.setdefault("status", "")
    if isinstance(data.get("manual"), dict):
        data["manual"].setdefault("links", [])
        data["manual"].setdefault("source_file", "")
    else:
        data["manual"] = {"links": [], "source_file": ""}

    data["discovered"] = kept
    data["updated_at"] = now_iso

    _write_url_json_atomic(json_path, data)

def update_observations_latest(
    *,
    folder_path: str,
    source: str,
    version: str,
    last_update_iso: str,
) -> None:
    """
    Update url.json with:
      observations[source] = {version, last_update_iso}
      latest = newest observation by last_update_iso
      updated_at + latest.computed_at = now

    Does nothing if url.json doesn't exist.
    """
    folder = Path(folder_path)
    json_path = folder / URL_JSON_NAME
    if not json_path.exists():
        return

    data = _load_url_json(json_path)
    now_iso = _now_iso_z()

    # Ensure observations container
    observations = data.get("observations")
    if not isinstance(observations, dict):
        observations = {}
        data["observations"] = observations

    # Write/update this source observation
    observations[source] = {
        "version": version or "",
        "last_update_iso": last_update_iso or "",
    }

    # Recompute latest (ISO strings compare lexicographically correctly)
    best_source = ""
    best_version = ""
    best_iso = ""

    for src, obs in observations.items():
        if not isinstance(obs, dict):
            continue

        iso = str(obs.get("last_update_iso", "") or "")
        ver = str(obs.get("version", "") or "")

        if not iso:
            continue

        if (not best_iso) or iso > best_iso:
            best_iso = iso
            best_version = ver
            best_source = src

    if best_iso:
        data["latest"] = {
            "source": best_source,
            "version": best_version,
            "last_update_iso": best_iso,
            "computed_at": now_iso,
        }
    else:
        # Preserve shape even if we can't compute latest
        if not isinstance(data.get("latest"), dict):
            data["latest"] = {}

    # Maintain invariants
    data.setdefault("game_id", "")
    data.setdefault("status", "")
    if not isinstance(data.get("manual"), dict):
        data["manual"] = {"links": [], "source_file": ""}

    data["updated_at"] = now_iso

    _write_url_json_atomic(json_path, data)
