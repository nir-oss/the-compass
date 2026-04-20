"""
odata_db.py — Local SQLite cache built from odata.org.il ZIP (~75 MB).

Contains 20 major Israeli cities / 712K transactions (2007-2025).
A background thread downloads and indexes the data once every 35 days.
Queries return the same dict format as nadlan_scraper.fetch_deals().
"""

import io
import logging
import os
import sqlite3
import threading
import time
import zipfile
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

ODATA_ZIP_URL = (
    "https://www.odata.org.il/dataset/84f2bc2d-87a0-474e-a3ea-63d7bb9b5447"
    "/resource/5eb859da-6236-4b67-bcd1-ec4b90875739/download/.zip"
)
_OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "./output"))
DB_PATH = _OUTPUT_DIR / "odata.db"
ZIP_PATH = _OUTPUT_DIR / "odata.zip"
DB_MAX_AGE_DAYS = 35

# city_name values as they appear in the XLSX city_name column
# Keys = search variations, Values = LIKE pattern for SQLite
KNOWN_CITIES: dict[str, str] = {
    "תל אביב":          "תל אביב%",
    "יפו":              "תל אביב%",
    "ירושלים":          "ירושלים%",
    "חיפה":             "חיפה%",
    "נתניה":            "נתניה%",
    "פתח תקווה":        "פתח תקווה%",
    "באר שבע":          "באר שבע%",
    "חולון":            "חולון%",
    "ראשון לציון":      "ראשון לציון%",
    "רמת גן":           "רמת גן%",
    "אשדוד":            "אשדוד%",
    "בת ים":            "בת ים%",
    "בני ברק":          "בני ברק%",
    "רחובות":           "רחובות%",
    "אשקלון":           "אשקלון%",
    "הרצלייה":          "הרצלי%",   # covers הרצלייה / הרצליה
    "הרצליה":           "הרצלי%",
    "כפר סבא":          "כפר סבא%",
    "חדרה":             "חדרה%",
    "רעננה":            "רעננה%",
    "מודיעין":          "מודיעין%",
    "בית שמש":          "בית שמש%",
}

_building = False
_ready    = False
_lock     = threading.Lock()


def city_pattern(city_name: str) -> Optional[str]:
    """Return the SQLite LIKE pattern for city, or None if city not in dataset."""
    name = city_name.strip()
    # Direct lookup
    if name in KNOWN_CITIES:
        return KNOWN_CITIES[name]
    # Substring match against known keys
    for key, pattern in KNOWN_CITIES.items():
        if name in key or key in name:
            return pattern
    return None


def is_city_available(city_name: str) -> bool:
    return city_pattern(city_name) is not None


def is_ready() -> bool:
    return _ready or DB_PATH.exists()


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _parse_price(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(str(val).replace(",", "").strip())
    except ValueError:
        return None


def _parse_area(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(str(val).replace(",", "").strip())
    except ValueError:
        return None


def _parse_year(val) -> Optional[int]:
    if not val:
        return None
    try:
        return int(str(val)[:4])
    except (ValueError, TypeError):
        return None


# ── Background build ──────────────────────────────────────────────────────────

def _build_db() -> None:
    global _building, _ready
    with _lock:
        if _building:
            return
        _building = True

    try:
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Download
        log.info("[odata] Downloading ZIP (~75 MB)...")
        import requests as _req
        resp = _req.get(ODATA_ZIP_URL, stream=True, timeout=180)
        resp.raise_for_status()
        with open(ZIP_PATH, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        log.info("[odata] ZIP downloaded (%.1f MB)", ZIP_PATH.stat().st_size / 1e6)

        # Build SQLite
        import openpyxl
        tmp_db = DB_PATH.with_suffix(".tmp")
        if tmp_db.exists():
            tmp_db.unlink()

        con = sqlite3.connect(str(tmp_db))
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("""
            CREATE TABLE deals (
                id      INTEGER PRIMARY KEY,
                date    TEXT,
                year    INTEGER,
                address TEXT,
                city    TEXT,
                street  TEXT,
                rooms   TEXT,
                floor   TEXT,
                area    REAL,
                price   INTEGER,
                dtype   TEXT
            )
        """)

        zf = zipfile.ZipFile(str(ZIP_PATH))
        for xlsx_name in zf.namelist():
            log.info("[odata] Parsing %s...", xlsx_name)
            data = zf.read(xlsx_name)
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            ws = wb.active
            row_iter = ws.iter_rows(values_only=True)
            next(row_iter)  # skip header row

            batch = []
            for row in row_iter:
                # Columns: DEALDATE, DEALDATETIME, FULLADRESS, DISPLAYADRESS,
                #          GUSH, DEALNATUREDESCRIPTION, ASSETROOMNUM, FLOORNO,
                #          DEALNATURE (=area sqm), DEALAMOUNT,
                #          NEWPROJECTTEXT, PROJECTNAME, BUILDINGYEAR, YEARBUILT,
                #          BUILDINGFLOORS, KEYVALUE, TYPE, POLYGON_ID,
                #          TREND_IS_NEGATIVE, TREND_FORMAT, city_name, street
                (_, deal_dt, full_addr, _, _,
                 deal_desc, rooms, floor,
                 area, amount,
                 _, _, _, _, _, _, _, _, _, _,
                 city, street) = row

                batch.append((
                    str(deal_dt or "")[:10],
                    _parse_year(deal_dt),
                    full_addr,
                    city,
                    street,
                    str(rooms) if rooms is not None else None,
                    floor,
                    _parse_area(area),
                    _parse_price(amount),
                    deal_desc,
                ))
                if len(batch) >= 5000:
                    con.executemany(
                        "INSERT INTO deals(date,year,address,city,street,"
                        "rooms,floor,area,price,dtype) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        batch,
                    )
                    batch.clear()

            if batch:
                con.executemany(
                    "INSERT INTO deals(date,year,address,city,street,"
                    "rooms,floor,area,price,dtype) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    batch,
                )
            con.commit()
            wb.close()

        zf.close()
        log.info("[odata] Building indices...")
        con.execute("CREATE INDEX idx_city        ON deals(city)")
        con.execute("CREATE INDEX idx_city_street  ON deals(city, street)")
        con.execute("CREATE INDEX idx_year         ON deals(year)")
        con.commit()
        total = con.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
        con.close()

        tmp_db.replace(DB_PATH)
        log.info("[odata] DB ready — %s rows at %s", f"{total:,}", DB_PATH)
        with _lock:
            _ready = True

    except Exception as exc:
        log.error("[odata] Build failed: %s", exc, exc_info=True)
    finally:
        with _lock:
            _building = False


def start() -> None:
    """Start background build if DB is missing or stale. Call once at app startup."""
    global _ready
    if DB_PATH.exists():
        age = time.time() - DB_PATH.stat().st_mtime
        if age < DB_MAX_AGE_DAYS * 86400:
            with _lock:
                _ready = True
            log.info("[odata] DB is fresh (%.0f days old).", age / 86400)
            return
        log.info("[odata] DB is stale (%.0f days old), rebuilding...", age / 86400)
    threading.Thread(target=_build_db, daemon=True, name="odata-build").start()


# ── Query ─────────────────────────────────────────────────────────────────────

def query(
    city_name: str,
    street: Optional[str] = None,
    neighborhood: Optional[str] = None,
    rooms: Optional[str] = None,
    property_type: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_area: Optional[float] = None,
    max_area: Optional[float] = None,
    min_year: Optional[int] = None,
    year: Optional[int] = None,
    max_items: int = 200,
) -> list:
    """
    Query local SQLite DB. Returns list of deal dicts matching fetch_deals() format.
    Returns [] if DB is not ready yet.
    """
    if not DB_PATH.exists():
        return []

    pattern = city_pattern(city_name)
    if not pattern:
        return []

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row

    clauses = ["city LIKE ?"]
    params: list = [pattern]

    if street:
        clauses.append("(street LIKE ? OR address LIKE ?)")
        params += [f"%{street}%", f"%{street}%"]
    if neighborhood:
        clauses.append("address LIKE ?")
        params.append(f"%{neighborhood}%")
    if year:
        clauses.append("year = ?")
        params.append(year)
    elif min_year:
        clauses.append("year >= ?")
        params.append(min_year)
    if min_price:
        clauses.append("price >= ?")
        params.append(min_price)
    if max_price:
        clauses.append("price <= ?")
        params.append(max_price)
    if min_area:
        clauses.append("area >= ?")
        params.append(min_area)
    if max_area:
        clauses.append("area <= ?")
        params.append(max_area)
    if property_type:
        clauses.append("dtype LIKE ?")
        params.append(f"%{property_type}%")

    # Rooms filter
    if rooms:
        if rooms.endswith("+"):
            try:
                clauses.append("CAST(rooms AS REAL) >= ?")
                params.append(float(rooms[:-1]))
            except ValueError:
                pass
        elif "-" in rooms:
            lo, hi = rooms.split("-", 1)
            try:
                clauses.append("CAST(rooms AS REAL) BETWEEN ? AND ?")
                params += [float(lo), float(hi)]
            except ValueError:
                pass
        else:
            try:
                clauses.append("CAST(rooms AS REAL) = ?")
                params.append(float(rooms))
            except ValueError:
                pass

    where = " AND ".join(clauses)
    sql = f"SELECT * FROM deals WHERE {where} ORDER BY date DESC LIMIT ?"
    params.append(max_items)

    rows = con.execute(sql, params).fetchall()
    con.close()

    return [
        {
            "dealDate":   r["date"],
            "address":    r["address"] or "",
            "dealAmount": r["price"] or 0,
            "roomNum":    r["rooms"] or "",
            "floor":      r["floor"] or "",
            "assetArea":  r["area"] or "",
            "dealNature": r["dtype"] or "",
        }
        for r in rows
    ]
