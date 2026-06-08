# Optional: card-database baseline values for the first-run cross-check.
#
# BankWatch compares the rates/fees it extracts from each live page against
# these known values on the FIRST run, so a mismatch (e.g. the site shows a
# fee your database doesn't) is surfaced immediately. Keys are target ids
# from config/targets.yaml; values use the card database's field names.
#
# This file is OPTIONAL — delete it and BankWatch still works (it just skips
# the cross-check). Populate/refresh it from your Point Maxing data.js.

DB_VALUES = {
    "amex-qantas-ultimate":      {"annualFee": 450,  "minSpend": 5000,  "minSpendMonths": 3},
    "amex-explorer":             {"annualFee": 395,  "minSpend": 4000,  "minSpendMonths": 3},
    "amex-platinum":             {"annualFee": 1450, "minSpend": 5000,  "minSpendMonths": 3},
    "wbc-altitude-rewards-black":{"annualFee": 295,  "annualFeeY1": 200, "minSpend": 12000, "minSpendMonths": 12},
    "anz-rewards-black":         {"annualFee": 375,  "minSpend": 5000,  "minSpendMonths": 3},
    "anz-ff-black":              {"annualFee": 425,  "minSpend": 5000,  "minSpendMonths": 3},
    "nab-rewards-signature":     {"annualFee": 420,  "minSpend": 5000,  "minSpendMonths": 3},
    "cba-ultimate":              {"annualFee": 420,  "minSpend": 9000,  "minSpendMonths": 3},
    "cba-smart":                 {"annualFee": 228,  "minSpend": 4500,  "minSpendMonths": 3},
    "qm-platinum":               {"annualFee": 399,  "annualFeeY1": 349, "minSpend": 5000, "minSpendMonths": 3},
    "qm-titanium":               {"annualFee": 1200, "minSpend": 5000,  "minSpendMonths": 3},
    "hsbc-platinum-qantas":      {"annualFee": 399,  "annualFeeY1": 0},
    "myc-prestige":              {"annualFee": 700,  "minSpend": 10000, "minSpendMonths": 3},
}
