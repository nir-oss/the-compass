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

    settlement = meta.get("settlement", "")
    if street and settlement:
        title = f"{street}, {settlement}"
    elif settlement:
        title = settlement
    else:
        title = street or "אזור"
    today     = date.today().isoformat()
    direction = trends.get("direction", "stable")
    total     = meta.get("total_deals", 0)

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
