# Nadlan Research System — Design Spec

**Date:** 2026-04-19  
**Status:** Approved  
**Scope:** Phase 1 — Claude as central engine

---

## Goal

A system that lets a user ask a free-form Hebrew question about a real estate area (e.g. "מה קורה בדיזנגוף? כדאי לקנות שם?") and receive:
1. An HTML report with real transaction data, price statistics, trends, and comparisons
2. A short verbal summary from Claude in the conversation

Target users: the developer runs it, clients receive the HTML report.

---

## Architecture

```
Free-form question (Hebrew)
        ↓
[Skill: nadlan-research]
Claude parses → settlement, streets, period, property type
        ↓
research.py  (orchestrator / entry point)
        ↓
nadlan_scraper.py  ←→  nadlan.gov.il API
(fetches real transactions via reCAPTCHA + JWT)
        ↓
analyze.py
(statistics: averages, medians, trends, comparisons)
        ↓
report.py
(generates Hebrew HTML report, opens in browser)
        ↓
HTML report + Claude verbal summary (3 key findings)
```

### Files

| File | Role |
|------|------|
| `nadlan_scraper.py` | **Existing.** Fetches transactions from nadlan.gov.il (Playwright + JWT auth) |
| `analyze.py` | **New.** Pure functions: takes raw deals list, returns statistics dict |
| `report.py` | **New.** Takes statistics dict, generates self-contained HTML file |
| `research.py` | **New.** CLI orchestrator: scrape → analyze → report → open browser |
| `skills/nadlan-research.md` | **New.** Skill file instructing Claude how to drive the system |

---

## Skill: nadlan-research

The skill instructs Claude to follow 4 steps when activated:

**Step 1 — Parse the question**
Extract from natural language:
- Settlement (יישוב) — default: ask user if ambiguous
- Streets — 1 specific street OR top 3–5 streets in area for comparison
- Period — default: last 2 years
- Property type — default: all types

If the question is ambiguous about location, Claude asks one clarifying question before proceeding.

**Step 2 — Fetch data**
Run `research.py --settlement X --street Y [--year Z]`.  
The script handles reCAPTCHA automatically via Playwright.

**Step 3 — Analyze**
`analyze.py` is called internally by `research.py`. Output is a JSON statistics file alongside the HTML.

**Step 4 — Report + Summary**
HTML report opens automatically. Claude reads the statistics JSON and writes a 3–4 sentence Hebrew summary in the conversation, answering the user's original question directly.

---

## analyze.py — Statistics

Input: list of deal dicts (from `nadlan_scraper.py` output)  
Output: structured dict with:

```python
{
  "meta": {
    "street": str, "settlement": str,
    "period_from": str, "period_to": str,
    "total_deals": int
  },
  "prices": {
    "mean": float, "median": float,
    "mean_per_sqm": float, "median_per_sqm": float,
    "by_rooms": {2: {...}, 3: {...}, 4: {...}},
    "by_floor_type": {"ground": {...}, "low": {...}, "high": {...}}
  },
  "trends": {
    "by_quarter": [{"label": "Q1 2025", "count": int, "mean_price": float}, ...],
    "direction": "rising" | "falling" | "stable",
    "volume_change_pct": float   # vs same period last year
  },
  "outliers": [deal, ...],       # >30% above or below mean
  "street_comparison": [         # populated when multiple streets fetched
    {"street": str, "mean_price": float, "mean_per_sqm": float, "count": int}
  ]
}
```

Floor classification: "קרקע" → ground, floors 1–3 → low, 4+ → high.  
Outlier threshold: ±30% from mean price per sqm.

---

## report.py — HTML Report

**Self-contained HTML** (no external dependencies — CSS inline, no JS libraries).  
**RTL Hebrew**, professional and clean — not decorative.

### Sections

1. **Header** — title, date generated, period covered
2. **Executive Summary** — 3–4 auto-generated Hebrew sentences from the statistics
3. **Price Data** — mean/median overall, table by room count (2/3/4+ rooms)
4. **Trends** — bar chart (CSS only) showing quarterly deal volume and average price
5. **Recent Transactions** — table: date | address | price | sqm | rooms | floor | type
6. **Outliers** — flagged deals significantly above/below average (if any)
7. **Street Comparison** — table comparing streets (populated for area-level queries)

**Filename:** `report_{street}_{YYYY-MM-DD}.html`  
**Opens automatically** in the default browser after generation.

---

## research.py — CLI Orchestrator

```
python3 research.py --settlement "תל אביב" --street "דיזנגוף" [--limit 200] [--year 2025]
```

Steps:
1. Call `nadlan_scraper.py` → save `deals_raw.json`
2. Call `analyze.py` → save `analysis.json`
3. Call `report.py` → save `report_*.html`
4. Open HTML in browser
5. Print brief stats summary to stdout

All output files saved to `./output/` directory.

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| reCAPTCHA token not obtained | Print instructions for manual token, exit with code 1 |
| Street not found in settlement | Warn, fall back to settlement-level search |
| Fewer than 5 deals found | Generate report with warning banner, skip trend charts |
| Settlement not found | Print available settlements, exit |

---

## Out of Scope (Phase 1)

- Scheduled/automated runs
- Multiple cities in one query
- Price prediction / ML
- User authentication or web interface
- PDF export
