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
