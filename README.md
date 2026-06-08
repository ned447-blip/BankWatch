# BankWatch

Daily, accuracy-first monitor for changes to **Australian bank credit-card
terms, rates, fees and product line-ups** — reading only from official bank
domains, and seeded from the Point Maxing card database.

It runs as a scheduled GitHub Action: it fetches each tracked page with a
real headless browser, extracts and hashes the meaningful content (HTML **and**
the linked Conditions-of-Use / Rates-&-Fees **PDFs**), diffs it against the
last committed snapshot, and writes a Markdown report — committing both the
snapshots and the report back to the repo so **every change is a readable git
diff**.

---

## What it detects

| Signal | How |
| --- | --- |
| 🔴 **Material change** | A tracked field (annual fee, purchase/cash-advance rate, interest-free days, bonus points, min spend) changed value, **or** a T&C PDF's content hash changed. |
| 🆕 **New product** | A new card link appeared on a bank's own listing page and persisted across `new_product_confirm_runs` runs. |
| 🗑️ **Withdrawn product** | A card disappeared from a listing. |
| 🟡 **Non-material change** | Page content hash moved but no tracked field did (likely copy/marketing). |
| ⚠️ **Unverified** | Page unreachable, blocked (bot challenge / 4xx-5xx), redirected off-domain, or its structure couldn't be parsed. **Never reported as "no change."** |
| 🔎 **Discovery candidate** | A newly-licensed ADI from the APRA register — surfaced for you to review, never auto-scraped. |

### The accuracy guarantee
Every check ends in exactly one of: **verified-no-change**, **change**, or
**unverified**. A broken selector or a Cloudflare block becomes a ⚠️ you must
review — it is *never* silently counted as "no change." If any check is
unverified, the report will not say "all clear", and the process exits
non-zero so CI flags it.

---

## How change detection avoids false positives

1. **Canonicalisation** (`bw/normalise.py`) strips scripts, styles, nav,
   header/footer, cookie/ad/promo blocks, comments and known-volatile tokens
   (session ids, nonces, dates), isolates the main content region, collapses
   whitespace and lowercases — so cosmetic/markup churn can't trigger a change.
2. **SHA-256** of that canonical text is the catch-all change signal.
3. **Structured extraction** (`bw/extract.py`) pulls the high-value fields with
   conservative text heuristics; a field is only reported as changed when a
   confident old **and** new value disagree.
4. **Two-run confirmation** gates new-product discovery.

---

## Two-tier discovery

- **Tier 1 — known issuers:** each issuer's listing page is diffed as a product
  *set*, so new/withdrawn cards are found **directly from the bank's own site.**
- **Tier 2 — new issuers:** the APRA register of Authorised Deposit-taking
  Institutions is snapshotted and diffed. A new ADI is a **candidate** for your
  review. Approve it by adding its official domain to `config/targets.yaml`;
  Tier 1 then monitors it. Discovery only ever surfaces *existence* — the bank
  is always the source of the actual details.

---

## Project layout

```
bankwatch/
  run.py                       orchestrator / entrypoint
  card_db_values.py            optional DB baseline for first-run cross-check
  config/targets.yaml          trusted allowlist + per-issuer targets
  bw/
    config.py    fetcher.py    normalise.py   pdfs.py
    extract.py   store.py      differ.py      discovery.py   reporter.py
  snapshots/                   committed JSON baselines (created on first run)
  reports/                     committed daily Markdown reports
  selftest.py                  offline logic check (no network)
  .github/workflows/bankwatch.yml
```

---

## Run it

### In CI (recommended)
Put this folder in its own GitHub repo, enable **Settings → Actions → General →
Workflow permissions → Read and write**, then **Actions → "BankWatch daily" →
Run workflow**. No secrets required.

### Locally
```bash
cd bankwatch
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

python run.py                 # full run (writes snapshots + reports/)
python run.py --issuer anz    # just one issuer
python run.py --no-pdfs       # skip PDFs (quick)
python run.py --dry-run       # diff + report, don't update baselines
python selftest.py            # offline: verifies hashing/diff/extract logic
```
First run captures **baselines** and reports "monitoring begins next run."
Real change detection starts from the second run.

---

## Adding a bank

1. Confirm it's a real, official domain you trust.
2. Add a block under `issuers:` in `config/targets.yaml` (name, domain,
   `listing`, and the product `pages`). Add the domain to `allowlist:`.
3. Done — the next run picks it up. (Per design, nothing off the allowlist is
   ever fetched.)

---

## Known assumptions & limits

- **Listing/index URLs** in `targets.yaml` are best-guess; if one is wrong it
  surfaces as ⚠️ Unverified (not a silent miss) — fix the URL and re-run.
- **Heuristic field extraction** is conservative by design. The hash layer
  still catches changes the heuristics miss; tune patterns in `bw/extract.py`
  per bank once you've seen a real fetch.
- **Bot mitigation** on the majors can still block headless Chromium; those
  land in ⚠️ Unverified for manual review rather than being fought.
- **One run/day** = one-day resolution; intra-day changes are coalesced.
- General information, **not financial advice.**
