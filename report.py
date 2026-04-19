"""
report.py — Generate a self-contained Hebrew HTML report from analyze() output.
Uses Chart.js (CDN) for interactive charts. Brand: ivory/gold/navy (המצפן).
"""

import json
import re
from datetime import date
from pathlib import Path


def _fmt_price(n):
    if not n:
        return "—"
    return "₪{:,}".format(int(n))


def _trend_cfg(direction):
    return {
        "rising":  {"color": "#2a9d8f", "label": "עולה ↑"},
        "falling": {"color": "#e76f51", "label": "יורדת ↓"},
        "stable":  {"color": "#457b9d", "label": "יציבה →"},
    }.get(direction, {"color": "#888", "label": direction})


def _rooms_table_rows(by_rooms):
    rows = ""
    for key in sorted(by_rooms.keys()):
        r = by_rooms[key]
        if r.get("count", 0) == 0:
            continue
        rows += (
            f"<tr>"
            f"<td>{key} חדרים</td>"
            f"<td class='num'>{r['count']}</td>"
            f"<td class='num'>{_fmt_price(r.get('mean'))}</td>"
            f"<td class='num'>{_fmt_price(r.get('mean_per_sqm'))}</td>"
            f"</tr>"
        )
    return rows


def _recent_rows(recent):
    rows = ""
    for d in recent[:15]:
        rows += (
            f"<tr>"
            f"<td>{(d.get('dealDate') or '')[:10]}</td>"
            f"<td>{d.get('address','')}</td>"
            f"<td class='num gold'>{_fmt_price(d.get('dealAmount'))}</td>"
            f"<td class='num'>{int(d.get('assetArea') or 0) or '—'}</td>"
            f"<td class='num'>{int(d.get('roomNum') or 0) or '—'}</td>"
            f"<td>{d.get('floor','')}</td>"
            f"<td>{d.get('dealNature','')}</td>"
            f"</tr>"
        )
    return rows


def _outliers_section(outliers):
    if not outliers:
        return ""
    rows = ""
    for d in outliers[:6]:
        direction_label = "גבוה" if d.get("_outlier_direction") == "high" else "נמוך"
        pct = d.get("_outlier_pct", "")
        badge_color = "#2a9d8f" if direction_label == "גבוה" else "#e76f51"
        rows += (
            f"<tr>"
            f"<td>{d.get('address','')}</td>"
            f"<td class='num gold'>{_fmt_price(d.get('dealAmount'))}</td>"
            f"<td class='num'>{_fmt_price(d.get('priceSM'))}</td>"
            f"<td><span class='badge' style='background:{badge_color}'>{direction_label} ב-{pct}%</span></td>"
            f"</tr>"
        )
    return f"""
    <div class="card">
      <div class="card-header">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        <h2>עסקאות חריגות</h2>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>כתובת</th><th>מחיר</th><th>מחיר למ"ר</th><th>חריגה</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>"""


_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Frank+Ruhl+Libre:wght@400;700;900&family=Heebo:wght@300;400;500;600;700&display=swap');

:root {
  --bg:      #f7f4ef;
  --bg2:     #ffffff;
  --bg3:     #f0ece4;
  --navy:    #0d1b2a;
  --navy2:   #1d3557;
  --gold:    #b8963e;
  --gold-lt: #c9a452;
  --gold-d:  rgba(184,150,62,.10);
  --gold-r:  rgba(184,150,62,.22);
  --text:    #1a1614;
  --dim:     rgba(26,22,20,.45);
  --border:  rgba(26,22,20,.08);
  --red:     #e76f51;
  --green:   #2a9d8f;
  --radius:  14px;
  --shadow:  0 4px 24px rgba(13,27,42,.08);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Heebo', -apple-system, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  direction: rtl;
  -webkit-font-smoothing: antialiased;
}

.container { max-width: 960px; margin: 0 auto; padding: 28px 20px 48px; }

/* ── Header ── */
.header {
  background: var(--navy);
  color: #f7f4ef;
  padding: 32px 36px;
  border-radius: var(--radius);
  margin-bottom: 24px;
  position: relative;
  overflow: hidden;
}
.header::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at 80% 50%, rgba(184,150,62,.12) 0%, transparent 60%);
  pointer-events: none;
}
.header-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
  opacity: .7;
}
.header-brand-name {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: .85rem;
  letter-spacing: 3px;
  text-transform: uppercase;
  color: var(--gold-lt);
}
.header h1 {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: clamp(1.4rem, 4vw, 2rem);
  font-weight: 700;
  margin-bottom: 10px;
  line-height: 1.2;
}
.header-meta {
  font-size: .82rem;
  opacity: .65;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
}
.header-meta span { display: flex; align-items: center; gap: 5px; }

/* ── Cards ── */
.card {
  background: var(--bg2);
  border-radius: var(--radius);
  padding: 24px;
  margin-bottom: 20px;
  box-shadow: var(--shadow);
  border: 1px solid var(--border);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}
.card-header svg { color: var(--gold); flex-shrink: 0; }
.card-header h2 {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--navy);
}

/* ── Summary ── */
.summary-box {
  background: var(--bg3);
  padding: 18px 22px;
  border-radius: 10px;
  border-right: 3px solid var(--gold-r);
  line-height: 1.85;
  font-size: .95rem;
  color: var(--text);
}
.trend-badge {
  display: inline-block;
  padding: 3px 12px;
  border-radius: 20px;
  font-size: .82em;
  font-weight: 600;
  margin-right: 8px;
  color: #fff;
}

/* ── Stat grid ── */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 22px;
}
.stat {
  background: var(--bg3);
  border: 1px solid var(--border);
  padding: 16px 18px;
  border-radius: 10px;
  transition: box-shadow .2s;
}
.stat:hover { box-shadow: 0 2px 12px rgba(184,150,62,.12); }
.stat .lbl {
  font-size: .75rem;
  color: var(--dim);
  font-weight: 500;
  margin-bottom: 6px;
  letter-spacing: .3px;
}
.stat .val {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--navy);
  font-family: 'Frank Ruhl Libre', serif;
}

/* ── Charts ── */
.chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 4px;
}
.chart-wrap {
  background: var(--bg3);
  border-radius: 10px;
  padding: 16px;
  position: relative;
  height: 220px;
}
.chart-wrap canvas { max-height: 188px; }
.chart-label {
  font-size: .75rem;
  font-weight: 600;
  color: var(--dim);
  margin-bottom: 10px;
  text-align: center;
  letter-spacing: .5px;
  text-transform: uppercase;
}
@media (max-width: 600px) {
  .chart-grid { grid-template-columns: 1fr; }
  .chart-wrap { height: 200px; }
}

/* ── Tables ── */
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .88rem; }
thead th {
  background: var(--navy);
  color: #f7f4ef;
  padding: 10px 14px;
  font-weight: 600;
  font-size: .8rem;
  letter-spacing: .3px;
  text-align: right;
  white-space: nowrap;
}
tbody td {
  padding: 9px 14px;
  border-bottom: 1px solid var(--border);
  color: var(--text);
}
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: var(--gold-d); }
.num { text-align: left; font-variant-numeric: tabular-nums; }
.gold { color: var(--gold); font-weight: 700; }

/* ── Badge ── */
.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: .78em;
  font-weight: 600;
  color: #fff;
}
"""


def generate_html(stats, output_dir="output", street=None):
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    meta     = stats.get("meta", {})
    prices   = stats.get("prices", {})
    overall  = prices.get("overall", {})
    trends   = stats.get("trends", {})
    by_rooms = prices.get("by_rooms", {})

    settlement = meta.get("settlement", "")
    title = f"{street}, {settlement}" if (street and settlement) else (settlement or street or "אזור")
    today     = date.today().isoformat()
    direction = trends.get("direction", "stable")
    total     = meta.get("total_deals", 0)
    trend_cfg = _trend_cfg(direction)

    if total == 0:
        summary_text = "לא נמצאו עסקאות לתקופה זו."
    else:
        summary_text = (
            f"נבדקו <strong>{total}</strong> עסקאות בתקופה "
            f"{meta.get('period_from','')} עד {meta.get('period_to','')}. "
            f"מחיר ממוצע: <strong>{_fmt_price(overall.get('mean'))}</strong>, "
            f"ממוצע למ\"ר: <strong>{_fmt_price(overall.get('mean_per_sqm'))}</strong>."
        )

    # Quarterly chart data
    quarters = trends.get("by_quarter", [])
    q_labels     = json.dumps([q["label"] for q in quarters], ensure_ascii=False)
    q_counts     = json.dumps([q["count"] for q in quarters])
    q_prices     = json.dumps([round(q["mean_price"] / 1000) for q in quarters])  # in K

    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>ניתוח עסקאות — {title}</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div class="header-brand">
      <svg viewBox="0 0 120 120" width="22" height="22" xmlns="http://www.w3.org/2000/svg">
        <circle cx="60" cy="60" r="56" fill="none" stroke="rgba(184,150,62,.5)" stroke-width="2"/>
        <polygon points="60,16 56.5,64 63.5,64" fill="#b8963e"/>
        <polygon points="60,104 56.5,64 63.5,64" fill="rgba(184,150,62,.3)"/>
        <circle cx="60" cy="60" r="6" fill="#b8963e"/>
        <circle cx="60" cy="60" r="2.5" fill="#f7f4ef"/>
      </svg>
      <span class="header-brand-name">המצפן · by Target</span>
    </div>
    <h1>ניתוח עסקאות — {title}</h1>
    <div class="header-meta">
      <span>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
        הופק: {today}
      </span>
      <span>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        תקופה: {meta.get('period_from','')} — {meta.get('period_to','')}
      </span>
      <span>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>
        {total} עסקאות
      </span>
    </div>
  </div>

  <!-- Summary -->
  <div class="card">
    <div class="card-header">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      <h2>סיכום מנהלים</h2>
    </div>
    <div class="summary-box">
      {summary_text}
      &nbsp;
      <span class="trend-badge" style="background:{trend_cfg['color']}">{trend_cfg['label']}</span>
    </div>
  </div>

  <!-- Price stats -->
  <div class="card">
    <div class="card-header">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>
      <h2>נתוני מחירים</h2>
    </div>
    <div class="stat-grid">
      <div class="stat"><div class="lbl">ממוצע מחיר</div><div class="val">{_fmt_price(overall.get('mean'))}</div></div>
      <div class="stat"><div class="lbl">חציון מחיר</div><div class="val">{_fmt_price(overall.get('median'))}</div></div>
      <div class="stat"><div class="lbl">ממוצע למ"ר</div><div class="val">{_fmt_price(overall.get('mean_per_sqm'))}</div></div>
      <div class="stat"><div class="lbl">חציון למ"ר</div><div class="val">{_fmt_price(overall.get('median_per_sqm'))}</div></div>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>חדרים</th><th>עסקאות</th><th>ממוצע מחיר</th><th>ממוצע למ"ר</th></tr></thead>
        <tbody>{_rooms_table_rows(by_rooms)}</tbody>
      </table>
    </div>
  </div>

  <!-- Charts -->
  <div class="card">
    <div class="card-header">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
      <h2>מגמות רבעוניות</h2>
    </div>
    <div class="chart-grid">
      <div class="chart-wrap">
        <div class="chart-label">נפח עסקאות</div>
        <canvas id="chartVolume"></canvas>
      </div>
      <div class="chart-wrap">
        <div class="chart-label">מחיר ממוצע (אלפי ₪)</div>
        <canvas id="chartPrice"></canvas>
      </div>
    </div>
  </div>

  <!-- Recent transactions -->
  <div class="card">
    <div class="card-header">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
      <h2>עסקאות אחרונות</h2>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>תאריך</th><th>כתובת</th><th>מחיר</th><th>מ"ר</th><th>חדרים</th><th>קומה</th><th>סוג</th></tr></thead>
        <tbody>{_recent_rows(stats.get('recent', []))}</tbody>
      </table>
    </div>
  </div>

  {_outliers_section(stats.get('outliers', []))}

</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
const GOLD = '#b8963e';
const NAVY = '#0d1b2a';
const GOLD_FILL = 'rgba(184,150,62,0.12)';
const NAVY_FILL = 'rgba(13,27,42,0.08)';

const baseFont = {{ family: "'Heebo', sans-serif", size: 11 }};
const gridColor = 'rgba(26,22,20,0.06)';

const sharedOptions = {{
  responsive: true,
  maintainAspectRatio: false,
  plugins: {{
    legend: {{ display: false }},
    tooltip: {{
      rtl: true,
      bodyFont: baseFont,
      titleFont: {{ ...baseFont, weight: '600' }},
      backgroundColor: NAVY,
      titleColor: '#f7f4ef',
      bodyColor: 'rgba(247,244,239,0.8)',
      padding: 10,
      cornerRadius: 8,
      displayColors: false,
    }},
  }},
  scales: {{
    x: {{
      ticks: {{ font: baseFont, color: 'rgba(26,22,20,0.45)', maxRotation: 45 }},
      grid: {{ color: gridColor }},
      border: {{ color: gridColor }},
    }},
    y: {{
      ticks: {{ font: baseFont, color: 'rgba(26,22,20,0.45)' }},
      grid: {{ color: gridColor }},
      border: {{ display: false }},
      beginAtZero: true,
    }},
  }},
}};

const labels = {q_labels};
const counts = {q_counts};
const prices = {q_prices};

// Volume bar chart
new Chart(document.getElementById('chartVolume'), {{
  type: 'bar',
  data: {{
    labels,
    datasets: [{{
      data: counts,
      backgroundColor: labels.map((_, i) =>
        i === counts.indexOf(Math.max(...counts)) ? GOLD : 'rgba(184,150,62,0.35)'
      ),
      borderColor: GOLD,
      borderWidth: 1.5,
      borderRadius: 5,
      borderSkipped: false,
    }}],
  }},
  options: {{
    ...sharedOptions,
    plugins: {{
      ...sharedOptions.plugins,
      tooltip: {{
        ...sharedOptions.plugins.tooltip,
        callbacks: {{
          label: ctx => ` ${{ctx.parsed.y}} עסקאות`,
        }},
      }},
    }},
  }},
}});

// Price line chart
new Chart(document.getElementById('chartPrice'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [{{
      data: prices,
      borderColor: NAVY,
      borderWidth: 2.5,
      pointBackgroundColor: GOLD,
      pointBorderColor: '#fff',
      pointBorderWidth: 2,
      pointRadius: 4,
      pointHoverRadius: 6,
      fill: true,
      backgroundColor: GOLD_FILL,
      tension: 0.4,
    }}],
  }},
  options: {{
    ...sharedOptions,
    plugins: {{
      ...sharedOptions.plugins,
      tooltip: {{
        ...sharedOptions.plugins.tooltip,
        callbacks: {{
          label: ctx => ` ₪${{(ctx.parsed.y).toLocaleString('he-IL')}}K`,
        }},
      }},
    }},
  }},
}});
</script>
</body>
</html>"""

    safe_name = re.sub(r"[^\w\u0590-\u05FF]", "_", title)
    out_path  = Path(output_dir) / f"report_{safe_name}_{today}.html"
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)
