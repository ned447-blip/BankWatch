"""HTML → canonical text, with aggressive removal of cosmetic noise.

The goal: two fetches of an UNCHANGED page must produce byte-identical
canonical text (and therefore the same SHA-256), even if the markup,
script nonces, session tokens, ad slots or whitespace differ.
"""
from __future__ import annotations

import hashlib
import re

from bs4 import BeautifulSoup, Comment

# Tags that never carry meaningful T&C content.
_DROP_TAGS = [
    "script", "style", "noscript", "svg", "canvas", "iframe", "template",
    "header", "footer", "nav", "form", "button", "input", "select",
]

# Elements commonly used for chrome/ads/analytics — dropped by id/class hints.
_DROP_HINTS = re.compile(
    r"(cookie|consent|banner|promo|advert|ad-|-ad|carousel|chat|live-?chat|"
    r"breadcrumb|share|social|newsletter|subscribe|footer|header|nav|menu|"
    r"skip-link|back-to-top|recommend|related|cross-?sell)",
    re.I,
)

# Volatile substrings to neutralise before hashing (dates, ids, nonces).
_DATE = re.compile(
    r"\b(\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|"
    r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b",
    re.I,
)
_NONCE = re.compile(r'\b(nonce|csrf|sessionid|requestid|token)="?[\w\-]{6,}"?', re.I)
_WS = re.compile(r"\s+")


def extract_main_text(html: str) -> str:
    """Return readable text from the main content region of a page."""
    soup = BeautifulSoup(html, "html.parser")

    for el in soup.find_all(string=lambda s: isinstance(s, Comment)):
        el.extract()
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    for tag in soup.find_all(attrs={"class": _DROP_HINTS}):
        tag.decompose()
    for tag in soup.find_all(attrs={"id": _DROP_HINTS}):
        tag.decompose()

    # Prefer an explicit main/article/role=main region if present.
    main = (
        soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.find("article")
        or soup.body
        or soup
    )
    return main.get_text(separator="\n")


def canonicalise(html: str) -> str:
    """Canonical, comparison-stable text for hashing."""
    text = extract_main_text(html)
    text = text.lower()
    text = _DATE.sub("«date»", text)
    text = _NONCE.sub("«id»", text)
    # Normalise non-breaking spaces and collapse whitespace.
    text = text.replace("\xa0", " ")
    lines = [_WS.sub(" ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
