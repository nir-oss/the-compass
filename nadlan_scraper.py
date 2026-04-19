"""
nadlan_scraper.py — עסקאות נדל"ן מ-nadlan.gov.il

שימוש:
  # חיפוש ברמת יישוב (כל תל אביב):
  python3 nadlan_scraper.py --settlement "תל אביב" --limit 100

  # חיפוש ברמת רחוב (דיזנגוף בתל אביב):
  python3 nadlan_scraper.py --settlement "תל אביב" --street "דיזנגוף" --limit 50

  # סינון לפי שנה:
  python3 nadlan_scraper.py --settlement "תל אביב" --street "דיזנגוף" --year 2024

  # עם token ידני (מ-DevTools > Console > sessionStorage.getItem('recaptchaServerToken')):
  python3 nadlan_scraper.py --settlement "תל אביב" --token "UUID-HERE"
"""

import asyncio
import json
import csv
import gzip
import base64
import time
import argparse
import jwt
import requests as _req
from datetime import datetime
from typing import Optional

# ─── Config ──────────────────────────────────────────────────────────────────
JWT_SECRET = "90c3e620192348f1bd46fcd9138c3c68"
API_BASE   = "https://api.nadlan.gov.il"
DATA_BASE  = "https://data.nadlan.gov.il/api"
DOMAIN     = "www.nadlan.gov.il"
HEADERS    = {
    "Content-Type": "text/plain",
    "User-Agent":   "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer":      "https://www.nadlan.gov.il/",
    "Origin":       "https://www.nadlan.gov.il",
}

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _decompress(text: str) -> dict:
    pad = 4 - len(text) % 4
    if pad != 4:
        text += "=" * pad
    return json.loads(gzip.decompress(base64.b64decode(text)))


def _build_body(base_id, base_name: str, recaptcha_token: str,
                fetch_number: int = 1, extra: dict = None) -> dict:
    """Build signed JWT body for the deal-data API."""
    payload = {
        "base_id":      str(base_id),
        "base_name":    base_name,
        "fetch_number": fetch_number,
        "type_order":   "dealDate_down",
        "token":        recaptcha_token,
        "sk":           jwt.encode(
                            {"domain": DOMAIN, "exp": int(time.time()) + 120},
                            JWT_SECRET, algorithm="HS256"
                        ),
        "exp":          int(time.time()) + 120,
        "domain":       DOMAIN,
    }
    if extra:
        payload.update(extra)
    return {"##": jwt.encode(payload, JWT_SECRET, algorithm="HS256")[::-1]}


# ─── Lookup: settlements & streets ───────────────────────────────────────────

def lookup_settlement(name: str) -> Optional[int]:
    """Find settlement ID by name (partial match, then fuzzy fallback)."""
    r = _req.get(f"{DATA_BASE}/index/setl_types.json",
                 headers={"Referer": "https://www.nadlan.gov.il/"}, timeout=15)
    r.raise_for_status()
    data = r.json()
    name_lower = name.lower()

    # Exact substring match first
    for sid, info in data.items():
        if name_lower in info.get("SETL_NAME", "").lower():
            return int(sid)

    # Fuzzy fallback: ignore yud doublings (הרצליה ↔ הרצלייה) and similar
    import difflib
    candidates = {sid: info.get("SETL_NAME", "") for sid, info in data.items()}
    names = list(candidates.values())
    matches = difflib.get_close_matches(name, names, n=1, cutoff=0.75)
    if matches:
        for sid, n in candidates.items():
            if n == matches[0]:
                return int(sid)

    return None


def lookup_street(settlement_id: int, street_name: str) -> Optional[int]:
    """Find street ID within a settlement."""
    r = _req.get(f"{DATA_BASE}/pages/settlement/buy/{settlement_id}.json",
                 headers={"Referer": "https://www.nadlan.gov.il/"}, timeout=15)
    r.raise_for_status()
    streets = r.json().get("otherSettlmentStreets", [])
    name_lower = street_name.lower()
    for s in streets:
        if isinstance(s, dict) and name_lower in s.get("title", "").lower():
            return s["id"]
    return None


# ─── reCAPTCHA token via browser ─────────────────────────────────────────────

async def get_recaptcha_token(settlement_id: int) -> Optional[str]:
    """
    Open a browser window to nadlan.gov.il, wait for reCAPTCHA to pass,
    and return the server token from sessionStorage.
    """
    from playwright.async_api import async_playwright

    token_holder = []

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                channel="chrome",
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )

        context = await browser.new_context(
            locale="he-IL",
            timezone_id="Asia/Jerusalem",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        url = f"https://www.nadlan.gov.il/?view=settlement&id={settlement_id}&page=deals"
        print(f"  Opening: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)

        print("  Waiting for reCAPTCHA (up to 60s)...", flush=True)
        for i in range(60):
            await page.wait_for_timeout(1000)
            token = await page.evaluate("sessionStorage.getItem('recaptchaServerToken')")
            if token:
                token = token.strip().strip('"')
                if token and token not in ("null", "None", "undefined"):
                    print(f"  Token obtained after {i + 1}s!")
                    token_holder.append(token)
                    break
            if i % 10 == 9:
                print(f"  Still waiting... ({i + 1}s)", flush=True)

        await browser.close()

    return token_holder[0] if token_holder else None


# ─── API fetch ────────────────────────────────────────────────────────────────

def fetch_deals(base_id, base_name: str, recaptcha_token: str,
                max_items: int = 100, year: Optional[int] = None) -> list:
    """Fetch deals from the deal-data API with pagination."""
    all_deals = []
    page_num = 1

    while len(all_deals) < max_items:
        body = _build_body(base_id, base_name, recaptcha_token, fetch_number=page_num)
        r = _req.post(f"{API_BASE}/deal-data", json=body, headers=HEADERS, timeout=30)
        r.raise_for_status()

        try:
            data = _decompress(r.text)
        except Exception:
            try:
                data = r.json()
            except Exception:
                print(f"  Parse error: {r.text[:100]}")
                break

        status = data.get("statusCode", 0)
        if status == 405:
            print("  reCAPTCHA token rejected (405). Token may have expired.")
            break
        if status == 403:
            print("  Rate limited (403).")
            break
        if status != 200:
            print(f"  API error {status}: {data.get('body', '')[:100]}")
            break

        items = data.get("data", {}).get("items", [])
        total = data.get("data", {}).get("total_rows", 0)

        # Filter by year if requested
        if year:
            filtered = []
            for deal in items:
                date_str = deal.get("DEALDATETIME") or deal.get("DEALDATE") or ""
                try:
                    deal_year = datetime.fromisoformat(date_str.replace("Z", "+00:00")).year
                    if deal_year == year:
                        filtered.append(deal)
                except Exception:
                    filtered.append(deal)
            items = filtered

        all_deals.extend(items)
        print(f"  Page {page_num}: {len(items)} deals (total so far: {len(all_deals)}/{total})")

        if not items or len(all_deals) >= min(max_items, total):
            break
        page_num += 1

    return all_deals[:max_items]


# ─── Output ───────────────────────────────────────────────────────────────────

def to_csv_rows(deals: list) -> list:
    rows = []
    for d in deals:
        rows.append({
            "תאריך":          d.get("dealDate") or d.get("DEALDATETIME") or "",
            "כתובת":          d.get("address") or d.get("FULLADRESS") or "",
            "שכונה":          d.get("neighborhoodName") or "",
            "מחיר (₪)":      d.get("dealAmount") or d.get("DEALAMOUNT") or "",
            "מחיר למ״ר (₪)": d.get("priceSM") or "",
            "חדרים":          d.get("roomNum") or d.get("ASSETROOMNUM") or "",
            "קומה":           d.get("floor") or d.get("FLOORNO") or "",
            "שטח במ״ר":      d.get("assetArea") or d.get("DEALNATURE") or "",
            "סוג נכס":        d.get("dealNature") or "",
            "שנת בנייה":     d.get("yearBuilt") or d.get("BUILDINGYEAR") or "",
            "מספר חלקה":     d.get("parcelNum") or "",
        })
    return rows


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="עסקאות נדל\"ן מ-nadlan.gov.il")
    parser.add_argument("--settlement", default="תל אביב",    help="שם יישוב")
    parser.add_argument("--street",                           help="שם רחוב (אופציונלי)")
    parser.add_argument("--year",     type=int,               help="סנן לפי שנה")
    parser.add_argument("--limit",    type=int, default=100,  help="מקסימום עסקאות")
    parser.add_argument("--token",                            help="recaptchaServerToken ידני")
    parser.add_argument("--out-json", default="deals_raw.json")
    parser.add_argument("--out-csv",  default="deals.csv")
    args = parser.parse_args()

    # 1. Settlement ID
    print(f"מחפש יישוב: '{args.settlement}'...")
    settlement_id = lookup_settlement(args.settlement)
    if not settlement_id:
        print(f"יישוב לא נמצא. נסה שם אחר.")
        return
    print(f"  → ID: {settlement_id}")

    # 2. Street ID (optional)
    base_id   = settlement_id
    base_name = "settlmentID"   # Note: API has a typo ("settlment" not "settlement")

    if args.street:
        print(f"מחפש רחוב: '{args.street}'...")
        street_id = lookup_street(settlement_id, args.street)
        if street_id:
            base_id   = street_id
            base_name = "streetCode"
            print(f"  → ID: {street_id}")
        else:
            print(f"  רחוב לא נמצא, מחפש ברמת יישוב.")

    # 3. reCAPTCHA token
    if args.token:
        token = args.token
        print(f"משתמש ב-token ידני.")
    else:
        print("פותח דפדפן לקבלת reCAPTCHA token...")
        token = asyncio.run(get_recaptcha_token(settlement_id))
        if not token:
            print("\nלא הצלחתי לקבל token אוטומטית.")
            print("הוצאה ידנית:")
            print(f"  1. פתח Chrome → https://www.nadlan.gov.il/?view=settlement&id={settlement_id}&page=deals")
            print("  2. המתן 15 שניות")
            print("  3. DevTools (F12) → Console:")
            print("     sessionStorage.getItem('recaptchaServerToken')")
            print(f"  4. python3 nadlan_scraper.py --settlement \"{args.settlement}\" --token \"PASTE_HERE\"")
            return
        print(f"  Token: {token[:40]}...")

    # 4. Fetch
    year_str = f" שנת {args.year}" if args.year else ""
    print(f"\nמושך עסקאות ({base_name} = {base_id}{year_str}, מקסימום {args.limit})...")
    deals = fetch_deals(base_id, base_name, token, max_items=args.limit, year=args.year)
    print(f"\nנמצאו {len(deals)} עסקאות")

    if not deals:
        print("אין עסקאות. הסיבות האפשריות:")
        print("  - ה-token פג (הרץ שוב)")
        print("  - לא נמצאו עסקאות לפרמטרים אלו")
        return

    # 5. Save
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(deals, f, ensure_ascii=False, indent=2)

    rows = to_csv_rows(deals)
    fields = ["תאריך", "כתובת", "שכונה", "מחיר (₪)", "מחיר למ״ר (₪)", "חדרים", "קומה", "שטח במ״ר", "סוג נכס", "שנת בנייה", "מספר חלקה"]
    with open(args.out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # Print table
    print(f"\n{'תאריך':<12} {'כתובת':<28} {'מחיר (₪)':<12} {'מ״ר':<6} {'חדרים':<7} {'קומה':<10} סוג נכס")
    print("─" * 100)
    for row in rows[:20]:
        print(f"{str(row['תאריך']):<12} {str(row['כתובת'])[:27]:<28} "
              f"{str(row['מחיר (₪)']):<12} {str(row['שטח במ״ר']):<6} "
              f"{str(row['חדרים']):<7} {str(row['קומה'])[:9]:<10} {str(row['סוג נכס'])[:20]}")
    if len(rows) > 20:
        print(f"... ועוד {len(rows) - 20} עסקאות")

    print(f"\nנשמר → {args.out_json}, {args.out_csv}")


if __name__ == "__main__":
    main()
