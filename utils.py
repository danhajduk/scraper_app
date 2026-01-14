# scraper_app/utils.py
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from typing import Any, Optional, Tuple
from urllib.parse import urlparse

import pandas as pd

from .config import FILE_URL_PATTERNS


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _strip_na(x: Any) -> str:
    """Fix for pandas sometimes giving float NaN etc."""
    if x is None:
        return ""
    if isinstance(x, float):
        try:
            if pd.isna(x):
                return ""
        except Exception:
            pass
        return str(x)
    return str(x)


def safe_read_text_path(path) -> str:
    """Read a Path-like object as utf-8, replacing errors."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def normalize_url(url: str) -> str:
    return url.strip()


def normalize_link(url: str) -> str:
    """
    For de-duping links. Keeps behavior conservative.
    (Optional: also remove trailing slash.)
    """
    u = (url or "").strip()
    # If you want trailing slash normalization, uncomment:
    # if u.endswith("/"):
    #     u = u[:-1]
    return u


def domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def normalize_domain(d: str) -> str:
    return (d or "").lower().removeprefix("www.")


def game_id_from_url(url: str) -> str:
    """
    Tries to mimic your screenshot IDs: last path segment, underscores.
    """
    u = urlparse(url)
    segs = [s for s in u.path.split("/") if s]
    base = segs[-1] if segs else u.netloc
    base = re.sub(r"[^a-zA-Z0-9]+", "_", base).strip("_").lower()
    return base or "unknown"


def split_bracket_version(title: str) -> Tuple[str, str]:
    """
    In every line, the FIRST [...] is the version tag.
    Return (version, cleaned_title_without_any_[...]).
    """
    version = ""
    m = re.search(r"\[([^\]]+)\]", title)
    if m:
        version = m.group(1).strip()

    # Remove ALL bracketed segments for a clean display title
    cleaned = re.sub(r"\[[^\]]*\]", "", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—\t ")
    return version, cleaned


def iso_to_pretty_date(iso: str) -> str:
    """
    "2026-01-01T13:41:27Z" -> "January 1, 2026"
    """
    iso = (iso or "").strip()
    if not iso:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        dt = dt.astimezone(timezone.utc)
        return dt.strftime("%B %-d, %Y") if sys.platform != "win32" else dt.strftime("%B %#d, %Y")
    except Exception:
        return "N/A"


def pretty_date_to_dt(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s or s == "N/A":
        return None
    for fmt in ("%B %d, %Y", "%B %-d, %Y", "%B %#d, %Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def looks_like_file_url(url: str) -> bool:
    s = (url or "").lower()
    return any(re.search(pat, s) for pat in FILE_URL_PATTERNS)
