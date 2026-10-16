# APAC SG&A Dashboard: AI-assisted variance commentary

A proof of concept for **AI-generated SG&A commentary**, built as the first
phase of a regional AI strategy in a corporate FP&A team. It is a
**3-layer interactive dashboard** designed to replace manual monthly
variance reporting. The aim: instead of eight separately drafted
functional commentaries each month, one self-serve view where a reader can
go from the regional headline down to the exact spreadsheet cell behind any
number.

> **Synthetic data; original built for a former employer.** This public
> version runs on a randomly generated dataset for a fictional company,
> "APAC Co." (markets: AU, SG, TW, TH, MY). It contains no real financials,
> names or internal systems. The code was rewritten from the original
> design to remove every employer-specific detail.

**Live demo:** open [`index.html`](index.html) in a browser. It is one
self-contained file with the synthetic data embedded, with no server and no
install.

---

## The three layers

| Layer | Question it answers | What you see |
|---|---|---|
| **Executive** | "Where are we vs plan, and which market is driving it?" | Actual vs Plan per market as budget meters, split Headcount / Non-headcount / Total, for MTD, YTD or the full-year forecast. |
| **Functional** | "Within this function, which cost lines moved?" | Every nature-of-cost line, sorted by size of variance, with diverging bars and grouped detail rows. |
| **Regional** | "Show me the ledger, and prove it." | The full main-line ledger, lines by markets, where every figure shows its source cell (e.g. `Operations!Q12`) on hover. |

A **commentary panel** sits beside every view: a headline, up to five
material variance bullets ("$57K U - Software & Cloud, driven by Taiwan"),
and a separate list of items that are **flagged, not explained**.

## How it works

```
monthly workbook (.xlsx)                     scripts/generate_synthetic_workbook.py
        |                                    creates the demo input
        v
sga/extract.py     read every cell with openpyxl -> SQLite, keeping
                   sheet + row provenance and Excel outline levels
        |          data checks -> validation_issues table
        v
sga/views.py       Executive / Functional / Regional read models
sga/commentary.py  deterministic selection + optional AI wording + guard
        |
        v
sga/export.py      one self-contained index.html (vanilla JS, no build step)
```

Design principle: **numbers are deterministic, AI supplies language only.**

- **Every figure is traceable.** Extraction stores the source sheet and row
  for each fact, so any number in the UI maps back to one workbook cell.
- **Data-quality checks are flagged, never silent.** The extractor detects a
  real class of spreadsheet bug, where an "FY vs Plan" cell is computed
  against the *prior* forecast with a flipped sign. It recomputes the cell
  as `Plan - Forecast` only when the stored value matches that exact
  pattern, and logs the cell reference. It also checks that the regional
  total reconciles to the sum of the markets. (The synthetic workbook plants
  two such errors so you can see them caught.)
- **Commentary rules are encoded as data** (`sga/rules.py`): per-function
  materiality thresholds, a five-bullet cap, combining Travel & Entertainment
  with its allocation line, aggregating all headcount lines into one figure
  (so no individual's pay can be inferred), and attributing each variance to
  its driving market. Lines with no confirmed driver (e.g. an "Unidentified
  adjustment") are flagged for follow-up, not narrated.
- **The AI step is optional and guarded.** `polish_with_claude()` sends only
  the already-computed bullets to Claude to improve the wording. A post-guard
  then rejects the reply if it contains any dollar figure the code did not
  compute, or if headcount commentary drifts into speculation (e.g. "timing
  of a hire"). On failure the deterministic draft is kept and the reason is
  reported.

## Tech

Python 3.9+ · openpyxl · SQLite · vanilla JavaScript/HTML/CSS (single-file
export, light and dark mode) · Anthropic Claude API (optional) · pytest

The original internal version was a FastAPI + React app with department-level
access control and an upload flow for each month's workbook. This public
version keeps the same pipeline and layers but exports a static file so it
can be viewed without a server.

## Run it

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1. regenerate the synthetic workbook (optional, one is committed)
python scripts/generate_synthetic_workbook.py

# 2. rebuild the dashboard
python -m sga.export data/synthetic/APAC_Co_SGA_2026-09_SYNTHETIC.xlsx
#    -> index.html

# 3. print one function's commentary as JSON
python -m sga.commentary data/synthetic/APAC_Co_SGA_2026-09_SYNTHETIC.xlsx OPS --period YTD

# 4. optional: let Claude polish the wording (needs ANTHROPIC_API_KEY)
python -m sga.commentary data/synthetic/APAC_Co_SGA_2026-09_SYNTHETIC.xlsx OPS --ai

# tests
pytest -q
```

## Repo layout

```
index.html                      the dashboard (generated, self-contained)
dashboard/template.html         dashboard source; export.py injects the data
sga/rules.py                    functions, markets, materiality and tone rules
sga/layout.py                   workbook column layout + sign-error correction
sga/extract.py                  workbook -> SQLite with provenance and checks
sga/views.py                    Executive / Functional / Regional read models
sga/commentary.py               deterministic draft, optional Claude polish, guard
sga/export.py                   builds index.html
scripts/generate_synthetic_workbook.py
data/synthetic/                 the generated demo workbook
tests/test_pipeline.py          16 tests covering checks, views and commentary rules
```
