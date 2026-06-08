"""Git-diffable JSON snapshot store.

Layout (all committed to the repo so every change is a readable git diff):

  snapshots/<issuer_key>/<target_id>.json     one per product page (+ its PDFs)
  snapshots/_listings/<issuer_key>.json        known product set per issuer
  snapshots/_discovery/apra_adis.json          APRA ADI register snapshot
  reports/<YYYY-MM-DD>.md                       daily report

A page snapshot looks like:
{
  "target_id": "...", "issuer_key": "...", "url": "...",
  "captured_at": "2026-06-08T20:00:00Z",
  "content_hash": "…", "fields": { "annual_fee": {...}, ... },
  "pdfs": { "<pdf_url>": {"label": "...", "hash": "...", "is_terms": true} }
}
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP_DIR = os.path.join(ROOT, "snapshots")
REPORT_DIR = os.path.join(ROOT, "reports")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", s.lower()).strip("-")


def _read(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")


# ── page snapshots ──
def page_path(issuer_key: str, target_id: str) -> str:
    return os.path.join(SNAP_DIR, _slug(issuer_key), f"{_slug(target_id)}.json")


def load_page(issuer_key: str, target_id: str) -> Optional[dict]:
    return _read(page_path(issuer_key, target_id))


def save_page(snapshot: dict) -> None:
    _write(page_path(snapshot["issuer_key"], snapshot["target_id"]), snapshot)


# ── listing (product set) snapshots ──
def listing_path(issuer_key: str) -> str:
    return os.path.join(SNAP_DIR, "_listings", f"{_slug(issuer_key)}.json")


def load_listing(issuer_key: str) -> Optional[dict]:
    return _read(listing_path(issuer_key))


def save_listing(issuer_key: str, data: dict) -> None:
    _write(listing_path(issuer_key), data)


# ── discovery snapshots ──
def discovery_path(name: str) -> str:
    return os.path.join(SNAP_DIR, "_discovery", f"{_slug(name)}.json")


def load_discovery(name: str) -> Optional[dict]:
    return _read(discovery_path(name))


def save_discovery(name: str, data: dict) -> None:
    _write(discovery_path(name), data)


# ── reports ──
def report_path(date_str: str) -> str:
    return os.path.join(REPORT_DIR, f"{date_str}.md")


def save_report(date_str: str, markdown: str) -> str:
    path = report_path(date_str)
    _write_text(path, markdown)
    # Also refresh latest.md for convenience.
    _write_text(os.path.join(REPORT_DIR, "latest.md"), markdown)
    return path


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
