#!/usr/bin/env python3
"""Offline self-test — verifies the detection logic with NO network access.

Exercises the pieces that must be correct for accuracy:
  * canonicalisation ignores cosmetic/markup/date noise (same hash)
  * canonicalisation detects a real fee change (different hash)
  * structured extraction reads fee/rate/bonus
  * the differ reports a material field change and a baseline correctly
  * product-set diff finds an added card

Run: python selftest.py   → prints PASS/FAIL per check, exits non-zero on any failure.
"""
from __future__ import annotations

import sys

from bw import normalise, extract, differ

PASS, FAIL = "✅ PASS", "❌ FAIL"
results: list[bool] = []


def check(name: str, cond: bool) -> None:
    results.append(cond)
    print(f"  {PASS if cond else FAIL}  {name}")


PAGE_V1 = """
<html><head><script>var nonce='abc123def456';</script><style>.x{color:red}</style></head>
<body>
  <header><nav>Home About Login</nav></header>
  <div class="cookie-banner">We use cookies</div>
  <main>
    <h1>CommBank Ultimate Awards</h1>
    <p>Annual fee $420 p.a.</p>
    <p>Purchase rate 20.99% p.a. Cash advance 21.99% p.a.</p>
    <p>Up to 55 days interest-free.</p>
    <p>Earn 60,000 bonus points when you spend $9,000 on eligible purchases in the first 90 days.</p>
    <p>Information correct as at 7 June 2026.</p>
  </main>
  <footer>© 2026 Commonwealth Bank</footer>
</body></html>
"""

# Same facts, different markup / date / nonce / whitespace / cookie text → MUST hash identically.
PAGE_V1_COSMETIC = """
<html><head><script>var nonce='ZZZ999';</script></head>
<body>
  <header><nav>Home   About   Login</nav></header>
  <div class="cookie-banner">We value your privacy</div>
  <article>
    <h1>CommBank   Ultimate   Awards</h1>
    <p>Annual fee   $420   p.a.</p>
    <p>Purchase rate 20.99% p.a. Cash advance 21.99% p.a.</p>
    <p>Up to 55 days interest-free.</p>
    <p>Earn 60,000 bonus points when you spend $9,000 on eligible purchases in the first 90 days.</p>
    <p>Information correct as at 9 June 2026.</p>
  </article>
  <footer>© 2026 CBA</footer>
</body></html>
"""

# Real change: annual fee 420 → 450.
PAGE_V2 = PAGE_V1.replace("$420", "$450")


def main() -> int:
    c1 = normalise.canonicalise(PAGE_V1)
    c1b = normalise.canonicalise(PAGE_V1_COSMETIC)
    c2 = normalise.canonicalise(PAGE_V2)

    print("Canonicalisation / hashing:")
    check("cosmetic-only change → identical hash",
          normalise.sha256(c1) == normalise.sha256(c1b))
    check("real fee change → different hash",
          normalise.sha256(c1) != normalise.sha256(c2))

    print("Structured extraction:")
    f = extract.extract_fields(c1)
    check("annual fee = 420", (f["annual_fee"]["value"]) == 420)
    check("purchase rate = 20.99", (f["purchase_rate"]["value"]) == 20.99)
    check("cash advance = 21.99", (f["cash_advance_rate"]["value"]) == 21.99)
    check("interest-free days = 55", (f["interest_free_days"]["value"]) == 55)
    check("bonus points = 60000", (f["bonus_points"]["value"]) == 60000)

    print("Differ:")
    snap1 = {"target_id": "cba-ultimate", "issuer_key": "commbank", "url": "u",
             "content_hash": normalise.sha256(c1), "fields": f, "pdfs": {}}
    snap2 = {"target_id": "cba-ultimate", "issuer_key": "commbank", "url": "u",
             "content_hash": normalise.sha256(c2), "fields": extract.extract_fields(c2), "pdfs": {}}
    base = differ.diff_pages(None, snap1)
    check("first run = baseline", base.is_baseline)
    d = differ.diff_pages(snap1, snap2)
    check("fee change is material", d.material)
    check("reports 420 → 450",
          any(fc.old == 420 and fc.new == 450 for fc in d.field_changes))

    print("Product-set discovery:")
    sd = differ.diff_product_sets(
        {"products": {"https://x/card-a": "A"}},
        {"https://x/card-a": "A", "https://x/card-b": "B"},
    )
    check("new card detected", sd["added"] == ["https://x/card-b"])

    ok = all(results)
    print(f"\n{'ALL PASSED' if ok else 'SOME FAILED'} — {sum(results)}/{len(results)} checks")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
