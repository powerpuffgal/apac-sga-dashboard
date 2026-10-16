"""
Variance commentary: deterministic numbers, optional AI language.

Design rule: the numbers are never the model's job. `draft()` selects and
orders the material variances with plain code (materiality threshold,
line combining, headcount aggregation, "driven by <market>" attribution)
and produces a complete, usable commentary on its own.

`polish_with_claude()` is optional. It sends ONLY the already-computed
bullets to Claude to improve the wording, then a post-guard checks the
reply: every dollar figure in the prose must match a figure the code
computed, and payroll narration must not drift into speculative or
circular explanations. If the reply fails either check, the deterministic
draft is kept and the failure is reported, never shipped silently.
"""
from __future__ import annotations

import json
import os
import re

from . import rules
from .views import PERIODS


def fmt_k(amount: float) -> str:
    """$123K F / $1.2M U  (F = favorable, U = unfavorable)."""
    tag = "F" if rules.is_favorable(amount) else "U"
    a = abs(amount)
    s = f"${a / 1e6:.1f}M" if a >= 1e6 else f"${a / 1e3:.0f}K"
    return f"{s} {tag}"


def _line_items(conn, dept, period):
    """{item_label: {geo: delta}} after combining and aggregation rules."""
    _, _, d = PERIODS[period]
    rows = conn.execute(
        f"SELECT line, geo, {d} AS delta FROM facts WHERE department = ? AND "
        f"bucket != 'TOTAL'", (dept,)).fetchall()
    combine = {child: parent for parent, child in rules.COMBINE_LINES}
    items: dict = {}
    for r in rows:
        label = r["line"]
        if label in rules.HEADCOUNT_LINES:
            label = rules.HEADCOUNT_LABEL
        label = combine.get(label, label)
        by_geo = items.setdefault(label, {})
        by_geo[r["geo"]] = by_geo.get(r["geo"], 0) + (r["delta"] or 0)
    return items


def _driver(by_geo, sign):
    leaves = [(g, by_geo.get(g, 0)) for g in rules.GEO_LEAVES]
    same = [x for x in leaves if (x[1] > 0) == (sign > 0)]
    return max(same or leaves, key=lambda x: abs(x[1]))[0]


def draft(conn, dept, period="YTD"):
    cfg = rules.department_config(dept)
    _, _, d = PERIODS[period]
    head = conn.execute(
        f"SELECT {d} FROM facts WHERE department = ? AND geo = 'APAC_TOTAL' "
        f"AND line = ?", (dept, rules.ROLLUP_LABELS["total_costs"])).fetchone()[0]

    bullets, flags = [], []
    for label, by_geo in _line_items(conn, dept, period).items():
        amount = by_geo.get("APAC_TOTAL", 0)
        if label in rules.FLAG_ONLY_LINES:
            if abs(amount) >= 1:
                flags.append(f"{label}: {fmt_k(amount)} - driver not confirmed, "
                             f"flagged for follow-up rather than explained.")
            continue
        if abs(amount) < cfg["materiality"]:
            continue
        geo = _driver(by_geo, amount)
        bullets.append({
            "line": label, "amount": round(amount), "geo": geo,
            "text": f"{fmt_k(amount)} - {label}, driven by "
                    f"{rules.GEO_LABELS[geo]}",
        })
    # headline direction first, then largest first
    bullets.sort(key=lambda b: ((b["amount"] > 0) != (head > 0), -abs(b["amount"])))
    bullets = bullets[: rules.MAX_BULLETS]

    corrected = conn.execute(
        "SELECT geo, detail FROM validation_issues WHERE department = ? AND "
        "issue = 'sign_error_corrected'", (dept,)).fetchall()
    if period == "FY":
        for c in corrected:
            flags.append(f"Source cell {c['detail']} had a sign error in "
                         f"'FY Delta vs Plan'; recomputed as Plan - Forecast.")
    return {
        "department": cfg["label"], "period": period,
        "headline": f"{cfg['label']} {period} SG&A {fmt_k(head)} vs plan",
        "headline_amount": round(head),
        "bullets": bullets, "flags": flags,
    }


# ---- optional LLM polish + guards ---------------------------------------
_MONEY = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s?[KkMm]?")
_FORBIDDEN = [re.compile(p, re.I) for p in rules.PAYROLL_FORBIDDEN_PATTERNS]


def _norm(m: str) -> str:
    return m.replace(" ", "").replace(",", "").upper()


def guard(text: str, d: dict) -> list[str]:
    """Return a list of problems with model-written text (empty = OK)."""
    allowed = {_norm(fmt_k(b["amount"]).split()[0]) for b in d["bullets"]}
    allowed.add(_norm(fmt_k(d["headline_amount"]).split()[0]))
    problems = [f"figure not in computed set: {m}"
                for m in _MONEY.findall(text) if _norm(m) not in allowed]
    problems += [f"payroll narration rule: /{p.pattern}/"
                 for p in _FORBIDDEN if p.search(text)]
    return problems


SYSTEM = (
    "You edit monthly SG&A variance commentary for a finance leadership "
    "audience. You receive bullets whose figures were computed by code and "
    "are correct. Rewrite them as concise, plain-English bullets.\n"
    "Rules: use only the dollar figures given, formatted exactly as given; "
    "never compute, round differently or add figures. Keep the order. "
    "Headcount variances stop at 'driven by <market>' - do not speculate "
    "about hiring timing or restate the variance as its own cause. Never "
    "name individuals. Keep any flagged items as flags; do not invent a "
    "driver for them. Output plain text bullets only."
)


def polish_with_claude(d: dict, model: str | None = None) -> dict:
    """Optional. Needs `pip install anthropic` and an API key."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model or os.environ.get("SGA_MODEL", "claude-opus-5-5"),
        max_tokens=2000,
        thinking={"type": "adaptive"},
        output_config={"effort": "low"},
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(
            {k: d[k] for k in ("headline", "bullets", "flags")})}],
    )
    if response.stop_reason == "refusal":
        return {**d, "polished": None, "guard": ["model declined"]}
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    problems = guard(text, d)
    return {**d, "polished": None if problems else text, "guard": problems}


if __name__ == "__main__":
    import argparse
    import sys

    from . import extract

    ap = argparse.ArgumentParser(description="Print commentary for one department")
    ap.add_argument("workbook")
    ap.add_argument("department", choices=rules.DEPARTMENT_ORDER)
    ap.add_argument("--period", default="YTD", choices=list(PERIODS))
    ap.add_argument("--ai", action="store_true", help="polish wording with Claude")
    a = ap.parse_args()
    out = draft(extract.run(a.workbook), a.department, a.period)
    if a.ai:
        out = polish_with_claude(out)
    json.dump(out, sys.stdout, indent=2)
