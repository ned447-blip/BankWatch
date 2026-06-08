"""Discovery.

Tier 1 — within KNOWN issuers: parse each issuer's card-listing page and
diff the set of product links against last run. New links that persist for
`new_product_confirm_runs` runs are reported as confirmed-new products —
sourced directly from the bank's own site.

Tier 2 — NEW issuers we don't track: snapshot APRA's register of Authorised
Deposit-taking Institutions (the legal list of Australian banks/credit
unions) and diff it. A newly-licensed ADI surfaces as a CANDIDATE for your
review. Candidates are never scraped for card data — once you approve one,
add it to targets.yaml and Tier 1 takes over.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# Links on a card-listing page that look like individual card products.
_CARD_LINK = re.compile(r"(credit-card|/card[s]?/|rewards|frequent-flyer|qantas|velocity|platinum|black)", re.I)
_NOISE = re.compile(r"(compare|help|support|login|apply|terms|contact|search|#|\.pdf$)", re.I)


def extract_products(html: str, listing_url: str, allow_host) -> dict:
    """Return {product_url: anchor_label} for plausible card links on a listing page."""
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(listing_url).hostname or ""
    products: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(listing_url, href.split("#")[0]).rstrip("/")
        host = urlparse(full).hostname or ""
        if not (host == base_host or host.endswith("." + base_host)):
            continue
        if not allow_host(full):
            continue
        if _NOISE.search(full) or not _CARD_LINK.search(full):
            continue
        label = re.sub(r"\s+", " ", a.get_text(" ").strip())[:120]
        if len(label) < 3:
            continue
        products.setdefault(full, label)
    return products


# ── APRA ADI register (Tier 2) ──
_ADI_NOISE = re.compile(r"(apra|register|authorised|deposit|institution|home|search|menu|skip|privacy|copyright)", re.I)


def extract_adis(html: str) -> list[str]:
    """Best-effort list of ADI institution names from the APRA register page."""
    soup = BeautifulSoup(html, "html.parser")
    names: set[str] = set()

    # APRA publishes the register as a table; fall back to list items.
    for cell in soup.select("table td, table th"):
        t = re.sub(r"\s+", " ", cell.get_text(" ").strip())
        if 3 < len(t) < 90 and not _ADI_NOISE.search(t) and re.search(r"[A-Za-z]", t):
            names.add(t)
    if len(names) < 5:
        for li in soup.select("li"):
            t = re.sub(r"\s+", " ", li.get_text(" ").strip())
            if 3 < len(t) < 90 and not _ADI_NOISE.search(t):
                names.add(t)
    return sorted(names)


def diff_adis(old: list[str] | None, new: list[str]) -> dict:
    old_set = set(old or [])
    new_set = set(new)
    # Only surface additions if we had a meaningful baseline (avoids a flood on first run).
    added = sorted(new_set - old_set) if old else []
    return {"added": added, "removed": sorted(old_set - new_set) if old else [], "current": new}
