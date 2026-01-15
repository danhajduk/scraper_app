# scraper_app/config.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# -----------------------------
# Defaults (CLI)
# -----------------------------


# Per-game folder metadata
URL_JSON_NAME = "url.json"
URL_TXT_NAME = "url.txt"
URL_JSON_SCHEMA_VERSION = 1


# -----------------------------
# Recency rules
# -----------------------------

RECENT_DAYS = 21
ABANDONED_DAYS = 365


# -----------------------------
# HTTP / scraping
# -----------------------------

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# Domains we consider "interesting" for external scraping hooks / metadata
SUPPORTED_EXTERNAL_DOMAINS = (
    "itch.io",
    "www.patreon.com",
    "patreon.com",
    "store.steampowered.com",
    "steamcommunity.com",
    "lewdgames.to",
    "discord.com",
    "subscribestar.adult",
)

# Ignore URLs that look like file downloads
FILE_URL_PATTERNS = (
    r"patreon\.com/file\?",
    r"\.zip(\?|$)",
    r"\.rar(\?|$)",
    r"\.7z(\?|$)",
    r"\.exe(\?|$)",
    r"\.apk(\?|$)",
    r"\.dmg(\?|$)",
    r"\.pkg(\?|$)",
    r"\.tar(\.|$|\?)",
    r"\.gz(\.|$|\?)",
    r"\.pdf(\?|$)",
    r"\.mp4(\?|$)",
    r"\.mkv(\?|$)",
)


# -----------------------------
# Folder roots (
# -----------------------------

DEFAULT_ACTIVE_ROOT = Path("/home/dan/games/fapnation")
DEFAULT_WAITING_ROOT = Path("/home/dan/games/fapnation/Waiting update")


# -----------------------------
# Link pruning policy (future use)
# -----------------------------

DISCOVERED_PRUNE_DAYS = 10
