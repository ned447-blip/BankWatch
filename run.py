#!/usr/bin/env python3
"""BankWatch orchestrator.

For each known issuer:
  * fetch each product page (headless Chromium, allowlist-guarded)
  * extract canonical text → hash + structured fields
  * discover + fetch + hash same-domain T&C PDFs
  * diff against the committed JSON snapshot
  * fetch the listing page → diff the product set (Tier-1 discovery)
Then Tier-2: snapshot + diff the APRA ADI register for new-issuer candidates.

Anything not fetched cleanly is recorded as UNVERIFIED — never "no change".

Writes updated snapshots + a Markdown report, both committed by CI.

Usage:
  python run.py                 # full run
  python run.py --issuer anz    # one issuer
  python run.py --no-pdfs       # skip PDF monitoring (faster smoke test)
  python run.py --dry-run       # fetch + diff, write report, but DON'T update baselines
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

# Local card-DB values for the first-run cross-check (optional; safe if absent).
try:
    from card_db_values import DB_VALUES  # generated map: {target_id: {annualFee,...}}
except Exception:
    DB_VALUES = {}

from bw.config import load_config
from bw.fetcher import Fetcher
from bw import normalise, pdfs, extract, store, differ, discovery, reporter, emailer


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_aest() -> str:
    # Australia/Sydney calendar date (handles AEST/AEDT); falls back to UTC.
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Australia/Sydney")).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def build_page_snapshot(cfg, page, fr, follow_pdfs, fetcher) -> dict:
    canon = normalise.canonicalise(fr.html)
    snap = {
        "target_id": page.id,
        "issuer_key": page.issuer_key,
        "url": fr.final_url,
        "captured_at": now_iso(),
        "content_hash": normalise.sha256(canon),
        "fields": extract.extract_fields(canon),
        "pdfs": {},
    }
    if follow_pdfs and cfg.settings.follow_pdf_links:
        for link in pdfs.discover_pdf_links(fr.html, fr.final_url, cfg.host_allowed):
            pr = fetcher.fetch_pdf(link["url"])
            if pr.ok:
                ptext = pdfs.extract_pdf_text(pr.body_bytes)
                snap["pdfs"][link["url"]] = {
                    "label": link["label"],
                    "is_terms": link["is_terms"],
                    "hash": normalise.sha256(ptext),
                }
            # PDF fetch failures are folded into the page's unverified note by caller.
    return snap


def main() -> int:
    ap = argparse.ArgumentParser(description="BankWatch — AU bank card T&C monitor")
    ap.add_argument("--issuer", help="only run this issuer key")
    ap.add_argument("--no-pdfs", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    issuers = [i for i in cfg.issuers if (not args.issuer or i.key == args.issuer)]

    page_diffs: list[differ.PageDiff] = []
    baselines: list[differ.PageDiff] = []
    unverified: list[dict] = []
    new_products: list[dict] = []
    withdrawn_products: list[dict] = []
    candidates: list[str] = []
    checked = 0

    with Fetcher(cfg) as fetcher:
        for iss in issuers:
            # ── product pages ──
            for page in iss.pages:
                checked += 1
                fr = fetcher.fetch_page(page.url)
                if not fr.ok:
                    unverified.append({
                        "issuer_key": iss.key, "target_id": page.id, "url": page.url,
                        "status": fr.status, "note": fr.note or "unverified",
                    })
                    continue

                snap = build_page_snapshot(cfg, page, fr, not args.no_pdfs, fetcher)
                old = store.load_page(iss.key, page.id)
                d = differ.diff_pages(old, snap)

                # First-run cross-check against the card database.
                if d.is_baseline and page.id in DB_VALUES:
                    d.db_mismatches = differ.crosscheck_db(snap, DB_VALUES[page.id])

                if d.is_baseline:
                    baselines.append(d)
                else:
                    page_diffs.append(d)

                if not args.dry_run:
                    store.save_page(snap)

            # ── listing page → Tier-1 product-set discovery ──
            if iss.listing:
                checked += 1
                lr = fetcher.fetch_page(iss.listing)
                if not lr.ok:
                    unverified.append({
                        "issuer_key": iss.key, "target_id": "_listing", "url": iss.listing,
                        "status": lr.status, "note": lr.note or "unverified",
                    })
                else:
                    products = discovery.extract_products(lr.html, lr.final_url, cfg.host_allowed)
                    prev = store.load_listing(iss.key)
                    setdiff = differ.diff_product_sets(prev, products)

                    # Confirm-over-N-runs gate for new products.
                    pending = (prev or {}).get("pending", {})
                    confirmed_now = []
                    for url in setdiff["added"]:
                        seen = pending.get(url, 0) + 1
                        pending[url] = seen
                        if seen >= cfg.settings.new_product_confirm_runs:
                            confirmed_now.append(url)
                    for url in list(pending.keys()):
                        if url not in products:
                            pending.pop(url, None)   # vanished before confirming
                    for url in confirmed_now:
                        new_products.append({
                            "issuer_key": iss.key, "url": url,
                            "label": products.get(url, url),
                            "seen_runs": pending.get(url, cfg.settings.new_product_confirm_runs),
                        })
                        pending.pop(url, None)
                    for url in setdiff["removed"]:
                        withdrawn_products.append({"issuer_key": iss.key, "url": url})

                    if not args.dry_run:
                        store.save_listing(iss.key, {
                            "issuer_key": iss.key, "captured_at": now_iso(),
                            "products": products, "pending": pending,
                        })

        # ── Tier-2: APRA ADI register ──
        if not args.issuer and cfg.apra_adi_list:
            checked += 1
            ar = fetcher.fetch_page(cfg.apra_adi_list)
            if not ar.ok:
                unverified.append({
                    "issuer_key": "discovery", "target_id": "apra_adis",
                    "url": cfg.apra_adi_list, "status": ar.status, "note": ar.note,
                })
            else:
                adis = discovery.extract_adis(ar.html)
                prev = store.load_discovery("apra_adis")
                addiff = discovery.diff_adis((prev or {}).get("current"), adis)
                candidates = addiff["added"]
                if not args.dry_run and adis:
                    store.save_discovery("apra_adis", {"captured_at": now_iso(), "current": adis})

    date_str = today_aest()
    md = reporter.build_report(
        date_str=date_str, page_diffs=page_diffs, baselines=baselines,
        unverified=unverified, new_products=new_products,
        withdrawn_products=withdrawn_products, candidates=candidates,
        checked_total=checked,
    )
    path = store.save_report(date_str, md)

    n_material = sum(d.material for d in page_diffs)
    print(f"BankWatch run complete → {path}")
    print(f"  checked={checked}  material={n_material}  "
          f"new={len(new_products)}  unverified={len(unverified)}  baselines={len(baselines)}")

    # Email notification — only fires if there is something to act on.
    if not args.dry_run and emailer.should_send(
        n_material, len(new_products), len(withdrawn_products), len(unverified)
    ):
        emailer.send(
            date_str=date_str, report_markdown=md,
            material=n_material, new_products=len(new_products),
            withdrawn=len(withdrawn_products), unverified=len(unverified),
        )

    # Non-zero exit if anything needs a human, so CI can surface it.
    return 2 if unverified else 0


if __name__ == "__main__":
    sys.exit(main())
