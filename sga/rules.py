"""
Business rules for the SG&A commentary pipeline, encoded as data.

One source of truth shared by the extractor (which rollup row is each
department's headline), the commentary layer (materiality, ordering, tone
guards) and the dashboard (department list).

All departments, thresholds and labels here describe a fictional company,
"APAC Co.", used for the synthetic demo dataset.
"""

GEOS = ["APAC_TOTAL", "AU", "SG", "TW", "TH", "MY"]
GEO_LABELS = {
    "APAC_TOTAL": "APAC Total", "AU": "Australia", "SG": "Singapore",
    "TW": "Taiwan", "TH": "Thailand", "MY": "Malaysia",
}
GEO_LEAVES = ["AU", "SG", "TW", "TH", "MY"]

# sheet: workbook tab. materiality: smallest variance (USD) worth a bullet.
DEPARTMENTS = {
    "OPS":       {"label": "Operations",           "sheet": "Operations",   "materiality": 30_000},
    "TECH":      {"label": "Technology",           "sheet": "Technology",   "materiality": 40_000},
    "PRODUCT":   {"label": "Product & Marketing",  "sheet": "Product",      "materiality": 15_000},
    "FINANCE":   {"label": "Finance",              "sheet": "Finance",      "materiality": 12_000},
    "CARE":      {"label": "Customer Care",        "sheet": "Care",         "materiality": 25_000},
    "HR":        {"label": "Human Resources",      "sheet": "HR",           "materiality": 8_000},
    "LEGAL":     {"label": "Legal",                "sheet": "Legal",        "materiality": 7_000},
    "RISK":      {"label": "Risk & Compliance",    "sheet": "Risk",         "materiality": 6_000},
}
DEPARTMENT_ORDER = list(DEPARTMENTS)

ROLLUP_LABELS = {
    "total_hc": "Total HC Related",
    "total_non_hc": "Total Non-HC Related",
    "total_costs": "Total Costs",
}

# ---- commentary selection / tone rules ----------------------------------
MAX_BULLETS = 5
# Lines reported as one combined figure, never separately.
COMBINE_LINES = [("Travel & Entertainment", "Allocations - T&E")]
# Headcount lines are aggregated into one figure (never split salary vs
# contractors, so no individual's pay can be reverse-engineered).
HEADCOUNT_LINES = ["Salaries & Benefits", "Contract Labour",
                   "Recruiting & Training", "Allocations - Payroll"]
HEADCOUNT_LABEL = "Headcount costs"

# Payroll narration must stop at "driven by <GEO>". These phrasings were
# real failure modes (circular or speculative explanations) and are
# flagged by the post-guard if an LLM produces them.
PAYROLL_FORBIDDEN_PATTERNS = [
    r"forecast (is )?running (well )?above (the )?(aop|plan)",
    r"replacement hire",
    r"timing of (the |a )?hire",
]

# Lines that are flagged, never explained with an invented driver.
FLAG_ONLY_LINES = ["Unidentified adjustment"]


def is_favorable(delta: float) -> bool:
    """Sign convention: delta = Plan - Actual (or Plan - Forecast for FY).
    Positive = favorable (spend below plan)."""
    return delta is not None and delta > 0


def department_config(key: str) -> dict:
    if key not in DEPARTMENTS:
        raise KeyError(f"Unknown department: {key}")
    return DEPARTMENTS[key]
