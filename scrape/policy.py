from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional
import re

@dataclass(frozen=True)
class ScrapePolicy:
    # Identity / compliance
    user_agent: str = "FapScraper/1.0 (+contact: you@example.com)"
    respect_robots_txt: bool = True

    # Scope control
    allowed_domains: tuple[str, ...] = ()
    blocked_domains: tuple[str, ...] = ()
    allowed_url_regex: tuple[str, ...] = ()
    blocked_url_regex: tuple[str, ...] = ()

    # Rate limiting
    per_host_rps: float = 0.5              # requests per second per host
    per_host_burst: int = 2                # token bucket burst
    global_concurrency: int = 6
    per_host_concurrency: int = 2

    # Reliability
    timeout_s: float = 20.0
    max_retries: int = 3
    retry_backoff_base_s: float = 0.75     # exponential base
    retry_jitter_s: float = 0.25
    retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504)

    # Politeness
    min_delay_s: float = 0.0               # extra fixed delay per request if needed
    honor_retry_after: bool = True

    # Content limits
    max_response_bytes: int = 8 * 1024 * 1024  # 8 MB cap unless overridden
    accept_mime_prefixes: tuple[str, ...] = ("text/", "application/json", "application/xml")

    def url_allowed(self, url: str, host: str) -> bool:
        if self.allowed_domains and not any(host == d or host.endswith("." + d) for d in self.allowed_domains):
            return False
        if self.blocked_domains and any(host == d or host.endswith("." + d) for d in self.blocked_domains):
            return False

        for pat in self.blocked_url_regex:
            if re.search(pat, url):
                return False
        if self.allowed_url_regex:
            return any(re.search(pat, url) for pat in self.allowed_url_regex)

        return True
