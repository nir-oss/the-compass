# Nadlan Research System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a system where Claude receives a free-form Hebrew question about a real estate area, fetches real transactions from nadlan.gov.il, computes statistics, and produces a Hebrew HTML report.

**Architecture:** `research.py` is the CLI entry point that orchestrates `nadlan_scraper.py` → `analyze.py` → `report.py`. A Claude skill (`skills/nadlan-research.md`) instructs Claude how to parse natural-language questions and drive the pipeline.

**Tech Stack:** Python 3.9, Playwright (already installed), PyJWT (already installed), requests (already installed). No new external dependencies.

---

## File Map

| File | Status | Responsibility |
|------|--------|----------------|
| `nadlan_scraper.py` | Existing — no changes | Fetches transactions from nadlan.gov.il |
| `analyze.py` | Create | Pure functions: deals list → statistics dict |
| `report.py` | Create | Statistics dict → self-contained Hebrew HTML file |
| `research.py` | Create | CLI orchestrator: scrape → analyze → report → open |
| `skills/nadlan-research.md` | Create | Claude skill: parse question → drive pipeline |
| `tests/test_analyze.py` | Create | Unit tests for analyze.py |
| `tests/test_report.py` | Create | Smoke test for report.py |
| `output/` | Auto-created at runtime | Generated HTML and JSON files |

---

## Task 1: Test fixtures + analyze.py skeleton

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/fixtures.py`
- Create: `analyze.py`
- Create: `tests/test_analyze.py`

- [ ] **Step 1: Create tests directory and fixtures**

```bash
mkdir -p tests
touch tests/__init__.py
```

Create `tests/fixtures.py`:

```python
# Realistic deal objects matching the actual nadlan.gov.il API response shape.
SAMPLE_DEALS = [
    {"address": "דיזנגוף 78",  "dealDate": "2026-02-01", "dealAmount": 4675000, "priceSM": 63176, "roomNum": 3.0, "floor": "חמישית",  "assetArea": 74.0,  "yearBuilt": 1930, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 203", "dealDate": "2026-01-03", "dealAmount": 4794000, "priceSM": 103509,"roomNum": 3.0, "floor": "קרקע",    "assetArea": 46.32, "yearBuilt": 1960, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 230", "dealDate": "2025-12-28", "dealAmount": 4620000, "priceSM": 70000, "roomNum": 3.0, "floor": "חמישית",  "assetArea": 66.0,  "yearBuilt": 1955, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 154", "dealDate": "2025-12-21", "dealAmount": 3220000, "priceSM": 44513, "roomNum": 3.0, "floor": "שלישית", "assetArea": 72.33, "yearBuilt": 1940, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 137", "dealDate": "2025-12-10", "dealAmount": 3800000, "priceSM": 66667, "roomNum": 2.0, "floor": "חמישית",  "assetArea": 57.0,  "yearBuilt": 1935, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 50",  "dealDate": "2025-12-09", "dealAmount": 5500000, "priceSM": 59140, "roomNum": 4.0, "floor": "עשרים",   "assetArea": 93.0,  "yearBuilt": 1930, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 203", "dealDate": "2025-12-02", "dealAmount": 12000000,"priceSM": 95238, "roomNum": 4.0, "floor": "שניה",    "assetArea": 126.0, "yearBuilt": 1960, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 126", "dealDate": "2025-11-20", "dealAmount": 4300000, "priceSM": 75439, "roomNum": 2.5, "floor": "חמישית",  "assetArea": 57.0,  "yearBuilt": 1945, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 136", "dealDate": "2025-11-18", "dealAmount": 3290000, "priceSM": 55201, "roomNum": 3.0, "floor": "שניה",    "assetArea": 59.6,  "yearBuilt": 1952, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
    {"address": "דיזנגוף 249", "dealDate": "2025-11-02", "dealAmount": 10700000,"priceSM": 62941, "roomNum": 5.0, "floor": "שביעית",  "assetArea": 170.0, "yearBuilt": 1965, "dealNature": "דירת גג",         "neighborhoodName": "הצפון הישן"},
    # Deal with no priceSM — should be handled gracefully
    {"address": "דיזנגוף 70",  "dealDate": "2025-11-30", "dealAmount": 593000,  "priceSM": None,  "roomNum": None,"floor": "מרתף",   "assetArea": 55.74, "yearBuilt": 1930, "dealNature": "מחסנים",          "neighborhoodName": "הצפון הישן"},
    # Deal with no dealAmount — should be excluded from stats
    {"address": "דיזנגוף 1",   "dealDate": "2025-10-01", "dealAmount": None,    "priceSM": None,  "roomNum": 2.0, "floor": "ראשונה", "assetArea": 60.0,  "yearBuilt": 1935, "dealNature": "דירה בבית קומות", "neighborhoodName": "הצפון הישן"},
]
```

- [ ] **Step 2: Create analyze.py skeleton**

Create `analyze.py`:

```python
"""
analyze.py — Pure statistics functions for nadlan deal data.
Input:  list of deal dicts (from nadlan_scraper.py / deals_raw.json)
Output: nested dict with prices, trends, outliers, recent
"""

import statistics
import re
from collections import defaultdict
from datetime import datetime

# Hebrew ordinal floor names → integer floor number
_FLOOR_MAP = {
    "מרתף": -1, "קרקע": 0,
    "ראשונה": 1, "שניה": 2, "שלישית": 3, "רביעית": 4,
    "חמישית": 5, "שישית": 6, "שביעית": 7, "שמינית": 8,
    "תשיעית": 9, "עשירית": 10, "אחת עשרה": 11, "שתים עשרה": 12,
}


def _floor_to_int(floor_str):
    """Convert a Hebrew (or numeric) floor string to int. Returns None if unknown."""
    if not floor_str:
        return None
    s = str(floor_str).strip()
    if s in _FLOOR_MAP:
        return _FLOOR_MAP[s]
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


def _floor_type(floor_str):
    """Classify floor as 'ground', 'low' (1-3), or 'high' (4+). Returns None if unknown."""
    n = _floor_to_int(floor_str)
    if n is None:
        return None
    if n <= 0:
        return "ground"
    if n <= 3:
        return "low"
    return "high"


def _room_key(room_num):
    """Return bucketed room key: '2', '3', '4+'. Returns None if unknown."""
    if room_num is None:
        return None
    n = int(room_num)
    return "4+" if n >= 4 else str(n)


def _stats(amounts, sqm_list=None):
    """Return mean/median/min/max dict. Handles empty lists."""
    if not amounts:
        return {"count": 0}
    result = {
        "count": len(amounts),
        "mean":   round(statistics.mean(amounts)),
        "median": round(statistics.median(amounts)),
        "min":    min(amounts),
        "max":    max(amounts),
    }
    valid_sqm = [x for x in (sqm_list or []) if x]
    if valid_sqm:
        result["mean_per_sqm"]   = round(statistics.mean(valid_sqm))
        result["median_per_sqm"] = round(statistics.median(valid_sqm))
    return result


def compute_prices(deals):
    """Compute overall, by-rooms, and by-floor-type price statistics."""
    pass  # implemented in Task 2


def compute_trends(deals):
    """Compute quarterly deal volume and price trend direction."""
    pass  # implemented in Task 2


def find_outliers(deals, threshold=0.3):
    """Return deals whose priceSM deviates ≥ threshold from the mean."""
    pass  # implemented in Task 2


def analyze(deals, street=None, settlement=None):
    """
    Main entry point.

    Args:
        deals: list of deal dicts from nadlan_scraper
        street: street name string (optional, for metadata)
        settlement: settlement name string (optional, for metadata)

    Returns:
        dict with keys: meta, prices, trends, outliers, recent
    """
    pass  # implemented in Task 2
```

- [ ] **Step 3: Write failing tests for _floor_to_int and _floor_type**

Create `tests/test_analyze.py`:

```python
import pytest
from analyze import _floor_to_int, _floor_type, _room_key, _stats
from tests.fixtures import SAMPLE_DEALS


class TestFloorParsing:
    def test_hebrew_ordinal(self):
        assert _floor_to_int("חמישית") == 5

    def test_ground_floor(self):
        assert _floor_to_int("קרקע") == 0

    def test_basement(self):
        assert _floor_to_int("מרתף") == -1

    def test_numeric_in_string(self):
        assert _floor_to_int("קומה 7") == 7

    def test_large_number(self):
        assert _floor_to_int("עשרים ושמונה") is None  # not in map, no digit → None

    def test_none_input(self):
        assert _floor_to_int(None) is None

    def test_floor_type_ground(self):
        assert _floor_type("קרקע") == "ground"

    def test_floor_type_basement_is_ground(self):
        assert _floor_type("מרתף") == "ground"

    def test_floor_type_low(self):
        assert _floor_type("שלישית") == "low"

    def test_floor_type_high(self):
        assert _floor_type("חמישית") == "high"

    def test_floor_type_unknown(self):
        assert _floor_type(None) is None


class TestRoomKey:
    def test_two_rooms(self):
        assert _room_key(2.0) == "2"

    def test_three_rooms(self):
        assert _room_key(3.0) == "3"

    def test_four_plus(self):
        assert _room_key(4.0) == "4+"

    def test_five_rooms_is_four_plus(self):
        assert _room_key(5.0) == "4+"

    def test_none(self):
        assert _room_key(None) is None


class TestStats:
    def test_empty(self):
        assert _stats([]) == {"count": 0}

    def test_single_value(self):
        r = _stats([1000000])
        assert r["count"] == 1
        assert r["mean"] == 1000000
        assert r["median"] == 1000000

    def test_mean_median(self):
        r = _stats([1000000, 2000000, 3000000])
        assert r["mean"] == 2000000
        assert r["median"] == 2000000

    def test_with_sqm(self):
        r = _stats([1000000], [10000])
        assert r["mean_per_sqm"] == 10000

    def test_sqm_none_values_ignored(self):
        r = _stats([1000000, 2000000], [None, 10000])
        assert r["mean_per_sqm"] == 10000
```

- [ ] **Step 4: Run tests to confirm they pass (helpers are already implemented)**

```bash
cd "/Users/nirabas/Library/CloudStorage/Dropbox/2026/ClAUDE CODE/מאגר עסקאות שבוצעו"
python3 -m pytest tests/test_analyze.py::TestFloorParsing tests/test_analyze.py::TestRoomKey tests/test_analyze.py::TestStats -v
```

Expected: all 17 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd "/Users/nirabas/Library/CloudStorage/Dropbox/2026/ClAUDE CODE/מאגר עסקאות שבוצעו"
git add tests/ analyze.py
git commit -m "feat: add test fixtures and analyze.py skeleton with helpers"
```

---

## Task 2: Implement analyze.py functions

**Files:**
- Modify: `analyze.py` (implement the 4 `pass` bodies)
- Modify: `tests/test_analyze.py` (add tests for compute_prices, compute_trends, find_outliers, analyze)

- [ ] **Step 1: Write failing tests for compute_prices**

Add to `tests/test_analyze.py`:

```python
from analyze import compute_prices, compute_trends, find_outliers, analyze


class TestComputePrices:
    def test_overall_count(self):
        # SAMPLE_DEALS has 1 deal with no dealAmount → should be excluded
        result = compute_prices(SAMPLE_DEALS)
        assert result["overall"]["count"] == 10  # 11 with amount, but 1 has None

    def test_overall_mean_positive(self):
        result = compute_prices(SAMPLE_DEALS)
        assert result["overall"]["mean"] > 0

    def test_by_rooms_keys(self):
        result = compute_prices(SAMPLE_DEALS)
        assert "2" in result["by_rooms"] or "3" in result["by_rooms"]

    def test_by_floor_ground_exists(self):
        result = compute_prices(SAMPLE_DEALS)
        # מרתף and קרקע both map to ground
        assert "ground" in result["by_floor_type"]

    def test_no_sqm_deals_excluded_from_sqm_stats(self):
        # דיזנגוף 70 has priceSM=None — should not break mean_per_sqm
        result = compute_prices(SAMPLE_DEALS)
        assert "mean_per_sqm" in result["overall"]


class TestComputeTrends:
    def test_by_quarter_not_empty(self):
        result = compute_trends(SAMPLE_DEALS)
        assert len(result["by_quarter"]) > 0

    def test_direction_is_valid(self):
        result = compute_trends(SAMPLE_DEALS)
        assert result["direction"] in ("rising", "falling", "stable")

    def test_quarter_has_required_keys(self):
        result = compute_trends(SAMPLE_DEALS)
        q = result["by_quarter"][0]
        assert "label" in q and "count" in q and "mean_price" in q

    def test_deals_with_no_date_are_skipped(self):
        deals = [{"dealDate": None, "dealAmount": 1000000}]
        result = compute_trends(deals)
        assert result["by_quarter"] == []


class TestFindOutliers:
    def test_returns_list(self):
        result = find_outliers(SAMPLE_DEALS)
        assert isinstance(result, list)

    def test_outliers_have_direction(self):
        result = find_outliers(SAMPLE_DEALS)
        for o in result:
            assert o["_outlier_direction"] in ("high", "low")
            assert "_outlier_pct" in o

    def test_no_priceSM_deals_excluded(self):
        deals = [{"dealAmount": 1000000, "priceSM": None}]
        result = find_outliers(deals)
        assert result == []

    def test_high_threshold_returns_fewer(self):
        r_low  = find_outliers(SAMPLE_DEALS, threshold=0.1)
        r_high = find_outliers(SAMPLE_DEALS, threshold=0.9)
        assert len(r_low) >= len(r_high)


class TestAnalyze:
    def test_returns_all_keys(self):
        result = analyze(SAMPLE_DEALS, street="דיזנגוף", settlement="תל אביב")
        assert all(k in result for k in ("meta", "prices", "trends", "outliers", "recent"))

    def test_meta_values(self):
        result = analyze(SAMPLE_DEALS, street="דיזנגוף", settlement="תל אביב")
        assert result["meta"]["street"] == "דיזנגוף"
        assert result["meta"]["settlement"] == "תל אביב"
        assert result["meta"]["total_deals"] > 0

    def test_recent_at_most_20(self):
        result = analyze(SAMPLE_DEALS)
        assert len(result["recent"]) <= 20

    def test_recent_sorted_newest_first(self):
        result = analyze(SAMPLE_DEALS)
        dates = [d["dealDate"] for d in result["recent"] if d.get("dealDate")]
        assert dates == sorted(dates, reverse=True)

    def test_empty_deals(self):
        result = analyze([])
        assert result["meta"]["total_deals"] == 0
        assert result["prices"]["overall"]["count"] == 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python3 -m pytest tests/test_analyze.py -v -x 2>&1 | head -30
```

Expected: FAIL at `TestComputePrices` — `compute_prices` returns `None`.

- [ ] **Step 3: Implement compute_prices in analyze.py**

Replace the `compute_prices` function body:

```python
def compute_prices(deals):
    """Compute overall, by-rooms, and by-floor-type price statistics."""
    valid = [d for d in deals if d.get("dealAmount")]

    amounts = [d["dealAmount"] for d in valid]
    sqm     = [d.get("priceSM") for d in valid]

    by_rooms     = defaultdict(list)
    by_rooms_sqm = defaultdict(list)
    by_floor     = defaultdict(list)
    by_floor_sqm = defaultdict(list)

    for d in valid:
        key = _room_key(d.get("roomNum"))
        if key:
            by_rooms[key].append(d["dealAmount"])
            if d.get("priceSM"):
                by_rooms_sqm[key].append(d["priceSM"])

        ft = _floor_type(d.get("floor"))
        if ft:
            by_floor[ft].append(d["dealAmount"])
            if d.get("priceSM"):
                by_floor_sqm[ft].append(d["priceSM"])

    return {
        "overall":       _stats(amounts, sqm),
        "by_rooms":      {k: _stats(by_rooms[k], by_rooms_sqm[k])
                          for k in sorted(by_rooms)},
        "by_floor_type": {ft: _stats(by_floor[ft], by_floor_sqm[ft])
                          for ft in by_floor},
    }
```

- [ ] **Step 4: Implement compute_trends in analyze.py**

Replace the `compute_trends` function body:

```python
def compute_trends(deals):
    """Compute quarterly deal volume and price trend direction."""
    by_quarter = defaultdict(list)

    for d in deals:
        date_str = d.get("dealDate") or ""
        if not date_str:
            continue
        try:
            dt = datetime.fromisoformat(str(date_str)[:10])
        except ValueError:
            continue
        q      = (dt.month - 1) // 3 + 1
        label  = f"Q{q} {dt.year}"
        by_quarter[label].append(d)

    sorted_labels = sorted(
        by_quarter.keys(),
        key=lambda x: (int(x.split()[1]), int(x[1]))
    )

    quarterly = []
    for label in sorted_labels:
        q_deals  = by_quarter[label]
        amounts  = [d["dealAmount"] for d in q_deals if d.get("dealAmount")]
        quarterly.append({
            "label":      label,
            "count":      len(q_deals),
            "mean_price": round(statistics.mean(amounts)) if amounts else 0,
        })

    # Direction: compare last 2 quarters vs first 2 (need ≥ 4 quarters)
    direction = "stable"
    if len(quarterly) >= 4:
        recent_prices = [q["mean_price"] for q in quarterly[-2:] if q["mean_price"]]
        older_prices  = [q["mean_price"] for q in quarterly[:2]  if q["mean_price"]]
        if recent_prices and older_prices:
            recent_avg = statistics.mean(recent_prices)
            older_avg  = statistics.mean(older_prices)
            if recent_avg > older_avg * 1.03:
                direction = "rising"
            elif recent_avg < older_avg * 0.97:
                direction = "falling"

    return {"by_quarter": quarterly, "direction": direction}
```

- [ ] **Step 5: Implement find_outliers in analyze.py**

Replace the `find_outliers` function body:

```python
def find_outliers(deals, threshold=0.3):
    """Return deals whose priceSM deviates ≥ threshold fraction from the mean."""
    with_sqm = [d for d in deals if d.get("priceSM")]
    if not with_sqm:
        return []

    mean = statistics.mean(d["priceSM"] for d in with_sqm)
    outliers = []
    for d in with_sqm:
        deviation = abs(d["priceSM"] - mean) / mean
        if deviation >= threshold:
            entry = dict(d)
            entry["_outlier_direction"] = "high" if d["priceSM"] > mean else "low"
            entry["_outlier_pct"]       = round(deviation * 100)
            outliers.append(entry)
    return outliers
```

- [ ] **Step 6: Implement analyze in analyze.py**

Replace the `analyze` function body:

```python
def analyze(deals, street=None, settlement=None):
    valid = [d for d in deals if d.get("dealAmount")]

    dates = sorted(
        (d["dealDate"] for d in valid if d.get("dealDate")),
        key=str
    )

    return {
        "meta": {
            "street":      street,
            "settlement":  settlement,
            "total_deals": len(valid),
            "period_from": dates[0]  if dates else "",
            "period_to":   dates[-1] if dates else "",
        },
        "prices":   compute_prices(valid),
        "trends":   compute_trends(valid),
        "outliers": find_outliers(valid),
        "recent":   sorted(valid, key=lambda d: d.get("dealDate", ""), reverse=True)[:20],
    }
```

- [ ] **Step 7: Run all analyze tests**

```bash
python3 -m pytest tests/test_analyze.py -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add analyze.py tests/test_analyze.py
git commit -m "feat: implement analyze.py — prices, trends, outliers, analyze"
```

---

## Task 3: Implement report.py

**Files:**
- Create: `report.py`
- Create: `tests/test_report.py`

- [ ] **Step 1: Write a smoke test**

Create `tests/test_report.py`:

```python
import os
import tempfile
from pathlib import Path
from analyze import analyze
from report import generate_html
from tests.fixtures import SAMPLE_DEALS


class TestGenerateHtml:
    def test_creates_html_file(self):
        stats = analyze(SAMPLE_DEALS, street="דיזנגוף", settlement="תל אביב")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_html(stats, output_dir=tmpdir, street="דיזנגוף")
            assert Path(path).exists()
            assert path.endswith(".html")

    def test_html_contains_street_name(self):
        stats = analyze(SAMPLE_DEALS, street="דיזנגוף", settlement="תל אביב")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_html(stats, output_dir=tmpdir, street="דיזנגוף")
            content = Path(path).read_text(encoding="utf-8")
            assert "דיזנגוף" in content

    def test_html_contains_price_data(self):
        stats = analyze(SAMPLE_DEALS, street="דיזנגוף", settlement="תל אביב")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_html(stats, output_dir=tmpdir, street="דיזנגוף")
            content = Path(path).read_text(encoding="utf-8")
            assert "₪" in content

    def test_html_is_rtl(self):
        stats = analyze(SAMPLE_DEALS, street="דיזנגוף", settlement="תל אביב")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_html(stats, output_dir=tmpdir, street="דיזנגוף")
            content = Path(path).read_text(encoding="utf-8")
            assert 'dir="rtl"' in content

    def test_empty_deals_no_crash(self):
        stats = analyze([], street="טסט", settlement="טסט")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_html(stats, output_dir=tmpdir, street="טסט")
            assert Path(path).exists()
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
python3 -m pytest tests/test_report.py -v 2>&1 | head -10
```

Expected: FAIL — `No module named 'report'`.

- [ ] **Step 3: Create report.py**

Create `report.py`:

```python
"""
report.py — Generate a self-contained Hebrew HTML report from analyze() output.
No external dependencies — all CSS is inline, no JS libraries.
"""

import re
from datetime import date
from pathlib import Path


def _fmt_price(n):
    """Format a number as ₪1,234,567. Returns '—' for None/0."""
    if not n:
        return "—"
    return "₪{:,}".format(int(n))


def _trend_badge(direction):
    """Return a coloured Hebrew badge for the price trend direction."""
    cfg = {
        "rising":  ("#2a9d8f", "עולה ↑"),
        "falling": ("#e76f51", "יורדת ↓"),
        "stable":  ("#457b9d", "יציבה →"),
    }
    color, label = cfg.get(direction, ("#888", direction))
    return (
        f'<span style="background:{color};color:#fff;'
        f'padding:3px 12px;border-radius:12px;font-size:0.85em">{label}</span>'
    )


def _bar_chart_html(quarters):
    """Return a pure-CSS bar chart for quarterly deal volumes."""
    if not quarters:
        return "<p style='color:#888'>אין מספיק נתונים לתצוגת מגמות</p>"

    max_count = max(q["count"] for q in quarters) or 1
    bars = ""
    for q in quarters:
        height = max(6, int(q["count"] / max_count * 120))
        bars += (
            f'<div style="display:flex;flex-direction:column;align-items:center;margin:0 8px">'
            f'  <div style="font-size:0.75em;color:#555;margin-bottom:4px">{q["count"]}</div>'
            f'  <div style="width:36px;height:{height}px;background:#457b9d;border-radius:3px 3px 0 0"></div>'
            f'  <div style="font-size:0.72em;color:#666;margin-top:6px;'
            f'writing-mode:vertical-rl;transform:rotate(180deg)">{q["label"]}</div>'
            f'</div>'
        )
    return f'<div style="display:flex;align-items:flex-end;padding:16px 0">{bars}</div>'


def _rooms_table_rows(by_rooms):
    """Return <tr> elements for the rooms breakdown table."""
    rows = ""
    for key in sorted(by_rooms.keys()):
        r = by_rooms[key]
        if r.get("count", 0) == 0:
            continue
        rows += (
            f"<tr>"
            f"<td>{key} חדרים</td>"
            f"<td style='text-align:center'>{r['count']}</td>"
            f"<td style='text-align:left'>{_fmt_price(r.get('mean'))}</td>"
            f"<td style='text-align:left'>{_fmt_price(r.get('mean_per_sqm'))}</td>"
            f"</tr>"
        )
    return rows


def _recent_rows(recent):
    """Return <tr> elements for the recent transactions table."""
    rows = ""
    for d in recent[:15]:
        rows += (
            f"<tr>"
            f"<td>{d.get('dealDate','')}</td>"
            f"<td>{d.get('address','')}</td>"
            f"<td style='text-align:left'>{_fmt_price(d.get('dealAmount'))}</td>"
            f"<td style='text-align:center'>{int(d.get('assetArea') or 0) or '—'}</td>"
            f"<td style='text-align:center'>{int(d.get('roomNum') or 0) or '—'}</td>"
            f"<td>{d.get('floor','')}</td>"
            f"<td>{d.get('dealNature','')}</td>"
            f"</tr>"
        )
    return rows


def _outliers_section(outliers):
    """Return an HTML section for outlier deals, or '' if none."""
    if not outliers:
        return ""
    rows = ""
    for d in outliers[:6]:
        direction_label = "גבוה" if d.get("_outlier_direction") == "high" else "נמוך"
        rows += (
            f"<tr>"
            f"<td>{d.get('address','')}</td>"
            f"<td style='text-align:left'>{_fmt_price(d.get('dealAmount'))}</td>"
            f"<td style='text-align:left'>{_fmt_price(d.get('priceSM'))}</td>"
            f"<td>{direction_label} ב-{d.get('_outlier_pct','')}%</td>"
            f"</tr>"
        )
    return f"""
    <div class="card">
      <h2>⚡ עסקאות חריגות</h2>
      <table>
        <tr><th>כתובת</th><th>מחיר</th><th>מחיר למ"ר</th><th>חריגה מהממוצע</th></tr>
        {rows}
      </table>
    </div>"""


_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, Arial, sans-serif; background: #f7f8fa;
       color: #1a1a1a; direction: rtl; }
.container { max-width: 960px; margin: 0 auto; padding: 24px 16px; }
.header { background: #1d3557; color: white; padding: 28px 32px;
          border-radius: 10px; margin-bottom: 24px; }
.header h1 { font-size: 1.7em; margin-bottom: 6px; }
.header .sub { font-size: 0.88em; opacity: 0.8; }
.card { background: white; border-radius: 10px; padding: 24px;
        margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
h2 { font-size: 1.1em; color: #1d3557; margin-bottom: 16px; }
.summary-box { background: #eaf2fb; padding: 16px 20px; border-radius: 8px;
               border-right: 4px solid #457b9d; line-height: 1.8; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr));
             gap: 14px; margin-bottom: 20px; }
.stat { background: #f0f4f8; padding: 14px 18px; border-radius: 8px; }
.stat .lbl { font-size: 0.8em; color: #666; margin-bottom: 4px; }
.stat .val { font-size: 1.3em; font-weight: 700; color: #1d3557; }
table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
th { background: #1d3557; color: white; padding: 9px 12px;
     text-align: right; font-weight: 600; }
td { padding: 8px 12px; border-bottom: 1px solid #eee; }
tr:hover td { background: #f5f8fc; }
"""


def generate_html(stats, output_dir="output", street=None):
    """
    Generate a self-contained Hebrew HTML report and save it to output_dir.

    Args:
        stats:      dict returned by analyze()
        output_dir: directory to save the HTML file
        street:     street name string for the filename and title

    Returns:
        Absolute path string of the created HTML file.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    meta    = stats.get("meta", {})
    prices  = stats.get("prices", {})
    overall = prices.get("overall", {})
    trends  = stats.get("trends", {})
    by_rooms = prices.get("by_rooms", {})

    title     = street or meta.get("settlement", "אזור")
    today     = date.today().isoformat()
    direction = trends.get("direction", "stable")
    total     = meta.get("total_deals", 0)

    # Executive summary sentence
    if total == 0:
        summary_text = "לא נמצאו עסקאות לתקופה זו."
    else:
        summary_text = (
            f"נבדקו {total} עסקאות בתקופה "
            f"{meta.get('period_from','')} עד {meta.get('period_to','')}. "
            f"מחיר ממוצע: {_fmt_price(overall.get('mean'))}, "
            f"מחיר ממוצע למ\"ר: {_fmt_price(overall.get('mean_per_sqm'))}."
        )

    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>ניתוח שוק — {title}</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>ניתוח שוק — {title}</h1>
    <div class="sub">הופק: {today} &nbsp;|&nbsp;
    תקופה: {meta.get('period_from','')} — {meta.get('period_to','')} &nbsp;|&nbsp;
    {total} עסקאות</div>
  </div>

  <div class="card">
    <h2>📋 סיכום מנהלים</h2>
    <div class="summary-box">
      {summary_text} &nbsp; {_trend_badge(direction)}
    </div>
  </div>

  <div class="card">
    <h2>💰 נתוני מחירים</h2>
    <div class="stat-grid">
      <div class="stat"><div class="lbl">ממוצע מחיר</div>
        <div class="val">{_fmt_price(overall.get('mean'))}</div></div>
      <div class="stat"><div class="lbl">חציון מחיר</div>
        <div class="val">{_fmt_price(overall.get('median'))}</div></div>
      <div class="stat"><div class="lbl">ממוצע למ"ר</div>
        <div class="val">{_fmt_price(overall.get('mean_per_sqm'))}</div></div>
      <div class="stat"><div class="lbl">חציון למ"ר</div>
        <div class="val">{_fmt_price(overall.get('median_per_sqm'))}</div></div>
    </div>
    <table>
      <tr><th>סוג</th><th>עסקאות</th><th>ממוצע מחיר</th><th>ממוצע למ"ר</th></tr>
      {_rooms_table_rows(by_rooms)}
    </table>
  </div>

  <div class="card">
    <h2>📈 מגמת עסקאות רבעונית</h2>
    {_bar_chart_html(trends.get('by_quarter', []))}
  </div>

  <div class="card">
    <h2>🏠 עסקאות אחרונות</h2>
    <table>
      <tr><th>תאריך</th><th>כתובת</th><th>מחיר</th>
          <th>מ"ר</th><th>חדרים</th><th>קומה</th><th>סוג</th></tr>
      {_recent_rows(stats.get('recent', []))}
    </table>
  </div>

  {_outliers_section(stats.get('outliers', []))}

</div>
</body>
</html>"""

    safe_name = re.sub(r"[^\w\u0590-\u05FF]", "_", title)
    out_path  = Path(output_dir) / f"report_{safe_name}_{today}.html"
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)
```

- [ ] **Step 4: Run report tests**

```bash
python3 -m pytest tests/test_report.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add report.py tests/test_report.py
git commit -m "feat: implement report.py — self-contained Hebrew HTML generation"
```

---

## Task 4: Implement research.py (CLI orchestrator)

**Files:**
- Create: `research.py`

- [ ] **Step 1: Create research.py**

Create `research.py`:

```python
"""
research.py — CLI entry point for the Nadlan Research System.

Usage:
  python3 research.py --settlement "תל אביב" --street "דיזנגוף" [--limit 200] [--year 2025]
  python3 research.py --settlement "תל אביב" --token "UUID-FROM-BROWSER"

Steps:
  1. Fetch deals via nadlan_scraper.py
  2. Analyze via analyze.py
  3. Generate HTML report via report.py
  4. Open HTML in browser
"""

import argparse
import asyncio
import json
import subprocess
import sys
import webbrowser
from pathlib import Path

from nadlan_scraper import (
    lookup_settlement,
    lookup_street,
    get_recaptcha_token,
    fetch_deals,
)
from analyze import analyze
from report import generate_html

OUTPUT_DIR = "output"


def _save_json(data, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run(settlement_name, street_name=None, limit=200, year=None, token=None):
    """
    Full pipeline: scrape → analyze → report → open browser.

    Returns:
        str: path to the generated HTML report
    """
    # 1. Settlement
    print(f"מחפש יישוב: '{settlement_name}'...")
    settlement_id = lookup_settlement(settlement_name)
    if not settlement_id:
        print(f"שגיאה: יישוב '{settlement_name}' לא נמצא.")
        sys.exit(1)
    print(f"  → ID: {settlement_id}")

    # 2. Street (optional)
    base_id, base_name, search_label = settlement_id, "settlmentID", settlement_name
    if street_name:
        print(f"מחפש רחוב: '{street_name}'...")
        street_id = lookup_street(settlement_id, street_name)
        if street_id:
            base_id, base_name, search_label = street_id, "streetCode", street_name
            print(f"  → ID: {street_id}")
        else:
            print(f"  ⚠ רחוב לא נמצא, מחפש ברמת יישוב.")

    # 3. reCAPTCHA token
    if token:
        print("משתמש ב-token ידני.")
    else:
        print("פותח דפדפן לקבלת reCAPTCHA token...")
        token = asyncio.run(get_recaptcha_token(settlement_id))
        if not token:
            print("\n⚠ לא הצלחתי לקבל token אוטומטית.")
            print("הוצאה ידנית:")
            print(f"  1. פתח Chrome → https://www.nadlan.gov.il/?view=settlement&id={settlement_id}&page=deals")
            print("  2. המתן 15 שניות")
            print("  3. DevTools (F12) → Console → sessionStorage.getItem('recaptchaServerToken')")
            print(f"  4. python3 research.py --settlement \"{settlement_name}\" --token \"PASTE_HERE\"")
            sys.exit(1)
        print(f"  Token: {token[:40]}...")

    # 4. Fetch
    print(f"\nמושך עסקאות ({base_name}={base_id}, מקסימום {limit})...")
    deals = fetch_deals(base_id, base_name, token, max_items=limit, year=year)
    print(f"  נמצאו {len(deals)} עסקאות")

    if not deals:
        print("אין עסקאות לניתוח.")
        sys.exit(0)

    raw_path = Path(OUTPUT_DIR) / f"deals_raw_{search_label}.json"
    _save_json(deals, raw_path)
    print(f"  נשמר: {raw_path}")

    # 5. Analyze
    print("מנתח נתונים...")
    stats = analyze(deals, street=street_name, settlement=settlement_name)

    stats_path = Path(OUTPUT_DIR) / f"analysis_{search_label}.json"
    _save_json(stats, stats_path)

    # 6. Report
    print("מייצר דוח HTML...")
    report_path = generate_html(stats, output_dir=OUTPUT_DIR, street=search_label)
    print(f"  נשמר: {report_path}")

    # 7. Open in browser
    webbrowser.open(f"file://{Path(report_path).resolve()}")

    # 8. Print summary to stdout
    overall = stats["prices"]["overall"]
    direction_heb = {"rising": "עולה", "falling": "יורדת", "stable": "יציבה"}.get(
        stats["trends"]["direction"], ""
    )
    print(f"\n{'='*50}")
    print(f"סיכום: {stats['meta']['total_deals']} עסקאות ב-{search_label}")
    print(f"  ממוצע מחיר:    ₪{overall.get('mean', 0):,.0f}")
    print(f"  ממוצע למ\"ר:   ₪{overall.get('mean_per_sqm', 0):,.0f}")
    print(f"  מגמת מחירים:  {direction_heb}")
    print(f"  דוח: {report_path}")
    print(f"{'='*50}\n")

    return report_path


def main():
    parser = argparse.ArgumentParser(description="מערכת חקר עסקאות נדל\"ן")
    parser.add_argument("--settlement", required=True, help="שם יישוב (חובה)")
    parser.add_argument("--street",                   help="שם רחוב (אופציונלי)")
    parser.add_argument("--limit",     type=int, default=200, help="מקסימום עסקאות")
    parser.add_argument("--year",      type=int,              help="סנן לפי שנה")
    parser.add_argument("--token",                    help="recaptchaServerToken ידני")
    args = parser.parse_args()

    run(
        settlement_name=args.settlement,
        street_name=args.street,
        limit=args.limit,
        year=args.year,
        token=args.token,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test the import**

```bash
python3 -c "from research import run; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run a real end-to-end test**

```bash
python3 research.py --settlement "תל אביב" --street "דיזנגוף" --limit 50
```

Expected:
- Browser opens with Hebrew HTML report
- Console prints price summary
- `output/` directory contains `deals_raw_דיזנגוף.json`, `analysis_דיזנגוף.json`, `report_דיזנגוף_<date>.html`

- [ ] **Step 4: Commit**

```bash
git add research.py
git commit -m "feat: implement research.py — CLI orchestrator for full pipeline"
```

---

## Task 5: Create the Claude skill

**Files:**
- Create: `skills/nadlan-research.md`

- [ ] **Step 1: Create skills directory and skill file**

```bash
mkdir -p skills
```

Create `skills/nadlan-research.md`:

```markdown
---
name: nadlan-research
description: Research a real estate area using real transaction data from nadlan.gov.il. Use when the user asks about property prices, market trends, or whether to buy in a specific area or street in Israel.
---

# Nadlan Research Skill

You are a real estate market analyst with access to real transaction data from Israel's Tax Authority (nadlan.gov.il).

## When this skill is triggered

Activate when the user asks questions like:
- "מה קורה בדיזנגוף?"
- "כמה עולות דירות ברחוב X?"
- "כדאי לקנות בשכונה Y?"
- "מה המחיר הממוצע למ\"ר בתל אביב?"
- Any question about Israeli real estate prices, transactions, or market trends.

## How to respond

### Step 1 — Parse the question

Extract from the user's message:
- **יישוב** (settlement/city): required. If unclear, ask: "באיזו עיר?"
- **רחוב** (street): optional. If the question mentions a specific street, use it.
- **שנה** (year): optional. Default = last 2 years of data.

### Step 2 — Run the pipeline

Run `research.py` with the extracted parameters:

```bash
python3 research.py --settlement "SETTLEMENT" [--street "STREET"] [--limit 150]
```

Wait for the command to complete. The script will:
1. Open a browser window briefly to get the reCAPTCHA token (this is normal)
2. Fetch real transaction data from nadlan.gov.il
3. Generate an HTML report and open it in the browser
4. Print a summary to the console

If the script fails with a token error, run with `--token` using the manual instructions it prints.

### Step 3 — Summarize findings in the conversation

After `research.py` completes, read the console output and write a 3–5 sentence Hebrew summary directly in the conversation. Answer the user's original question specifically.

Structure your summary as:
1. **עובדות** — key numbers (average price, price per sqm, number of deals)
2. **מגמה** — is the market rising, falling, or stable?
3. **תשובה לשאלה** — direct answer to what the user actually asked
4. **נכס חריג** — mention if there were significant outliers (if any)

### Example

User: "כדאי לקנות דירת 3 חדרים בדיזנגוף?"

Run: `python3 research.py --settlement "תל אביב" --street "דיזנגוף" --limit 150`

Then summarize:
> "ברחוב דיזנגוף בתל אביב נרשמו 87 עסקאות בשנתיים האחרונות. מחיר ממוצע לדירת 3 חדרים: ₪4.2M, ממוצע למ\"ר: ₪65,000. המגמה יציבה עם עלייה קלה של ~3% בשנה האחרונה. לפי הנתונים, הרחוב מציג ביקוש עקבי — אם המחיר המבוקש תואם הממוצע, זו עסקה סבירה בשוק הנוכחי."

## Important notes

- Never invent prices. All numbers come from the actual script output.
- The HTML report opens automatically — tell the user: "פתחתי את הדוח המלא בדפדפן שלך."
- If fewer than 5 deals are found, mention this limitation in your summary.
- This is data analysis, not legal or financial advice. State this if the user asks for a definitive recommendation.
```

- [ ] **Step 2: Verify the skill file is valid**

```bash
python3 -c "
import pathlib
content = pathlib.Path('skills/nadlan-research.md').read_text()
assert 'name: nadlan-research' in content
assert 'research.py' in content
print('Skill file OK')
"
```

Expected: `Skill file OK`

- [ ] **Step 3: Commit**

```bash
git add skills/nadlan-research.md
git commit -m "feat: add nadlan-research Claude skill"
```

---

## Task 6: End-to-end validation

**Files:** No new files — validation only.

- [ ] **Step 1: Run the full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests PASS (17 analyze + 5 report = 22 total).

- [ ] **Step 2: Run an end-to-end research query**

```bash
python3 research.py --settlement "רמת גן" --limit 50
```

Verify:
- Browser opens with Hebrew HTML report in RTL
- Report shows price statistics, bar chart, recent transactions table
- Console prints summary with ₪ numbers
- `output/` contains the 3 output files

- [ ] **Step 3: Run with a street query**

```bash
python3 research.py --settlement "תל אביב" --street "בן יהודה" --limit 100
```

Verify: report title shows "בן יהודה", rooms table is populated.

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "feat: nadlan research system complete — analyze, report, research, skill"
```

---

## Self-Review Notes

**Spec coverage:**
- ✅ Free-form question → parsed by skill → drives research.py
- ✅ Prices: mean, median, per sqm, by rooms, by floor type
- ✅ Trends: quarterly bar chart, direction (rising/falling/stable)
- ✅ Recent transactions table
- ✅ Outliers section
- ✅ Hebrew RTL HTML, no external dependencies
- ✅ Street comparison: not in Phase 1 scope (Out of Scope in spec)
- ✅ Error handling: no deals found, token failure, street not found

**Type consistency:** `analyze()` returns dict consumed directly by `generate_html()`. `fetch_deals()` returns list passed directly to `analyze()`. No type mismatches.

**No placeholders:** All code blocks are complete and runnable.
