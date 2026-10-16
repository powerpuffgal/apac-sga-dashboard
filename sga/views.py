"""
Read model behind the three dashboard layers.

  executive(...)   one glance: Actual vs Plan per market, split
                   Headcount / Non-headcount / Total
  functional(...)  nature-of-cost detail for one department, sorted by
                   size of variance
  regional(...)    the full auditable ledger, main lines x markets,
                   every figure carrying its source cell

Every figure returned carries `source` (sheet!cell) so the UI can show
where it came from. Department "ALL" sums across departments.
"""
from __future__ import annotations

from . import layout, rules

PERIODS = {
    # period: (actual-ish field, plan field, delta field)
    "MTD": ("mtd_actual", "mtd_plan", "mtd_delta"),
    "YTD": ("ytd_actual", "ytd_plan", "ytd_delta"),
    "FY": ("fy_forecast", "fy_plan", "fy_delta"),
}
BUCKET_ROWS = {
    "HC": rules.ROLLUP_LABELS["total_hc"],
    "NONHC": rules.ROLLUP_LABELS["total_non_hc"],
    "TOTAL": rules.ROLLUP_LABELS["total_costs"],
}


def _dept_filter(dept):
    if dept == "ALL":
        return "", ()
    rules.department_config(dept)
    return " AND department = ?", (dept,)


def _src(row, geo, field):
    return f"{row['source_sheet']}!{layout.cell_ref(row['source_row'], geo, field)}"


def executive(conn, dept, period):
    a, p, d = PERIODS[period]
    where, args = _dept_filter(dept)
    out = {}
    for bucket, label in BUCKET_ROWS.items():
        rows = conn.execute(
            f"SELECT * FROM facts WHERE line = ?{where}", (label, *args)).fetchall()
        per_geo = {}
        for r in rows:
            g = per_geo.setdefault(r["geo"], {"actual": 0, "plan": 0, "delta": 0,
                                              "source": [], "corrected": False})
            g["actual"] += r[a] or 0
            g["plan"] += r[p] or 0
            g["delta"] += r[d] or 0
            g["source"].append(_src(r, r["geo"], a))
            g["corrected"] |= bool(r["sign_error_corrected"]) and period == "FY"
        out[bucket] = [{"geo": geo, **per_geo[geo]} for geo in rules.GEOS
                       if geo in per_geo]
    return out


def functional(conn, dept, period, geo="APAC_TOTAL"):
    a, p, d = PERIODS[period]
    where, args = _dept_filter(dept)
    rows = conn.execute(
        f"SELECT line, bucket, outline_level, SUM({a}) a, SUM({p}) p, SUM({d}) d,"
        f" MAX(sign_error_corrected) c, MIN(source_sheet) s, MIN(source_row) r "
        f"FROM facts WHERE geo = ? AND bucket != 'TOTAL'{where} "
        f"GROUP BY line, bucket, outline_level", (geo, *args)).fetchall()
    lines = [{
        "line": r["line"], "bucket": r["bucket"], "detail": r["outline_level"] > 0,
        "actual": r["a"], "plan": r["p"], "delta": r["d"],
        "favorable": rules.is_favorable(r["d"]),
        "corrected": bool(r["c"]) and period == "FY",
        "source": (f"{r['s']}!{layout.cell_ref(r['r'], geo, a)}"
                   if dept != "ALL" else "sum of department tabs"),
    } for r in rows]
    lines.sort(key=lambda x: -abs(x["delta"] or 0))
    return lines


def regional(conn, dept, period):
    """Main lines only (outline level 0), in sheet order, markets as columns."""
    if dept == "ALL":
        raise ValueError("regional ledger is per department")
    a, p, d = PERIODS[period]
    rows = conn.execute(
        "SELECT * FROM facts WHERE department = ? AND outline_level = 0 "
        "ORDER BY source_row", (dept,)).fetchall()
    ledger = {}
    for r in rows:
        entry = ledger.setdefault(r["line"], {"line": r["line"],
                                              "bucket": r["bucket"], "cells": {}})
        entry["cells"][r["geo"]] = {
            "actual": r[a], "plan": r[p], "delta": r[d],
            "corrected": bool(r["sign_error_corrected"]) and period == "FY",
            "source": _src(r, r["geo"], a),
        }
    return list(ledger.values())


def validation_issues(conn):
    return [dict(r) for r in conn.execute(
        "SELECT department, geo, issue, detail FROM validation_issues")]
