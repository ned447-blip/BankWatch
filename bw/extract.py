"""Heuristic structured-field extraction.

We can't rely on per-bank CSS selectors (they drift constantly and differ
across 10 issuers), so we extract the few high-value, change-prone fields
with text heuristics over the canonical page/PDF text. These are deliberately
CONSERVATIVE: a field we can't read with confidence is returned as None, and
the hash layer still catches the change. Every extracted value keeps the
surrounding snippet so the report can show context.

Fields: annual_fee, annual_fee_y1, purchase_rate, cash_advance_rate,
        interest_free_days, bonus_points, min_spend, min_spend_months.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Field:
    value: Optional[float]
    snippet: str = ""

    def to_json(self):
        return {"value": self.value, "snippet": self.snippet}


def _money(s: str) -> Optional[float]:
    s = s.replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _search(patterns: list[str], text: str) -> Field:
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            raw = m.group("v")
            val = _money(raw) if "$" in pat or "," in raw else _safe_float(raw)
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 40)
            return Field(val, _clean(text[start:end]))
    return Field(None, "")


def _safe_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_fields(text: str) -> dict:
    """Return {field_name: Field-as-dict} from canonical text."""
    fields: dict[str, Field] = {}

    fields["annual_fee"] = _search([
        r"annual fee[^$]{0,30}\$(?P<v>[\d,]+(?:\.\d{2})?)",
        r"\$(?P<v>[\d,]+)\s*(?:p\.?a\.?\s*)?annual fee",
        r"card fee[^$]{0,20}\$(?P<v>[\d,]+)",
    ], text)

    fields["annual_fee_y1"] = _search([
        r"(?:first year|year 1|1st year)[^$]{0,30}\$(?P<v>[\d,]+)",
        r"\$(?P<v>[\d,]+)[^.]{0,30}first year",
        r"reduced[^$]{0,20}\$(?P<v>[\d,]+)[^.]{0,20}first year",
    ], text)

    fields["purchase_rate"] = _search([
        r"purchase[s]?[^%]{0,40}?(?P<v>\d{1,2}\.\d{2})\s*%\s*p\.?a\.?",
        r"(?P<v>\d{1,2}\.\d{2})\s*%\s*p\.?a\.?[^%]{0,30}purchase",
    ], text)

    fields["cash_advance_rate"] = _search([
        r"cash advance[^%]{0,40}?(?P<v>\d{1,2}\.\d{2})\s*%\s*p\.?a\.?",
        r"(?P<v>\d{1,2}\.\d{2})\s*%\s*p\.?a\.?[^%]{0,30}cash advance",
    ], text)

    fields["interest_free_days"] = _search([
        r"up to\s*(?P<v>\d{2})\s*(?:interest[- ]free )?days",
        r"(?P<v>\d{2})\s*days interest[- ]free",
    ], text)

    fields["bonus_points"] = _search([
        r"(?P<v>[\d,]{4,})\s*(?:bonus\s*)?(?:qantas|velocity|reward|membership|altitude|amplify)?\s*(?:bonus\s*)?points",
        r"bonus[^.\d]{0,20}(?P<v>[\d,]{4,})\s*points",
    ], text)

    fields["min_spend"] = _search([
        r"spend\s*\$(?P<v>[\d,]+)[^.]{0,40}(?:first|within|in)\s*\d",
        r"\$(?P<v>[\d,]+)\s*(?:or more\s*)?(?:on eligible purchases|spend)[^.]{0,30}\d+\s*(?:days|months)",
    ], text)

    fields["min_spend_months"] = _search([
        r"(?:first|within|in)\s*(?P<v>\d{1,2})\s*months",
        r"(?P<v>\d{2,3})\s*days",   # captured as days; normalised below
    ], text)

    # Normalise "90 days" → 3 months when captured as days.
    msm = fields["min_spend_months"]
    if msm.value and msm.value >= 28 and "day" in msm.snippet.lower():
        msm.value = round(msm.value / 30.0)

    return {k: v.to_json() for k, v in fields.items()}


# Map CARD_DB field names → extracted field names, for first-run cross-check.
DB_FIELD_MAP = {
    "annualFee": "annual_fee",
    "annualFeeY1": "annual_fee_y1",
    "minSpend": "min_spend",
    "minSpendMonths": "min_spend_months",
}
