import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from sga import commentary, extract, layout, rules, views  # noqa: E402
import generate_synthetic_workbook as gen  # noqa: E402


@pytest.fixture(scope="session")
def conn(tmp_path_factory):
    path = tmp_path_factory.mktemp("wb") / "synthetic.xlsx"
    gen.build(str(path), month=9, seed=42)
    return extract.run(str(path))


# ---- layout / sign-error rule --------------------------------------------
def test_sign_error_known_pattern_is_corrected():
    # plan 100, forecast 120, prior 110: correct delta = -20;
    # buggy cell stored forecast - prior = +10
    assert layout.correct_fy_sign_error(100, 120, 110, 10) == (-20, True)


def test_correct_value_is_left_alone():
    assert layout.correct_fy_sign_error(100, 120, 110, -20) == (-20, False)


def test_unknown_mismatch_is_not_silently_rewritten():
    assert layout.correct_fy_sign_error(100, 120, 110, 999) == (999, False)


def test_cell_ref():
    assert layout.cell_ref(8, "APAC_TOTAL", "mtd_actual") == "E8"
    assert layout.cell_ref(8, "AU", "mtd_actual") == "Q8"


# ---- extraction -----------------------------------------------------------
def test_every_department_extracted(conn):
    got = {r[0] for r in conn.execute("SELECT DISTINCT department FROM facts")}
    assert got == set(rules.DEPARTMENT_ORDER)


def test_planted_sign_errors_are_caught_and_flagged(conn):
    issues = [i for i in views.validation_issues(conn)
              if i["issue"] == "sign_error_corrected"]
    assert {(i["department"], i["geo"]) for i in issues} == {("HR", "AU"),
                                                            ("LEGAL", "TW")}


def test_totals_reconcile_to_markets(conn):
    assert not [i for i in views.validation_issues(conn)
                if i["issue"] == "total_ne_sum_of_markets"]


def test_outline_level_marks_detail_rows(conn):
    lvl = conn.execute("SELECT DISTINCT outline_level FROM facts WHERE "
                       "line = 'Allocations - Payroll'").fetchone()[0]
    assert lvl == 1


# ---- views ----------------------------------------------------------------
def test_all_functions_equals_sum_of_departments(conn):
    total = views.executive(conn, "ALL", "YTD")["TOTAL"][0]
    parts = sum(views.executive(conn, d, "YTD")["TOTAL"][0]["actual"]
                for d in rules.DEPARTMENT_ORDER)
    assert total["geo"] == "APAC_TOTAL"
    assert abs(total["actual"] - parts) < 1


def test_regional_shows_main_lines_only(conn):
    lines = [r["line"] for r in views.regional(conn, "OPS", "YTD")]
    assert "Allocations - Payroll" not in lines
    assert "Total Costs" in lines


def test_provenance_points_at_a_cell(conn):
    row = views.regional(conn, "OPS", "YTD")[0]
    assert row["cells"]["AU"]["source"].startswith("Operations!")


# ---- commentary -----------------------------------------------------------
def test_draft_respects_materiality_and_cap(conn):
    for dept in rules.DEPARTMENT_ORDER:
        d = commentary.draft(conn, dept, "YTD")
        m = rules.DEPARTMENTS[dept]["materiality"]
        assert len(d["bullets"]) <= rules.MAX_BULLETS
        assert all(abs(b["amount"]) >= m for b in d["bullets"])


def test_headcount_aggregated_and_te_combined(conn):
    for dept in rules.DEPARTMENT_ORDER:
        for b in commentary.draft(conn, dept, "YTD")["bullets"]:
            assert b["line"] not in rules.HEADCOUNT_LINES
            assert b["line"] != "Allocations - T&E"


def test_unidentified_line_is_flagged_not_explained(conn):
    d = commentary.draft(conn, "OPS", "YTD")
    assert any("Unidentified adjustment" in f for f in d["flags"])
    assert all(b["line"] != "Unidentified adjustment" for b in d["bullets"])


def test_guard_rejects_invented_figures(conn):
    d = commentary.draft(conn, "TECH", "YTD")
    ok = " ".join(b["text"] for b in d["bullets"])
    assert commentary.guard(ok, d) == []
    assert commentary.guard("Spend was $987K F due to cloud.", d)


def test_guard_rejects_payroll_speculation(conn):
    d = commentary.draft(conn, "HR", "YTD")
    assert commentary.guard("Driven by the timing of a hire in AU.", d)
