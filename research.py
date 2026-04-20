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

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", str(Path(__file__).parent / "output"))


def _save_json(data, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run(settlement_name, street_name=None, neighborhood_name=None,
        limit=200, year=None, min_year=None, token=None,
        rooms=None, property_type=None,
        min_price=None, max_price=None,
        min_area=None, max_area=None):
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

    # 2. Street / neighborhood (optional; street takes priority)
    base_id, base_name, search_label = settlement_id, "settlmentID", settlement_name
    neighborhood_filter = None  # client-side fallback when no direct neighborhood ID

    if street_name:
        print(f"מחפש רחוב: '{street_name}'...")
        street_id = lookup_street(settlement_id, street_name)
        if street_id:
            base_id, base_name, search_label = street_id, "streetCode", street_name
            print(f"  → ID: {street_id}")
        else:
            print(f"  ⚠ רחוב לא נמצא, מחפש ברמת יישוב.")

    elif neighborhood_name:
        print(f"מחפש שכונה: '{neighborhood_name}'...")
        nbhd = lookup_neighborhood(settlement_id, neighborhood_name)
        if nbhd:
            nbhd_id, nbhd_matched = nbhd
            base_id, base_name, search_label = nbhd_id, "neighborhoodId", nbhd_matched
            # Also apply client-side neighborhood filter as secondary accuracy check
            neighborhood_filter = nbhd_matched
            print(f"  → ID שכונה: {nbhd_id} ({nbhd_matched})")
        else:
            # Fall back: fetch at settlement level and filter by neighborhoodName
            search_label = neighborhood_name
            neighborhood_filter = neighborhood_name
            print(f"  → שכונה לא נמצאה ישירות, מסנן מתוך עסקאות היישוב")

    # 3. reCAPTCHA token — prefer cache, fall back to headless fetch, then manual
    if token:
        print("משתמש ב-token ידני.")
    else:
        # Try cache first (populated by token_cache background thread in app.py)
        try:
            import token_cache
            token = token_cache.get()
        except ImportError:
            token = None

        if token:
            print(f"משתמש ב-token מהcache.")
        else:
            print("מושך token חדש (headless)...")
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
    print(f"  נמצאו {len(deals)} עסקאות")

    if not deals:
        print("אין עסקאות לניתוח — ייתכן שה-token פג תוקף (נסה שוב) או שאין נתונים לפרמטרים אלו.")
        sys.exit(1)  # exit(1) so app.py shows an error instead of silent empty result

    raw_path = Path(OUTPUT_DIR) / f"deals_raw_{search_label}.json"
    _save_json(deals, raw_path)
    print(f"  נשמר: {raw_path}")

    # 5. Analyze
    print("מנתח נתונים...")
    stats = analyze(deals, street=search_label, settlement=settlement_name)

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
