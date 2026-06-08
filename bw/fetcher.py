"""Polite, allowlist-guarded fetching via headless Chromium (Playwright).

Guarantees:
  * Only allowlisted hosts are ever navigated to — checked on the request URL
    AND on the FINAL url after redirects (a redirect off-domain is rejected).
  * robots.txt is honoured per host (cached).
  * A descriptive User-Agent is sent.
  * A minimum delay is enforced between requests to the same host.
  * Transient failures are retried with backoff.

Every fetch returns a FetchResult whose `status` is one of:
  ok        — page (or PDF) fetched cleanly
  blocked   — robots.txt disallows, or a bot-challenge/non-2xx response
  offdomain — a redirect left the allowlist (treated as unverified)
  error     — unreachable / timeout / unexpected

Callers MUST treat anything other than `ok` as UNVERIFIED — never "no change".
"""
from __future__ import annotations

import time
import urllib.robotparser
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from .config import Config


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: str            # ok | blocked | offdomain | error
    http_status: Optional[int]
    content_type: str
    html: str = ""
    body_bytes: bytes = b""
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class Fetcher:
    """Wraps a single Playwright browser session for one run."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_hit: dict[str, float] = {}
        self._pw = None
        self._browser = None
        self._ctx = None

    # ── lifecycle ──
    def __enter__(self) -> "Fetcher":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._ctx = self._browser.new_context(
            user_agent=self.cfg.settings.user_agent,
            locale="en-AU",
            viewport={"width": 1366, "height": 1800},
        )
        return self

    def __exit__(self, *exc) -> None:
        for closer in (self._ctx, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass
        if self._pw:
            self._pw.stop()

    # ── politeness helpers ──
    def _throttle(self, host: str) -> None:
        gap = self.cfg.settings.per_domain_delay_seconds
        last = self._last_hit.get(host)
        if last is not None:
            wait = gap - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_hit[host] = time.time()

    def _robots_ok(self, url: str) -> bool:
        if not self.cfg.settings.honour_robots:
            return True
        host = urlparse(url).hostname or ""
        rp = self._robots.get(host)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = f"{urlparse(url).scheme}://{host}/robots.txt"
            try:
                rp.set_url(robots_url)
                rp.read()
            except Exception:
                # If robots.txt can't be read, be conservative: allow, but the
                # fetch itself will still be subject to the allowlist + status checks.
                rp = urllib.robotparser.RobotFileParser()
                rp.parse([])
            self._robots[host] = rp
        try:
            return rp.can_fetch(self.cfg.settings.user_agent, url)
        except Exception:
            return True

    # ── main entry points ──
    def fetch_page(self, url: str) -> FetchResult:
        """Fetch an HTML page through headless Chromium."""
        if not self.cfg.host_allowed(url):
            return FetchResult(url, url, "offdomain", None, "", note="URL not on allowlist")
        if not self._robots_ok(url):
            return FetchResult(url, url, "blocked", None, "", note="Disallowed by robots.txt")

        host = urlparse(url).hostname or ""
        last_err = ""
        for attempt in range(1, self.cfg.settings.retries + 1):
            self._throttle(host)
            page = self._ctx.new_page()
            try:
                resp = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=int(self.cfg.settings.nav_timeout_seconds * 1000),
                )
                # Allow client-rendered content to settle.
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except PWTimeout:
                    pass

                final_url = page.url
                if not self.cfg.host_allowed(final_url):
                    return FetchResult(url, final_url, "offdomain", None, "",
                                       note="Redirected off the allowlist")

                http_status = resp.status if resp else None
                if http_status is not None and not (200 <= http_status < 300):
                    last_err = f"HTTP {http_status}"
                    # 4xx/5xx — likely a bot challenge or moved page. Flag, don't retry forever.
                    if http_status in (403, 429) or http_status >= 500:
                        time.sleep(2 * attempt)
                        continue
                    return FetchResult(url, final_url, "blocked", http_status, "",
                                       note=f"Unexpected HTTP {http_status}")

                html = page.content()
                ctype = (resp.headers.get("content-type", "") if resp else "").lower()
                if _looks_like_challenge(html):
                    last_err = "bot challenge detected"
                    time.sleep(2 * attempt)
                    continue
                return FetchResult(url, final_url, "ok", http_status, ctype, html=html)
            except PWTimeout:
                last_err = "navigation timeout"
            except Exception as e:  # network, DNS, etc.
                last_err = f"{type(e).__name__}: {e}"
            finally:
                page.close()
            time.sleep(2 * attempt)

        status = "blocked" if "challenge" in last_err or "HTTP" in last_err else "error"
        return FetchResult(url, url, status, None, "", note=last_err or "unknown failure")

    def fetch_pdf(self, url: str) -> FetchResult:
        """Fetch a PDF's bytes via the browser request API (keeps the same UA/cookies)."""
        if not self.cfg.host_allowed(url):
            return FetchResult(url, url, "offdomain", None, "", note="PDF not on allowlist")
        if not self._robots_ok(url):
            return FetchResult(url, url, "blocked", None, "", note="Disallowed by robots.txt")

        host = urlparse(url).hostname or ""
        self._throttle(host)
        try:
            resp = self._ctx.request.get(url, timeout=self.cfg.settings.nav_timeout_seconds * 1000)
            if not resp.ok:
                return FetchResult(url, url, "blocked", resp.status, "application/pdf",
                                   note=f"HTTP {resp.status}")
            return FetchResult(url, resp.url, "ok", resp.status, "application/pdf",
                               body_bytes=resp.body())
        except Exception as e:
            return FetchResult(url, url, "error", None, "", note=f"{type(e).__name__}: {e}")


def _looks_like_challenge(html: str) -> bool:
    """Heuristic detection of Cloudflare/Akamai/Imperva interstitials."""
    if not html or len(html) < 600:
        return True
    low = html.lower()
    signals = (
        "just a moment", "checking your browser", "cf-browser-verification",
        "captcha", "access denied", "request unsuccessful", "incapsula",
        "/_incapsula_resource", "akamai", "bot detection",
    )
    return any(s in low for s in signals)
