"""
research.py — CLI entry point for the Nadlan Research System.

Data priority:
  1. odata_db  — local SQLite built from odata.org.il ZIP (20 major cities, no reCAPTCHA)
  2. nadlan.gov.il live scraping — fallback with reCAPTCHA token (all cities)

Exit codes:
  0  — success
  1  — general error (no data, settlement not found, etc.)
  2  — NEEDS_TOKEN: reCAPTCHA token required (live scraping path only)
  3  — CITY_UNAVAILABLE: city not in odata dataset and live scraping unavailable
"""

import argparse
import asyncio
import json
import sys
import webbrowser
import os
from pathlib import Path

from nadlan_scraper import (
    lookup_settlement,
    lookup_street,
    lookup_neighborhood,
    get_recaptcha_token,
    fetch_deals,
)
from analyze import analyze
from report import generate_html
import odata_db

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", str(Path(__file__).parent / "output"))


def _save_json(data, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _finish(deals, search_label, settlement_name, limit):
    """Analyze + report + print summary. Shared by both data paths."""
    deals = deals[:limit]
    print(f"  נמצאו {len(deals)} עסקאות")

    if not deals:
        print("אין עסקאות לניתוח עם הפרמטרים שנבחרו.")
        sys.exit(1)

    raw_path = Path(OUTPUT_DIR) / f"deals_raw_{search_label}.json"
    _save_json(deals, raw_path)
    print(f"  נשמר: {raw_path}")

    print("מנתח נתונים...")
    stats = analyze(deals, street=search_label, settlement=settlement_name)
    _save_json(stats, Path(OUTPUT_DIR) / f"analysis_{search_label}.json")

    print("מייצר דוח HTML...")
    report_path = generate_html(stats, output_dir=OUTPUT_DIR, street=search_label)
    print(f"  נשמר: {report_path}")

    webbrowser.open(f"file://{Path(report_path).resolve()}")

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


def run(settlement_name, street_name=None, neighborhood_name=None,
        limit=200, year=None, min_year=None, token=None,
        rooms=None, property_type=None,
        min_price=None, max_price=None,
        min_area=None, max_area=None):

    search_label = street_name or neighborhood_name or settlement_name

    # ── Path A: odata local DB ────────────────────────────────────────────────
    if odata_db.is_city_available(settlement_name):
        if not odata_db.is_ready():
            print(f"CITY_UNAVAILABLE:{json.dumps({'reason': 'loading', 'city': settlement_name}, ensure_ascii=False)}")
            sys.exit(3)

        print(f"[odata] שולף נתונים מהמסד המקומי עבור '{settlement_name}'...")
        deals = odata_db.query(
            city_name=settlement_name,
            street=street_name,
            neighborhood=neighborhood_name,
            rooms=rooms,
            property_type=property_type,
            min_price=min_price,
            max_price=max_price,
            min_area=min_area,
            max_area=max_area,
            min_year=min_year,
            year=year,
            max_items=limit,
        )
        return _finish(deals, search_label, settlement_name, limit)

    # ── Path B: city not in odata → try live scraping ────────────────────────
    print(f"מחפש יישוב: '{settlement_name}'...")
    settlement_id = lookup_settlement(settlement_name)
    if not settlement_id:
        print(f"CITY_UNAVAILABLE:{json.dumps({'reason': 'not_found', 'city': settlement_name}, ensure_ascii=False)}")
        sys.exit(3)
    print(f"  → ID: {settlement_id}")

    base_id, base_name = settlement_id, "settlmentID"
    neighborhood_filter = None

    if street_name:
        print(f"מחפש רחוב: '{street_name}'...")
        street_id = lookup_street(settlement_id, street_name)
        if street_id:
            base_id, base_name = street_id, "streetCode"
            print(f"  → ID: {street_id}")
        else:
            print(f"  ⚠ רחוב לא נמצא, מחפש ברמת יישוב.")

    elif neighborhood_name:
        print(f"מחפש שכונה: '{neighborhood_name}'...")
        nbhd = lookup_neighborhood(settlement_id, neighborhood_name)
        if nbhd:
            nbhd_id, nbhd_matched = nbhd
            base_id, base_name = nbhd_id, "neighborhoodId"
            search_label = nbhd_matched
            neighborhood_filter = nbhd_matched
            print(f"  → ID שכונה: {nbhd_id} ({nbhd_matched})")
        else:
            neighborhood_filter = neighborhood_name
            print(f"  → שכונה לא נמצאה ישירות, מסנן מתוך עסקאות היישוב")

    # Token
    if token:
        print("משתמש ב-token ידני.")
    else:
        try:
            import token_cache
            token = token_cache.get()
        except ImportError:
            token = None

        if token:
            print("משתמש ב-token מהcache.")
        else:
            print("מושך token חדש (headless)...")
            try:
                token = asyncio.run(get_recaptcha_token(settlement_id))
            except Exception as e:
                print(f"Playwright error: {e}")
                token = None
            if not token:
                print(f"NEEDS_TOKEN:{json.dumps({'settlement_id': settlement_id, 'settlement_name': settlement_name}, ensure_ascii=False)}")
                sys.exit(2)
        print(f"  Token: {token[:40]}...")

    filters = dict(rooms=rooms, property_type=property_type,
                   min_price=min_price, max_price=max_price,
                   min_area=min_area, max_area=max_area,
                   min_year=min_year)
    active = {k: v for k, v in filters.items() if v is not None}
    if active:
        print(f"  פילטרים: {active}")

    print(f"\nמושך עסקאות ({base_name}={base_id}, מקסימום {limit})...")
    deals = fetch_deals(base_id, base_name, token, max_items=limit, year=year,
                        neighborhood_filter=neighborhood_filter, **filters)

    return _finish(deals, search_label, settlement_name, limit)


def main():
    parser = argparse.ArgumentParser(description="מערכת חקר עסקאות נדל\"ן")
    parser.add_argument("--settlement",    required=True, help="שם יישוב (חובה)")
    parser.add_argument("--street",                      help="שם רחוב (אופציונלי)")
    parser.add_argument("--neighborhood",                help="שם שכונה/רובע (אופציונלי)")
    parser.add_argument("--limit",        type=int, default=200, help="מקסימום עסקאות")
    parser.add_argument("--year",         type=int,               help="סנן לפי שנה")
    parser.add_argument("--min-year",     type=int,               help="מינימום שנה (כולל)")
    parser.add_argument("--token",                       help="recaptchaServerToken ידני")
    parser.add_argument("--rooms",                       help="מספר חדרים (3 / 4.5 / 5+)")
    parser.add_argument("--property-type",               help="סוג נכס (דירה / פנטהאוס ...)")
    parser.add_argument("--min-price",    type=int,      help="מחיר מינימלי (ש\"ח)")
    parser.add_argument("--max-price",    type=int,      help="מחיר מקסימלי (ש\"ח)")
    parser.add_argument("--min-area",     type=float,    help="שטח מינימלי (מ\"ר)")
    parser.add_argument("--max-area",     type=float,    help="שטח מקסימלי (מ\"ר)")
    args = parser.parse_args()

    run(
        settlement_name=args.settlement,
        street_name=args.street,
        neighborhood_name=args.neighborhood,
        limit=args.limit,
        year=args.year,
        min_year=args.min_year,
        token=args.token,
        rooms=args.rooms,
        property_type=args.property_type,
        min_price=args.min_price,
        max_price=args.max_price,
        min_area=args.min_area,
        max_area=args.max_area,
    )


if __name__ == "__main__":
    main()
