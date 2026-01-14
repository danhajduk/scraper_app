# scraper_app/ui/app.py
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Header, Footer, DataTable, Static
from textual.binding import Binding

from scraper_app.scrape.orchestrator import scrape_all
from scraper_app.storage.csv_cache import load_previous
from scraper_app.utils import _strip_na
from scraper_app.sources import source_from_url
from scraper_app.config import DEFAULT_CACHE_FILE
import webbrowser
import asyncio


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

        lines = [
            f"[b]{title}[/b]",
            "",
            f"URL: {url}",
            f"Source: {source}",
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

    def __init__(self, *, cache_file: Path, urls: list[tuple[str, str]], cookie: str = ""):
        super().__init__()
        self.cache_file = cache_file
        self.urls = urls
        self.cookie = cookie

        self.df = None
        self.row_lookup: dict[str, dict] = {}

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

    def status_icon(self, row: dict) -> str:
        if row.get("change_status") == "New":
            return "🆕"
        if row.get("change_status") == "🔁 Updated":
            return "🔁"
        if row.get("is_recent") == "⚠️ Abandoned":
            return "⚠️"
        if row.get("is_recent") == "❌ Old":
            return "⏸"
        return "✅"

    def reload(self) -> None:
        prev = load_previous(self.cache_file)
        self.df = prev
        self.apply_view()

    def apply_view(self) -> None:
        self.table.clear()
        self.row_lookup.clear()

        rows = list(self.df.values()) if self.df else []

        for i, row in enumerate(rows):
            key = row.get("url") or f"row-{i}"
            icon = self.status_icon(row)
            title = _strip_na(row.get("title"))
            self.row_lookup[key] = row
            self.table.add_row(icon, title, key=key)

        if self.table.row_count:
            self.table.cursor_coordinate = (0, 0)

        # Stats
        total = sum(1 for r in rows if r.get("is_recent") == "✅ Recent")
        new = sum(1 for r in rows if r.get("change_status") == "New")
        upd = sum(1 for r in rows if r.get("change_status") == "🔁 Updated")
        recent = sum(1 for r in rows if r.get("is_recent") == "✅ Recent")
        old = sum(1 for r in rows if r.get("is_recent") != "✅ Recent")

        self.card_total.update_value(str(total))
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
        self.run_worker(self._scrape_worker(), exclusive=True)

    async def _scrape_worker(self) -> None:
        loop = asyncio.get_running_loop()
        self.top_details.update("[b]Scraping…[/b]")

        def progress_cb(i: int, n: int, msg: str) -> None:
            pct = int((i / n) * 100) if n else 0
            self.call_from_thread(self.top_details.update, f"[b]Scraping…[/b] {pct}%\n{msg}")

        def _do():
            scrape_all(
                urls=self.urls,
                cache_file=self.cache_file,
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
