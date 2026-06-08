"""Diffing: content-hash, structured fields, and product sets.

A material change = any structured field changed value. A non-material change
= content hash changed but no tracked field did (likely copy/marketing). New
/ withdrawn products come from listing-set diffs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FieldChange:
    name: str
    old: Optional[float]
    new: Optional[float]
    old_snippet: str = ""
    new_snippet: str = ""


@dataclass
class PageDiff:
    target_id: str
    issuer_key: str
    url: str
    is_baseline: bool = False
    hash_changed: bool = False
    field_changes: list[FieldChange] = field(default_factory=list)
    pdf_changes: list[dict] = field(default_factory=list)       # [{url,label,kind}]
    db_mismatches: list[FieldChange] = field(default_factory=list)

    @property
    def material(self) -> bool:
        return bool(self.field_changes) or any(p["kind"] == "changed" for p in self.pdf_changes)

    @property
    def nonmaterial(self) -> bool:
        return self.hash_changed and not self.material


_FIELD_LABELS = {
    "annual_fee": "Annual fee",
    "annual_fee_y1": "First-year fee",
    "purchase_rate": "Purchase rate",
    "cash_advance_rate": "Cash advance rate",
    "interest_free_days": "Interest-free days",
    "bonus_points": "Bonus points",
    "min_spend": "Minimum spend",
    "min_spend_months": "Min-spend window (months)",
}


def field_label(name: str) -> str:
    return _FIELD_LABELS.get(name, name)


def diff_pages(old: Optional[dict], new: dict) -> PageDiff:
    d = PageDiff(target_id=new["target_id"], issuer_key=new["issuer_key"], url=new["url"])
    if old is None:
        d.is_baseline = True
        return d

    d.hash_changed = old.get("content_hash") != new.get("content_hash")

    of, nf = old.get("fields", {}), new.get("fields", {})
    for name in _FIELD_LABELS:
        ov = (of.get(name) or {}).get("value")
        nv = (nf.get(name) or {}).get("value")
        # Only report when BOTH are known and differ — avoids "None→value" noise
        # from extractor flakiness on a single run.
        if ov is not None and nv is not None and ov != nv:
            d.field_changes.append(FieldChange(
                name, ov, nv,
                (of.get(name) or {}).get("snippet", ""),
                (nf.get(name) or {}).get("snippet", ""),
            ))

    # PDF changes
    opd, npd = old.get("pdfs", {}), new.get("pdfs", {})
    for url, meta in npd.items():
        if url not in opd:
            d.pdf_changes.append({"url": url, "label": meta.get("label", url), "kind": "new"})
        elif opd[url].get("hash") != meta.get("hash"):
            d.pdf_changes.append({"url": url, "label": meta.get("label", url), "kind": "changed"})
    for url, meta in opd.items():
        if url not in npd:
            d.pdf_changes.append({"url": url, "label": meta.get("label", url), "kind": "removed"})

    return d


def crosscheck_db(snapshot: dict, db_values: dict) -> list[FieldChange]:
    """First-run sanity: compare extracted fields against the known DB values."""
    from .extract import DB_FIELD_MAP
    out: list[FieldChange] = []
    fields = snapshot.get("fields", {})
    for db_key, ext_key in DB_FIELD_MAP.items():
        dbv = db_values.get(db_key)
        exv = (fields.get(ext_key) or {}).get("value")
        if dbv is not None and exv is not None and float(dbv) != float(exv):
            out.append(FieldChange(ext_key, float(dbv), exv,
                                   "database", (fields.get(ext_key) or {}).get("snippet", "")))
    return out


def diff_product_sets(old: Optional[dict], new_products: dict) -> dict:
    """new_products: {url: label}. Returns {added, removed, current}."""
    old_set = set((old or {}).get("products", {}).keys())
    new_set = set(new_products.keys())
    return {
        "added": sorted(new_set - old_set),
        "removed": sorted(old_set - new_set),
        "current": new_products,
    }
