# scraper_app/sources.py
from __future__ import annotations

from .config import SUPPORTED_EXTERNAL_DOMAINS
from .utils import domain, normalize_domain


def source_from_url(url: str) -> str:
    """
    Returns a stable "source" label based on netloc.

    Rules:
    - Keep fap-nation as explicit primary site label
    - For supported domains, return the normalized supported domain
      (handles subdomains like creator.itch.io)
    - Else fallback to normalized netloc
    """
    d = domain(url)
    if not d:
        return "unknown"
    d = normalize_domain(d)

    # Primary site label
    if d.endswith("fap-nation.com"):
        return "fap-nation"

    # Supported external domains (exact or subdomain match)
    for supported in SUPPORTED_EXTERNAL_DOMAINS:
        s = normalize_domain(supported)
        if d == s or d.endswith("." + s):
            return s

    return d
