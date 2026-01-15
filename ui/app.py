# scraper_app/ui/app.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import asyncio
import json
import webbrowser

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Header, Footer, DataTable, Static
from textual.binding import Binding

from scraper_app.config import DEFAULT_ACTIVE_ROOT, DEFAULT_WAITING_ROOT, URL_JSON_NAME
from scraper_app.scrape.orchestrator import scrape_all, ScrapeItem, classify_recency
from scraper_app.sources import source_from_url
from scraper_app.storage.game_folders import collect_urls_from_library
from scraper_app.utils import _strip_na, iso_to_pretty_date


# ----------------------------
# Small UI widgets
# ----------------------------

class StatCard(Static):
    def __init__(self, label: str, icon: str = ""):
        super().__init__()
        self.label = label
        self.icon = icon
        self.value = "0"

    def update_value(self, v: str) -> None:
        self.value = v
        self.update(f"{self.icon} {self.label}\n[b]{v}[/b]")


class Details(Static):
    can_focus = True

    def show_game(self, row: dict) -> None:
        if not row:
            self.update("Select a row…")
            return

        title = _strip_na(row.get("title")) or "N/A"
        version = _strip_na(row.get("version")) or "-"
        last_update = _strip_na(row.get("last_update")) or "N/A"
        is_recent = _strip_na(row.get("is_recent"))
        change_status = _strip_na(row.get("change_status"))
        source = _strip_na(row.get("source"))
        url = _strip_na(row.get("url"))
        folder = _strip_na(row.get("folder_path"))
        status = _strip_na(row.get("status"))

        lines = [
            f"[b]{title}[/b]",
            "",
            f"URL: {url}",
            f"Source: {source}",
            f"Folder: {folder}",
            f"Library Status: {status}",
            f"Updated: {last_update}",
            f"Version/Status: {version} | {is_recent} · {change_status}",
            "",
        ]

        links_raw = _strip_na(row.get("external_links"))
        links = [u for u in links_raw.split("|") if u.strip()] if links_raw else []

        if links:
            lines.append("[b]Links:[/b]")
            for i, u in enumerate(links, start=1):
                lines.append(f"{i}. {u}")

        self.update("\n".join(lines))
        self.scroll_home()


# ----------------------------
# Main App
# ----------------------------

class ScrapeApp(App):
    CSS = """
    Screen {
        background: #101417;
        color: #e8eef2;
    }

    #stats_row {
        height: 4;
        margin: 1 1 1 1;
    }

    StatCard {
        width: 1fr;
        border: tall #2d3a45;
        padding: 0 2;
        background: #0b0f12;
    }

    #left_pane {
        width: 2fr;
        margin-right: 1;
    }

    #top_details {
        height: 4;
        border: tall #2d3a45;
        padding: 0 1;
        margin-bottom: 1;
        background: #0b0f12;
    }

    #list_box {
        height: 1fr;
        border: tall #2d3a45;
    }

    #details_box {
        width: 1fr;
        border: tall #2d3a45;
        padding: 0 1;
        background: #0b0f12;
    }

    #side_details {
        height: 100%;
        overflow-y: auto;
    }

    DataTable {
        height: 100%;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("a", "filter_all", "All"),
        Binding("n", "filter_new", "New"),
        Binding("u", "filter_updated", "Updated"),
        Binding("c", "filter_recent", "Recent"),
        Binding("o", "filter_old", "Old"),
        Binding("s", "toggle_sort", "Sort"),
        Binding("enter", "focus_details", "Details"),
        Binding("escape", "focus_list", "List"),
        Binding("O", "open_url", "Open"),
    ]

    filter_mode = reactive("all")
    sort_mode = reactive("updated_desc")

    def __init__(
        self,
        *,
        active_root: Path = DEFAULT_ACTIVE_ROOT,
        waiting_root: Path = DEFAULT_WAITING_ROOT,
        cookie: str = "",
        urls: list[ScrapeItem] = None,
    ):
        super().__init__()
        self.active_root = Path(active_root).expanduser().resolve()
        self.waiting_root = Path(waiting_root).expanduser().resolve()
        self.cookie = cookie
        self.urls = urls or []

        self.rows: list[dict] = []
        self.row_lookup: dict[str, dict] = {}

        # Snapshot of last_update_iso per url taken right before a scrape,
        # used to compute New/Updated/Unchanged without CSV.
        self._baseline_iso: dict[str, str] = {}

    # ----------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal(id="stats_row"):
            self.card_total = StatCard("Active", "📦")
            self.card_new = StatCard("New", "🆕")
            self.card_updated = StatCard("Updated", "🔁")
            self.card_recent = StatCard("Recent", "✅")
            self.card_old = StatCard("Old", "⚠️")
            yield self.card_total
            yield self.card_new
            yield self.card_updated
            yield self.card_recent
            yield self.card_old

        with Horizontal():
            with Container(id="left_pane"):
                self.top_details = Details("Ready.", id="top_details")
                yield self.top_details

                self.table = DataTable(zebra_stripes=True, id="list_box")
                yield self.table

            with Container(id="details_box"):
                self.side_details = Details("Select a row…", id="side_details")
                yield self.side_details

        yield Footer()

    # ----------------------------

    def on_mount(self) -> None:
        self.table.add_column("", width=2)
        self.table.add_column("Title")

        self.table.cursor_type = "row"
        self.table.focus()

        self.reload()
        self.call_after_refresh(self.start_scrape)

    # ----------------------------

    def _load_folder_json(self, folder: Path) -> dict:
        p = folder / URL_JSON_NAME
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _last_update_iso_for(self, meta: dict, url: str) -> str:
        src = source_from_url(url)
        obs = meta.get("observations")
        if isinstance(obs, dict):
            entry = obs.get(src)
            if isinstance(entry, dict):
                return str(entry.get("last_update_iso", "") or "")
        return ""

    def _version_for(self, meta: dict, url: str) -> str:
        src = source_from_url(url)
        obs = meta.get("observations")
        if isinstance(obs, dict):
            entry = obs.get(src)
            if isinstance(entry, dict):
                return str(entry.get("version", "") or "")
        return ""

    def _discovered_links(self, meta: dict) -> list[str]:
        out: list[str] = []
        disc = meta.get("discovered")
        if not isinstance(disc, list):
            return out
        for entry in disc:
            if not isinstance(entry, dict):
                continue
            u = str(entry.get("url", "") or "").strip()
            if u:
                out.append(u)
        return out

    def _build_rows(self) -> list[dict]:
        folder_items = collect_urls_from_library(active_root=self.active_root, waiting_root=self.waiting_root)
        rows: list[dict] = []

        for it in folder_items:
            meta = self._load_folder_json(it.folder)
            game_id = str(meta.get("game_id", "") or "") or it.forced_game_id
            status = str(meta.get("status", "") or "") or it.status

            updated_iso = self._last_update_iso_for(meta, it.url)
            version = self._version_for(meta, it.url)

            last_update = iso_to_pretty_date(updated_iso) if updated_iso else "N/A"
            is_recent = classify_recency(updated_iso) if updated_iso else "❌ Old"

            # baseline-based change status computed later in apply_view()
            row = {
                "url": it.url,
                "source": source_from_url(it.url),
                "game_id": game_id,
                "status": status,
                "title": game_id or it.forced_game_id or "N/A",
                "raw_title": game_id or "N/A",
                "version": version or "-",
                "updated_utc_iso": updated_iso,
                "last_update": last_update,
                "is_recent": is_recent,
                "change_status": "-",  # filled after scrape snapshot compare
                "external_links": "|".join(self._discovered_links(meta)),
                "folder_path": str(it.folder),
            }
            rows.append(row)

        return rows

    def status_icon(self, row: dict) -> str:
        # Prioritize change state
        cs = row.get("change_status")
        if cs == "New":
            return "🆕"
        if cs == "🔁 Updated":
            return "🔁"

        # Then recency
        if row.get("is_recent") == "⚠️ Abandoned":
            return "⚠️"
        if row.get("is_recent") == "❌ Old":
            return "⏸"
        return "✅"

    def reload(self) -> None:
        self.rows = self._build_rows()
        self.apply_view()

    def apply_view(self) -> None:
        self.table.clear()
        self.row_lookup.clear()

        rows = list(self.rows)

        # Compute change_status using baseline snapshot
        for r in rows:
            url = str(r.get("url") or "")
            now_iso = str(r.get("updated_utc_iso") or "")
            was_iso = self._baseline_iso.get(url, "")

            if not was_iso:
                r["change_status"] = "New" if now_iso else "-"
            else:
                if now_iso and now_iso > was_iso:
                    r["change_status"] = "🔁 Updated"
                else:
                    r["change_status"] = "Unchanged"

        # Filtering
        if self.filter_mode == "new":
            rows = [r for r in rows if r.get("change_status") == "New"]
        elif self.filter_mode == "updated":
            rows = [r for r in rows if r.get("change_status") == "🔁 Updated"]
        elif self.filter_mode == "recent":
            rows = [r for r in rows if r.get("is_recent") == "✅ Recent"]
        elif self.filter_mode == "old":
            rows = [r for r in rows if r.get("is_recent") != "✅ Recent"]

        # Sorting
        if self.sort_mode == "title":
            rows.sort(key=lambda r: _strip_na(r.get("title")).lower())
        else:
            # updated_desc
            rows.sort(key=lambda r: str(r.get("updated_utc_iso") or ""), reverse=True)

        for i, row in enumerate(rows):
            key = row.get("url") or f"row-{i}"
            icon = self.status_icon(row)
            title = _strip_na(row.get("title"))
            self.row_lookup[key] = row
            self.table.add_row(icon, title, key=key)

        if self.table.row_count:
            self.table.cursor_coordinate = (0, 0)

        # Stats
        total_active = sum(1 for r in rows if r.get("status") == "active")
        new = sum(1 for r in rows if r.get("change_status") == "New")
        upd = sum(1 for r in rows if r.get("change_status") == "🔁 Updated")
        recent = sum(1 for r in rows if r.get("is_recent") == "✅ Recent")
        old = sum(1 for r in rows if r.get("is_recent") != "✅ Recent")

        self.card_total.update_value(str(total_active))
        self.card_new.update_value(str(new))
        self.card_updated.update_value(str(upd))
        self.card_recent.update_value(str(recent))
        self.card_old.update_value(str(old))

    # ----------------------------
    # Actions
    # ----------------------------

    def action_focus_details(self) -> None:
        self.side_details.focus()

    def action_focus_list(self) -> None:
        self.table.focus()

    def action_open_url(self) -> None:
        key = self.table.cursor_row_key
        if not key:
            return
        row = self.row_lookup.get(key)
        if not row:
            return
        url = row.get("url")
        if url:
            webbrowser.open(url)

    async def action_refresh(self) -> None:
        self.start_scrape()

    def start_scrape(self) -> None:
        # Take baseline snapshot for New/Updated status
        self._baseline_iso = {}
        current_rows = self._build_rows()
        for r in current_rows:
            url = str(r.get("url") or "")
            iso = str(r.get("updated_utc_iso") or "")
            if url:
                self._baseline_iso[url] = iso

        self.run_worker(self._scrape_worker(), exclusive=True)

    async def _scrape_worker(self) -> None:
        loop = asyncio.get_running_loop()
        self.top_details.update("[b]Scraping…[/b]")

        # Build ScrapeItems fresh each run (in case folders change)
        folder_items = collect_urls_from_library(active_root=self.active_root, waiting_root=self.waiting_root)
        scrape_items = [
            ScrapeItem(
                url=it.url,
                forced_game_id=it.forced_game_id,
                folder_path=str(it.folder),
                folder_status=it.status,
            )
            for it in folder_items
        ]

        def progress_cb(i: int, n: int, msg: str) -> None:
            pct = int((i / n) * 100) if n else 0
            self.call_from_thread(self.top_details.update, f"[b]Scraping…[/b] {pct}%\n{msg}")

        def _do():
            scrape_all(
                urls=scrape_items,
                cache_file="cache.json",  # Example cache file path
                cookie=self.cookie,
                print_updates_only=False,
                progress_cb=progress_cb,
            )

        await loop.run_in_executor(None, _do)
        self.reload()
        self.top_details.update("✅ Scrape finished.")

    # ----------------------------

    def action_filter_all(self) -> None:
        self.filter_mode = "all"
        self.apply_view()

    def action_filter_new(self) -> None:
        self.filter_mode = "new"
        self.apply_view()

    def action_filter_updated(self) -> None:
        self.filter_mode = "updated"
        self.apply_view()

    def action_filter_recent(self) -> None:
        self.filter_mode = "recent"
        self.apply_view()

    def action_filter_old(self) -> None:
        self.filter_mode = "old"
        self.apply_view()

    def action_toggle_sort(self) -> None:
        self.sort_mode = "title" if self.sort_mode == "updated_desc" else "updated_desc"
        self.apply_view()

    def on_data_table_row_highlighted(self, event: Any) -> None:
        key = event.row_key.value if event.row_key else ""
        row = self.row_lookup.get(key)
        self.side_details.show_game(row or {})
