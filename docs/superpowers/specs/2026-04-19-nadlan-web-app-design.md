# Nadlan AI Web App — Design Spec

**Date:** 2026-04-19  
**Status:** Approved  
**Scope:** Phase 2 — Web interface for the Nadlan Research System

---

## Goal

A private web application that wraps the existing Nadlan Research System (research.py, analyze.py, report.py) in a conversational AI interface. Clients receive a magic link, type a free-form Hebrew question, and receive real transaction data and a detailed HTML report — all inside the browser.

---

## Architecture

```
Client browser
      ↓
Flask app (app.py)
      ├── Auth: magic link → SQLite session
      ├── GET /          → chat page (templates/chat.html)
      ├── POST /ask      → runs research.py → SSE progress stream
      ├── GET /report/<id> → serves generated HTML report
      └── GET /admin     → magic link management (Nir only)
            ↓
      db.py (SQLite)
      users, magic_links, sessions, reports
            ↓
      research.py → analyze.py → report.py (existing)
```

### Files

| File | Status | Responsibility |
|------|--------|----------------|
| `app.py` | Create | Flask routes, SSE streaming, session handling |
| `db.py` | Create | SQLite: init schema, CRUD for users/links/sessions/reports |
| `templates/base.html` | Create | Shared layout: nav, RTL CSS, gradient theme |
| `templates/auth.html` | Create | Magic link landing page |
| `templates/chat.html` | Create | Chat UI + SSE event listener |
| `templates/report.html` | Create | Report page wrapper with back-to-chat nav |
| `templates/admin.html` | Create | Create magic links, list active clients |
| `static/chat.js` | Create | SSE client, chat rendering, submit handler |
| `static/style.css` | Create | Global styles, Modern Warm theme, RTL |
| `research.py` | Existing — no changes | CLI orchestrator (called as subprocess) |
| `analyze.py` | Existing — no changes | Statistics |
| `report.py` | Existing — no changes | HTML report generator |

---

## Visual Design

**Style:** Modern Warm — gradient (teal→blue), rounded corners, white card bubbles on light gradient background. Hebrew RTL throughout.

**Color palette:**
- Primary gradient: `#457b9d` → `#2a9d8f`
- Accent: `#e76f51`
- Background: `linear-gradient(135deg, #fff8f0, #f0f4ff)`
- Text: `#1a1a1a`
- Cards: `rgba(255,255,255,0.95)` with subtle shadow

---

## Pages

### 1. Auth (`/auth/<token>`)

- Validates token against `magic_links` table
- If valid and not expired (7 days): creates session, redirects to `/`
- If invalid/expired: shows error with contact message
- Auto-redirect after 1.5s with "כניסה אוטומטית..." indicator

### 2. Chat (`/`)

Requires valid session. Renders:
- Top nav: logo "Nadlan AI" (gradient text) + client name
- Chat history (stored in `reports` table per session)
- Input bar with rounded send button
- On submit: POST `/ask` → open SSE stream → render progress steps live

**SSE progress steps (streamed to client):**
1. `✓ זיהיתי: {settlement}, {street}`
2. `⟳ מושך עסקאות מנדל״ן.gov.il...`
3. `✓ נמצאו {N} עסקאות`
4. `⟳ מנתח נתונים...`
5. `✓ הדוח מוכן` + link to `/report/<id>`

**AI summary bubble:** After SSE completes, displays 3–4 sentence Hebrew summary (read from `analysis_{street}.json`) with a "📊 פתח דוח מלא" button.

### 3. Report (`/report/<id>`)

- Back-to-chat link at top
- Renders the generated HTML report inline (served from `output/` directory)
- Report content (from report.py) includes all fields:
  - Header: title, date, period, total deals
  - Executive summary (Hebrew, auto-generated)
  - Price stats: mean, median, per sqm, by rooms
  - Trend chart (CSS bar chart, quarterly)
  - **Detailed transactions table:** date | address | price | price/sqm | rooms | floor | area (sqm) | property type | year built | neighborhood
  - Outliers section (if any)

### 4. Admin (`/admin`)

Protected by `ADMIN_PASSWORD` environment variable. Separate login form at `/admin/login` — sets a distinct `admin_session` cookie valid for 24h.

- Form: client name → generate magic link
- Displays generated link for copy (Nir sends via WhatsApp)
- Table: active clients with name + link expiry date
- No analytics or history — purely link management

---

## Data Model (SQLite)

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE magic_links (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    token TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    token TEXT UNIQUE NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

CREATE TABLE reports (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id),
    question TEXT NOT NULL,
    settlement TEXT,
    street TEXT,
    report_path TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

---

## Auth Flow

1. Nir opens `/admin`, enters client name → system generates UUID token → stores in `magic_links` (expires 7 days)
2. Nir copies link (`https://yourdomain/auth/<token>`) → sends via WhatsApp
3. Client clicks link → `/auth/<token>` validates → creates session cookie (7-day expiry) → redirects to `/`
4. All subsequent requests check session cookie → 401 redirect to error page if missing/expired

---

## SSE Implementation

`POST /ask` accepts `{question: string}` JSON. Server:
1. Parses Hebrew question: calls Anthropic API (`claude-haiku-4-5`) with a short system prompt to extract `settlement` and `street` as JSON — e.g. `{"settlement": "תל אביב", "street": "דיזנגוף"}`. Falls back to asking user if ambiguous.
2. Runs `research.py --settlement X --street Y` as subprocess, captures stdout line by line
3. Yields each stdout line as SSE event: `data: {"step": "...", "done": false}`
4. On completion: yields `data: {"step": "done", "report_id": <id>, "summary": "...", "done": true}`

Client (`chat.js`) listens to EventSource, renders each step live in the AI bubble.

---

## Hosting

- **Server:** DigitalOcean Droplet ($6/month, Ubuntu 22.04)
- **Process manager:** systemd or gunicorn
- **Playwright:** runs server-side with `headless=False` requires display → use Xvfb virtual display
- **HTTPS:** Caddy reverse proxy (auto TLS via Let's Encrypt)
- **Domain:** configured by user (e.g., `nadlan.yourname.com`)

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Magic link expired | Error page: "הקישור פג תוקף — צור קשר עם ניר" |
| reCAPTCHA token fails | SSE error event: "נכשל בחיבור לנדל״ן.gov.il — נסה שוב" |
| No deals found | Report with warning banner, summary mentions data limitation |
| Settlement not found | SSE error: "לא מצאתי את הישוב — נסה שם אחר" |
| Server error | Generic Hebrew error in chat bubble |

---

## Out of Scope (Phase 2)

- Email delivery of magic links (Nir sends manually via WhatsApp)
- Multi-language support
- PDF export
- Mobile app
- Saved searches / alerts
- Payment / subscription
