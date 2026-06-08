"""PDF discovery and text extraction.

On a product page we look for same-domain links to PDFs (Conditions of Use,
Rates & Fees schedules, Key Facts sheets) — these usually hold the binding
T&Cs. We fetch and extract their text so changes can be hashed/diffed exactly
like HTML sections.
"""
from __future__ import annotations

import io
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from pypdf import PdfReader

from .normalise import _WS

# Anchor text / hrefs that signal a terms document (used to prioritise & label).
_TANDC_HINT = re.compile(
    r"(terms|conditions|conditions of use|rates|fees|key facts|"
    r"important information|disclosure|schedule)",
    re.I,
)


def discover_pdf_links(html: str, base_url: str, allow_host) -> list[dict]:
    """Return [{url, label, is_terms}] for same-domain PDFs linked on the page."""
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).hostname or ""
    seen: set[str] = set()
    out: list[dict] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(base_url, href)
        if ".pdf" not in full.lower():
            continue
        if not allow_host(full):
            continue
        host = urlparse(full).hostname or ""
        if not (host == base_host or host.endswith("." + base_host) or base_host.endswith("." + host)):
            # keep strictly same-site PDFs
            if not allow_host(full):
                continue
        if full in seen:
            continue
        seen.add(full)
        label = _WS.sub(" ", a.get_text(" ").strip())[:120] or full.rsplit("/", 1)[-1]
        out.append({
            "url": full,
            "label": label,
            "is_terms": bool(_TANDC_HINT.search(label) or _TANDC_HINT.search(full)),
        })
    # Terms-like docs first.
    out.sort(key=lambda d: (not d["is_terms"], d["label"]))
    return out


def extract_pdf_text(body: bytes) -> str:
    """Extract a canonical, comparison-stable text string from PDF bytes."""
    try:
        reader = PdfReader(io.BytesIO(body))
    except Exception as e:
        return f"«pdf-unreadable: {type(e).__name__}»"
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n".join(parts).lower().replace("\xa0", " ")
    lines = [_WS.sub(" ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)
