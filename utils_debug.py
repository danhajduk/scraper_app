# scraper_app/utils_debug.py
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEBUG = os.getenv("SCRAPER_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
_LOG_PATH = os.getenv("SCRAPER_DEBUG_LOG", "").strip()

def dbg(tag: str, **kv: Any) -> None:
    if not _DEBUG:
        return

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    parts = [f"{ts} [{tag}]"]
    for k, v in kv.items():
        parts.append(f"{k}={v!r}")
    line = " ".join(parts)

    if _LOG_PATH:
        try:
            Path(_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            # If file logging fails, fall back to stdout
            print(line)
    else:
        print(line)
