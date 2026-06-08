"""Configuration loader for BankWatch.

Reads config/targets.yaml and exposes typed accessors. Keeps the trusted
allowlist and per-issuer targets in one place.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config", "targets.yaml")


@dataclass
class Page:
    id: str
    url: str
    issuer_key: str
    issuer_name: str


@dataclass
class Issuer:
    key: str
    name: str
    domain: str
    listing: str
    pages: list[Page] = field(default_factory=list)


@dataclass
class Settings:
    user_agent: str
    per_domain_delay_seconds: float
    nav_timeout_seconds: float
    retries: int
    honour_robots: bool
    follow_pdf_links: bool
    new_product_confirm_runs: int


@dataclass
class Config:
    allowlist: list[str]
    settings: Settings
    issuers: list[Issuer]
    apra_adi_list: str

    def host_allowed(self, url: str) -> bool:
        """True only if the URL's host is, or is a subdomain of, an allowlisted host."""
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return False
        return any(host == d or host.endswith("." + d) for d in self.allowlist)

    def all_pages(self) -> list[Page]:
        return [p for iss in self.issuers for p in iss.pages]


@lru_cache(maxsize=1)
def load_config(path: str = CONFIG_PATH) -> Config:
    with open(path, "r", encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh)

    s = raw.get("settings", {})
    settings = Settings(
        user_agent=s.get("user_agent", "BankWatch/1.0"),
        per_domain_delay_seconds=float(s.get("per_domain_delay_seconds", 12)),
        nav_timeout_seconds=float(s.get("nav_timeout_seconds", 45)),
        retries=int(s.get("retries", 3)),
        honour_robots=bool(s.get("honour_robots", True)),
        follow_pdf_links=bool(s.get("follow_pdf_links", True)),
        new_product_confirm_runs=int(s.get("new_product_confirm_runs", 2)),
    )

    issuers: list[Issuer] = []
    for key, blk in (raw.get("issuers") or {}).items():
        iss = Issuer(
            key=key,
            name=blk["name"],
            domain=blk["domain"],
            listing=blk.get("listing", ""),
        )
        for pg in blk.get("pages", []):
            iss.pages.append(
                Page(id=pg["id"], url=pg["url"], issuer_key=key, issuer_name=blk["name"])
            )
        issuers.append(iss)

    return Config(
        allowlist=[d.lower() for d in raw.get("allowlist", [])],
        settings=settings,
        issuers=issuers,
        apra_adi_list=(raw.get("discovery") or {}).get("apra_adi_list", ""),
    )
