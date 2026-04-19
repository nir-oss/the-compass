"""
analyze.py — Pure statistics functions for nadlan deal data.
Input:  list of deal dicts (from nadlan_scraper.py / deals_raw.json)
Output: nested dict with prices, trends, outliers, recent
"""

import statistics
import re
from collections import defaultdict
from datetime import datetime

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
