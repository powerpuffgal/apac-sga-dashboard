#!/usr/bin/env python3
"""
Export a single-file, self-serve HTML dashboard (no server, no login).

All views for every department x period are precomputed into one JSON
payload and embedded in dashboard/template.html, so the result can be
opened from disk or hosted on GitHub Pages.

Usage: python -m sga.export data/synthetic/<workbook>.xlsx [out.html]
(default output: index.html at the repo root)
"""
from __future__ import annotations

import json
import os
import sys

from . import commentary, extract, rules, views

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
TEMPLATE = os.path.join(ROOT, "dashboard", "template.html")


def build_payload(conn):
    meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    depts = ["ALL"] + rules.DEPARTMENT_ORDER
    data = {}
    for dept in depts:
        data[dept] = {}
        for period in views.PERIODS:
            entry = {
                "executive": views.executive(conn, dept, period),
                "functional": views.functional(conn, dept, period),
            }
            if dept != "ALL":
                entry["regional"] = views.regional(conn, dept, period)
                entry["commentary"] = commentary.draft(conn, dept, period)
            data[dept][period] = entry
    return {
        "meta": meta,
        "departments": [{"key": "ALL", "label": "All functions"}] +
                       [{"key": k, "label": rules.DEPARTMENTS[k]["label"]}
                        for k in rules.DEPARTMENT_ORDER],
        "geos": rules.GEOS, "geoLabels": rules.GEO_LABELS,
        "issues": views.validation_issues(conn),
        "data": data,
    }


def export(workbook, out_path):
    payload = build_payload(extract.run(workbook))
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("/*__DATA__*/null", blob)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


if __name__ == "__main__":
    wb = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT,
                                                             "index.html")
    print("wrote", export(wb, out))
