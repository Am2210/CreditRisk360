"""Shared dashboard labels and approved segment dimensions."""

MODELS = {"logistic": "Logistic regression", "random_forest": "Random Forest", "xgboost": "XGBoost"}
SECTORS = {
    "11": "Agriculture and forestry", "21": "Mining, oil and gas", "22": "Utilities",
    "23": "Construction", "31-33": "Manufacturing", "42": "Wholesale trade",
    "44-45": "Retail trade", "48-49": "Transportation and warehousing", "51": "Information",
    "52": "Finance and insurance", "53": "Real estate and leasing", "54": "Professional services",
    "55": "Management of companies", "56": "Administrative and waste services",
    "61": "Educational services", "62": "Health care and social assistance",
    "71": "Arts, entertainment and recreation", "72": "Accommodation and food services",
    "81": "Other services", "92": "Public administration",
}
FILTER_FIELDS = {
    "industry": "Industry (NAICS sector)", "state": "Project state",
    "size": "Approved loan size", "vintage": "First-disbursement fiscal year",
    "term": "Reported loan term", "collateral": "Reported collateral",
}
DIMENSIONS = {**FILTER_FIELDS, "decile": "Risk decile", "portfolio": "Portfolio"}


def sector_label(code):
    return f"{code} · {SECTORS[code]}" if code in SECTORS else code
