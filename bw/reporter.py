"""Markdown daily report.

Sections, in priority order:
  🔴 Material changes        — a tracked rate/fee/bonus field changed, or a T&C PDF changed
  🆕 New products            — confirmed-new cards found on a bank's own listing
  🗑️ Withdrawn products      — cards that disappeared from a listing
  ⚠️ Unverified              — unreachable/blocked/off-domain/structure-missing — NEEDS A HUMAN
  🟡 Non-material changes    — page hash moved but no tracked field did
  🔎 Discovery candidates    — new ADIs to review (never auto-monitored)
  ✅ Verified, no change

If anything is Unverified, the report NEVER says "all clear".
"""
from __future__ import annotations

from datetime import datetime, timezone

from .differ import PageDiff, field_label


def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def build_report(*, date_str, page_diffs, baselines, unverified,
                 new_products, withdrawn_products, candidates, checked_total):
    material = [d for d in page_diffs if d.material]
    nonmaterial = [d for d in page_diffs if d.nonmaterial]
    clean = [d for d in page_diffs if not d.material and not d.nonmaterial and not d.is_baseline]

    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    L: list[str] = []
    L.append(f"# BankWatch — {date_str}")
    L.append("")
    L.append(f"_Run at {now} · {checked_total} targets checked · "
             f"{len(material)} material · {len(new_products)} new · "
             f"{len(unverified)} unverified_")
    L.append("")

    if unverified:
        L.append("> ⚠️ **This run has unverified checks — do not treat as “all clear”.** "
                 "See the Unverified section.")
        L.append("")

    # ── Material ──
    L.append(f"## 🔴 Material changes ({len(material)})")
    if not material:
        L.append("\n_None._\n")
    else:
        for d in material:
            L.append(f"\n### {d.issuer_key} · `{d.target_id}`")
            L.append(f"<{d.url}>")
            for fc in d.field_changes:
                L.append(f"- **{field_label(fc.name)}:** {_fmt(fc.old)} → **{_fmt(fc.new)}**")
                if fc.new_snippet:
                    L.append(f"  - context: “…{fc.new_snippet}…”")
            for p in d.pdf_changes:
                if p["kind"] == "changed":
                    L.append(f"- **T&C PDF changed:** [{p['label']}]({p['url']})")
            if d.db_mismatches:
                L.append("- ⚠️ _Extracted values differ from your card database (verify which is current):_")
                for fc in d.db_mismatches:
                    L.append(f"  - {field_label(fc.name)}: DB {_fmt(fc.old)} vs site {_fmt(fc.new)}")
        L.append("")

    # ── New / withdrawn ──
    L.append(f"## 🆕 New products ({len(new_products)})")
    if not new_products:
        L.append("\n_None._\n")
    else:
        for np in new_products:
            L.append(f"- **{np['issuer_key']}** — [{np['label']}]({np['url']}) "
                     f"_(confirmed across {np['seen_runs']} runs)_")
        L.append("")

    if withdrawn_products:
        L.append(f"## 🗑️ Withdrawn products ({len(withdrawn_products)})")
        for wp in withdrawn_products:
            L.append(f"- **{wp['issuer_key']}** — {wp['url']}")
        L.append("")

    # ── Unverified ──
    L.append(f"## ⚠️ Unverified — manual review needed ({len(unverified)})")
    if not unverified:
        L.append("\n_None._\n")
    else:
        for u in unverified:
            L.append(f"- **{u['issuer_key']}** · `{u['target_id']}` — {u['status']}: {u['note']}")
            L.append(f"  - {u['url']}")
        L.append("")

    # ── Non-material ──
    L.append(f"## 🟡 Non-material changes ({len(nonmaterial)})")
    if not nonmaterial:
        L.append("\n_None._\n")
    else:
        for d in nonmaterial:
            L.append(f"- **{d.issuer_key}** · `{d.target_id}` — page content changed, "
                     f"no tracked field moved. <{d.url}>")
        L.append("")

    # ── Discovery candidates ──
    L.append(f"## 🔎 Discovery — new ADIs to review ({len(candidates)})")
    if not candidates:
        L.append("\n_None._\n")
    else:
        L.append("\n_Newly-listed Australian deposit-taking institutions. "
                 "Review and, if they issue points cards, add their official domain to "
                 "`targets.yaml`. Not monitored until approved._\n")
        for c in candidates:
            L.append(f"- {c}")
        L.append("")

    # ── Baselines (first sight) ──
    if baselines:
        L.append(f"## 📸 Baselines captured ({len(baselines)})")
        L.append("\n_First snapshot taken — monitoring begins next run._\n")
        for b in baselines:
            L.append(f"- **{b.issuer_key}** · `{b.target_id}`")
        L.append("")

    # ── Clean ──
    L.append(f"## ✅ Verified, no change ({len(clean)})")
    if unverified:
        L.append(f"\n_{len(clean)} of {checked_total} targets verified unchanged. "
                 f"{len(unverified)} could not be verified (above)._\n")
    elif clean and not material and not nonmaterial and not new_products:
        L.append(f"\n**No changes detected across all {checked_total} targets (all verified).**\n")
    else:
        L.append(f"\n_{len(clean)} targets verified unchanged._\n")

    L.append("---")
    L.append("_BankWatch monitors official bank domains only. "
             "General information, not financial advice._")
    return "\n".join(L) + "\n"
