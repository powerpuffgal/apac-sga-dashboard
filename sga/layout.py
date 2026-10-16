"""
Column layout of the monthly SG&A workbook, plus the one data-quality rule
the pipeline applies to raw cells (the FY sign-error correction).

Each department tab has one block of 12 columns per GEO, starting at
column E. Within a block (0-based offsets):

  0 MTD Actual     4 YTD Actual     8 FY Prior Forecast
  1 MTD Plan       5 YTD Plan       9 FY Forecast
  2 MTD Delta      6 YTD Delta     10 FY Plan
  3 (spacer)       7 (spacer)      11 FY Delta vs Plan

Column B = line code, C = account, D = line label. Data starts at row 8.
Sign convention: Delta = Plan - Actual (Plan - Forecast for FY);
positive = favorable.
"""
from __future__ import annotations

from dataclasses import dataclass

from openpyxl.utils import get_column_letter

from . import rules

BLOCK_WIDTH = 12
FIRST_BLOCK_COL = 5
DATA_START_ROW = 8
COL_CODE, COL_ACCOUNT, COL_LABEL = 2, 3, 4

FIELD_OFFSETS = {
    "mtd_actual": 0, "mtd_plan": 1, "mtd_delta": 2,
    "ytd_actual": 4, "ytd_plan": 5, "ytd_delta": 6,
    "fy_prior_forecast": 8, "fy_forecast": 9, "fy_plan": 10,
    "fy_delta": 11,
}
FIELDS = list(FIELD_OFFSETS)


def block_start(geo: str) -> int:
    return FIRST_BLOCK_COL + rules.GEOS.index(geo) * BLOCK_WIDTH


def cell_ref(row: int, geo: str, field: str) -> str:
    """Excel reference for provenance, e.g. 'Q14'."""
    return f"{get_column_letter(block_start(geo) + FIELD_OFFSETS[field])}{row}"


def last_col() -> int:
    return FIRST_BLOCK_COL + len(rules.GEOS) * BLOCK_WIDTH - 1


@dataclass
class GeoFigures:
    geo: str
    values: dict
    sign_error_corrected: bool = False


def correct_fy_sign_error(fy_plan, fy_forecast, fy_prior, stored, eps=0.01):
    """
    Known source-file bug: some 'FY Delta vs Plan' cells were computed
    against the PRIOR forecast with a flipped sign, i.e. the stored value is
    -(Prior - Forecast) instead of (Plan - Forecast).

    Returns (value, was_corrected). Only the exact known pattern is
    corrected; any other mismatch is left as-is for the caller to flag, so
    nothing is ever silently rewritten.
    """
    if fy_plan is None or fy_forecast is None:
        return stored, False
    expected = fy_plan - fy_forecast
    if stored is None:
        return expected, False
    if abs(stored - expected) <= eps:
        return stored, False
    if fy_prior is not None and abs(stored - (fy_forecast - fy_prior)) <= eps:
        return expected, True
    return stored, False


def read_row(row_values: tuple, correct=True) -> list[GeoFigures]:
    out = []
    for geo in rules.GEOS:
        start = block_start(geo)
        vals = {}
        for f, off in FIELD_OFFSETS.items():
            idx = start + off - 1
            vals[f] = row_values[idx] if idx < len(row_values) else None
        fixed = False
        if correct:
            vals["fy_delta"], fixed = correct_fy_sign_error(
                vals["fy_plan"], vals["fy_forecast"],
                vals["fy_prior_forecast"], vals["fy_delta"])
        out.append(GeoFigures(geo, vals, fixed))
    return out
