# Nadlan AI Web App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing Nadlan Research System in a Flask web app with a Hebrew conversational chat UI, magic-link auth, SSE progress streaming, and an embedded report viewer.

**Architecture:** Flask app factory (`create_app`) with SQLite for users/sessions/magic-links/reports. Question parsing via Anthropic API (claude-haiku). research.py called as subprocess; progress streamed to client via SSE over fetch ReadableStream.

**Tech Stack:** Python 3.9, Flask, anthropic SDK, SQLite (stdlib), Jinja2, vanilla JS (no framework).

---

## File Map

| File | Status | Responsibility |
|------|--------|----------------|
| `db.py` | Create | SQLite schema + CRUD (users, magic_links, sessions, reports) |
| `app.py` | Create | Flask routes, SSE generator, question parsing, summary |
| `templates/base.html` | Create | Shared RTL layout, gradient theme |
| `templates/auth.html` | Create | Magic link landing / error |
| `templates/chat.html` | Create | Chat page (extends base) |
| `templates/report.html` | Create | Iframe wrapper with back-link |
| `templates/admin_login.html` | Create | Admin password form |
| `templates/admin.html` | Create | Create magic links, list clients |
| `static/style.css` | Create | Modern Warm gradient, RTL, all components |
| `static/chat.js` | Create | fetch SSE client, bubble rendering |
| `tests/test_db.py` | Create | Unit tests for all db functions |
| `tests/test_app.py` | Create | Flask test-client tests for all routes |
| `research.py` | Existing — no changes | Called as subprocess |
| `analyze.py` | Existing — no changes | — |
| `report.py` | Existing — no changes | — |

---

## Task 1: Install dependencies + db.py

**Files:**
- Create: `db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Install Flask and anthropic**

```bash
pip3 install flask anthropic
```

Expected: both install without errors.

- [ ] **Step 2: Write failing tests for db**

Create `tests/test_db.py`:

```python
import pytest
import db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


class TestInit:
    def test_creates_tables(self, tmp_db):
        conn = db.get_db()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert {"users", "magic_links", "sessions", "reports"} <= tables


class TestUsers:
    def test_create_user_returns_id(self, tmp_db):
        uid = db.create_user("רוני")
        assert isinstance(uid, int) and uid > 0

    def test_list_users_returns_all(self, tmp_db):
        db.create_user("א")
        db.create_user("ב")
        assert len(db.list_users()) == 2


class TestMagicLinks:
    def test_valid_link(self, tmp_db):
        uid = db.create_user("רוני")
        token = db.create_magic_link(uid)
        assert db.validate_magic_link(token) == uid

    def test_invalid_token(self, tmp_db):
        assert db.validate_magic_link("bad") is None

    def test_expired_link(self, tmp_db):
        uid = db.create_user("רוני")
        token = db.create_magic_link(uid, days=-1)
        assert db.validate_magic_link(token) is None


class TestSessions:
    def test_valid_session(self, tmp_db):
        uid = db.create_user("רוני")
        token = db.create_session(uid)
        assert db.validate_session(token) == uid

    def test_invalid_session(self, tmp_db):
        assert db.validate_session("bad") is None

    def test_expired_session(self, tmp_db):
        uid = db.create_user("רוני")
        token = db.create_session(uid, days=-1)
        assert db.validate_session(token) is None


class TestReports:
    def _session_id(self, tmp_db):
        uid = db.create_user("רוני")
        stok = db.create_session(uid)
        conn = db.get_db()
        sid = conn.execute(
            "SELECT id FROM sessions WHERE token=?", (stok,)
        ).fetchone()[0]
        conn.close()
        return sid

    def test_create_and_get_report(self, tmp_db):
        sid = self._session_id(tmp_db)
        rid = db.create_report(sid, "שאלה?", "תל אביב", "דיזנגוף")
        r = db.get_report(rid)
        assert r["question"] == "שאלה?"
        assert r["settlement"] == "תל אביב"

    def test_update_report(self, tmp_db):
        sid = self._session_id(tmp_db)
        rid = db.create_report(sid, "שאלה?", "תל אביב", "דיזנגוף")
        db.update_report(rid, "/output/report.html", "סיכום")
        r = db.get_report(rid)
        assert r["report_path"] == "/output/report.html"
        assert r["summary"] == "סיכום"

    def test_get_nonexistent_report(self, tmp_db):
        assert db.get_report(9999) is None
```

- [ ] **Step 3: Run to confirm tests fail**

```bash
cd "/Users/nirabas/Library/CloudStorage/Dropbox/2026/ClAUDE CODE/מאגר עסקאות שבוצעו"
python3 -m pytest tests/test_db.py -v 2>&1 | head -15
```

Expected: FAIL — `No module named 'db'`.

- [ ] **Step 4: Create db.py**

Create `db.py`:

```python
import sqlite3
import secrets
from datetime import datetime, timedelta

DB_PATH = "nadlan.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS magic_links (
            id INTEGER PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY,
            session_id INTEGER REFERENCES sessions(id),
            question TEXT NOT NULL,
            settlement TEXT,
            street TEXT,
            report_path TEXT,
            summary TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    db.commit()
    db.close()


def create_user(name):
    db = get_db()
    cur = db.execute("INSERT INTO users (name) VALUES (?)", (name,))
    uid = cur.lastrowid
    db.commit()
    db.close()
    return uid


def list_users():
    db = get_db()
    rows = db.execute("""
        SELECT u.id, u.name, u.created_at, MAX(ml.expires_at) AS link_expires
        FROM users u LEFT JOIN magic_links ml ON ml.user_id = u.id
        GROUP BY u.id ORDER BY u.created_at DESC
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]


def create_magic_link(user_id, days=7):
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(days=days)).isoformat()
    db = get_db()
    db.execute(
        "INSERT INTO magic_links (user_id, token, expires_at) VALUES (?, ?, ?)",
        (user_id, token, expires_at),
    )
    db.commit()
    db.close()
    return token


def validate_magic_link(token):
    db = get_db()
    row = db.execute(
        "SELECT user_id, expires_at FROM magic_links WHERE token=?", (token,)
    ).fetchone()
    db.close()
    if not row:
        return None
    if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
        return None
    return row["user_id"]


def create_session(user_id, days=7):
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(days=days)).isoformat()
    db = get_db()
    db.execute(
        "INSERT INTO sessions (user_id, token, expires_at) VALUES (?, ?, ?)",
        (user_id, token, expires_at),
    )
    db.commit()
    db.close()
    return token


def validate_session(token):
    if not token:
        return None
    db = get_db()
    row = db.execute(
        "SELECT user_id, expires_at FROM sessions WHERE token=?", (token,)
    ).fetchone()
    db.close()
    if not row:
        return None
    if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
        return None
    return row["user_id"]


def create_report(session_id, question, settlement, street):
    db = get_db()
    cur = db.execute(
        "INSERT INTO reports (session_id, question, settlement, street) VALUES (?, ?, ?, ?)",
        (session_id, question, settlement, street),
    )
    rid = cur.lastrowid
    db.commit()
    db.close()
    return rid


def update_report(report_id, report_path, summary):
    db = get_db()
    db.execute(
        "UPDATE reports SET report_path=?, summary=? WHERE id=?",
        (report_path, summary, report_id),
    )
    db.commit()
    db.close()


def get_report(report_id):
    db = get_db()
    row = db.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    db.close()
    return dict(row) if row else None
```

- [ ] **Step 5: Run tests — confirm all pass**

```bash
python3 -m pytest tests/test_db.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd "/Users/nirabas/Library/CloudStorage/Dropbox/2026/ClAUDE CODE/מאגר עסקאות שבוצעו"
git add db.py tests/test_db.py
git commit -m "feat: add db.py — SQLite layer for users, magic links, sessions, reports"
```

---

## Task 2: app.py — Flask routes + SSE + auth

**Files:**
- Create: `app.py`
- Create: `tests/test_app.py`

- [ ] **Step 1: Write failing route tests**

Create `tests/test_app.py`:

```python
import pytest
import db
from app import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    return create_app({"TESTING": True, "SECRET_KEY": "test-secret"})


@pytest.fixture
def client(app):
    return app.test_client()


def _login_client(client):
    """Create a user, get magic link, set session cookie."""
    uid = db.create_user("טסט")
    token = db.create_magic_link(uid)
    client.get(f"/auth/{token}", follow_redirects=False)
    return uid


class TestAuth:
    def test_valid_magic_link_redirects_to_chat(self, client):
        uid = db.create_user("רוני")
        token = db.create_magic_link(uid)
        resp = client.get(f"/auth/{token}")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/"

    def test_invalid_token_returns_401(self, client):
        resp = client.get("/auth/bad-token-xyz")
        assert resp.status_code == 401

    def test_chat_without_session_redirects(self, client):
        resp = client.get("/")
        assert resp.status_code == 302

    def test_chat_with_session_returns_200(self, client):
        _login_client(client)
        resp = client.get("/")
        assert resp.status_code == 200


class TestAdmin:
    def test_admin_requires_login(self, client):
        resp = client.get("/admin")
        assert resp.status_code == 302

    def test_admin_login_wrong_password(self, client):
        resp = client.post("/admin/login", data={"password": "wrong"})
        assert resp.status_code == 200
        assert b"error" in resp.data.lower() or b"שגויה" in resp.data

    def test_admin_login_correct_password(self, app, client):
        resp = client.post(
            "/admin/login",
            data={"password": app.config["ADMIN_PASSWORD"]},
        )
        assert resp.status_code == 302

    def test_create_link_returns_link(self, app, client):
        client.post(
            "/admin/login", data={"password": app.config["ADMIN_PASSWORD"]}
        )
        resp = client.post("/admin/create-link", data={"name": "רוני"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "link" in data and "auth/" in data["link"]


class TestAsk:
    def test_ask_without_session_redirects(self, client):
        resp = client.post("/ask", json={"question": "מה קורה?"})
        assert resp.status_code == 302

    def test_ask_empty_question_returns_400(self, client):
        _login_client(client)
        resp = client.post("/ask", json={"question": "  "})
        assert resp.status_code == 400


class TestReport:
    def test_report_404_for_unknown_id(self, client):
        _login_client(client)
        resp = client.get("/report/9999")
        assert resp.status_code == 404
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
python3 -m pytest tests/test_app.py -v 2>&1 | head -10
```

Expected: FAIL — `No module named 'app'`.

- [ ] **Step 3: Create app.py**

Create `app.py`:

```python
import glob
import json
import os
import subprocess
from functools import wraps
from pathlib import Path

from flask import (
    Flask, Response, abort, redirect, render_template,
    request, send_file, session, stream_with_context, url_for,
)
from anthropic import Anthropic

import db


def parse_question(question):
    """Extract settlement and street from Hebrew question via claude-haiku."""
    client = Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=120,
        messages=[{
            "role": "user",
            "content": (
                "חלץ מהשאלה שם יישוב ושם רחוב בישראל. "
                'החזר JSON בלבד: {"settlement":"...","street":"..." or null}\n\n'
                f"שאלה: {question}"
            ),
        }],
    )
    return json.loads(msg.content[0].text)


def generate_summary(stats, question):
    """3-4 sentence Hebrew answer to the user's question."""
    client = Anthropic()
    overall = stats.get("prices", {}).get("overall", {})
    meta = stats.get("meta", {})
    direction_heb = {"rising": "עולה", "falling": "יורדת", "stable": "יציבה"}.get(
        stats.get("trends", {}).get("direction", "stable"), "יציבה"
    )
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=280,
        messages=[{
            "role": "user",
            "content": (
                f'ענה בעברית (3-4 משפטים) על: "{question}"\n'
                f'נתונים: {meta.get("total_deals",0)} עסקאות, '
                f'ממוצע ₪{overall.get("mean",0):,.0f}, '
                f'ממוצע למ"ר ₪{overall.get("mean_per_sqm",0):,.0f}, '
                f'מגמה: {direction_heb}.'
            ),
        }],
    )
    return msg.content[0].text


def _sse(data):
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def run_research(question, session_id):
    """SSE generator: parse → fetch → analyze → summarize → done."""
    yield _sse({"step": "parsing", "text": "מזהה מיקום..."})
    try:
        parsed = parse_question(question)
    except Exception as e:
        yield _sse({"step": "error", "text": f"לא הצלחתי לזהות מיקום: {e}", "done": True})
        return

    settlement = parsed.get("settlement", "")
    street = parsed.get("street") or ""
    label = street or settlement

    if not settlement:
        yield _sse({"step": "error", "text": "לא זיהיתי עיר — נסה לציין עיר ספציפית.", "done": True})
        return

    yield _sse({"step": "parsed", "text": f"✓ זיהיתי: {settlement}{', ' + street if street else ''}"})

    report_id = db.create_report(session_id, question, settlement, street)

    cmd = ["python3", "research.py", "--settlement", settlement, "--limit", "150"]
    if street:
        cmd += ["--street", street]

    yield _sse({"step": "fetching", "text": "⟳ מושך עסקאות מנדל״ן.gov.il..."})

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8",
        )
        for line in proc.stdout:
            line = line.strip()
            if line and not line.startswith("  →"):
                yield _sse({"step": "progress", "text": line})
        proc.wait()
    except Exception as e:
        yield _sse({"step": "error", "text": f"שגיאה: {e}", "done": True})
        return

    if proc.returncode != 0:
        yield _sse({"step": "error", "text": "הרצת הניתוח נכשלה. נסה שוב.", "done": True})
        return

    yield _sse({"step": "analyzing", "text": "⟳ מנתח נתונים..."})

    # Find the most-recently generated HTML report
    html_files = sorted(
        glob.glob(f"output/report_{label}*.html"), key=os.path.getmtime, reverse=True
    )
    if not html_files:
        html_files = sorted(glob.glob("output/report_*.html"), key=os.path.getmtime, reverse=True)
    report_path = html_files[0] if html_files else None

    # Generate Hebrew summary from analysis JSON
    summary = ""
    analysis_path = Path(f"output/analysis_{label}.json")
    if analysis_path.exists():
        try:
            stats = json.loads(analysis_path.read_text(encoding="utf-8"))
            yield _sse({"step": "summarizing", "text": "⟳ מכין סיכום..."})
            summary = generate_summary(stats, question)
        except Exception:
            pass

    if report_path:
        db.update_report(report_id, report_path, summary)

    yield _sse({
        "step": "done", "text": "✓ הדוח מוכן",
        "report_id": report_id, "summary": summary, "done": True,
    })


def create_app(config=None):
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
    app.config["ADMIN_PASSWORD"] = os.environ.get("NADLAN_ADMIN_PASSWORD", "changeme")

    if config:
        app.config.update(config)

    db.init_db()

    def require_session(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            token = request.cookies.get("nadlan_session")
            user_id = db.validate_session(token)
            if not user_id:
                return redirect(url_for("chat"))  # will loop to auth_error
            return f(*args, user_id=user_id, **kwargs)
        return wrapped

    def require_admin(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not session.get("is_admin"):
                return redirect(url_for("admin_login"))
            return f(*args, **kwargs)
        return wrapped

    @app.route("/auth/<token>")
    def auth(token):
        user_id = db.validate_magic_link(token)
        if not user_id:
            return render_template("auth.html", error=True), 401
        session_token = db.create_session(user_id)
        resp = redirect("/")
        resp.set_cookie("nadlan_session", session_token, max_age=7 * 86400, httponly=True)
        return resp

    @app.route("/")
    def chat():
        token = request.cookies.get("nadlan_session")
        if not db.validate_session(token):
            return redirect(url_for("auth_error"))
        return render_template("chat.html")

    @app.route("/auth-error")
    def auth_error():
        return render_template("auth.html", error=True), 401

    @app.route("/ask", methods=["POST"])
    def ask():
        token = request.cookies.get("nadlan_session")
        user_id = db.validate_session(token)
        if not user_id:
            return redirect(url_for("auth_error"))

        data = request.get_json() or {}
        question = data.get("question", "").strip()
        if not question:
            return {"error": "שאלה ריקה"}, 400

        conn = db.get_db()
        row = conn.execute("SELECT id FROM sessions WHERE token=?", (token,)).fetchone()
        conn.close()
        session_id = row["id"] if row else None

        return Response(
            stream_with_context(run_research(question, session_id)),
            content_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.route("/report/<int:report_id>")
    def report_page(report_id):
        token = request.cookies.get("nadlan_session")
        if not db.validate_session(token):
            return redirect(url_for("auth_error"))
        report = db.get_report(report_id)
        if not report:
            abort(404)
        return render_template("report.html", report=report, report_id=report_id)

    @app.route("/report/<int:report_id>/file")
    def report_file(report_id):
        token = request.cookies.get("nadlan_session")
        if not db.validate_session(token):
            abort(401)
        report = db.get_report(report_id)
        if not report or not report.get("report_path"):
            abort(404)
        path = Path(report["report_path"])
        if not path.exists():
            abort(404)
        return send_file(str(path.resolve()), mimetype="text/html")

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            if request.form.get("password") == app.config["ADMIN_PASSWORD"]:
                session["is_admin"] = True
                return redirect(url_for("admin"))
            return render_template("admin_login.html", error=True)
        return render_template("admin_login.html")

    @app.route("/admin")
    @require_admin
    def admin():
        return render_template("admin.html", users=db.list_users(), base_url=request.host_url)

    @app.route("/admin/create-link", methods=["POST"])
    @require_admin
    def admin_create_link():
        name = (request.form.get("name") or "").strip()
        if not name:
            return {"error": "שם ריק"}, 400
        uid = db.create_user(name)
        token = db.create_magic_link(uid)
        return {"link": f"{request.host_url}auth/{token}", "name": name}

    return app


if __name__ == "__main__":
    create_app().run(debug=True, host="0.0.0.0", port=5000)
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_app.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add Flask app — auth, chat, SSE, report, admin routes"
```

---

## Task 3: Templates + CSS

**Files:**
- Create: `templates/base.html`
- Create: `templates/auth.html`
- Create: `templates/chat.html`
- Create: `templates/report.html`
- Create: `templates/admin_login.html`
- Create: `templates/admin.html`
- Create: `static/style.css`

- [ ] **Step 1: Create templates directory and base.html**

```bash
mkdir -p templates static
```

Create `templates/base.html`:

```html
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Nadlan AI{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
  {% block content %}{% endblock %}
  {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 2: Create auth.html and admin_login.html**

Create `templates/auth.html`:

```html
{% extends "base.html" %}
{% block content %}
<div class="auth-container">
  <div class="brand">Nadlan AI</div>
  {% if error %}
    <div class="auth-message error">
      הקישור אינו תקף או פג תוקף.<br>צור קשר עם ניר לקישור חדש.
    </div>
  {% else %}
    <div class="auth-message">מחבר אותך אוטומטית...</div>
  {% endif %}
</div>
{% endblock %}
```

Create `templates/admin_login.html`:

```html
{% extends "base.html" %}
{% block title %}אדמין — Nadlan AI{% endblock %}
{% block content %}
<div class="auth-container">
  <div class="brand">Nadlan AI — ניהול</div>
  <form method="POST" class="admin-form">
    <input type="password" name="password" placeholder="סיסמת מנהל" autofocus required>
    {% if error %}<div class="form-error">סיסמה שגויה</div>{% endif %}
    <button type="submit">כניסה</button>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 3: Create chat.html**

Create `templates/chat.html`:

```html
{% extends "base.html" %}
{% block title %}Nadlan AI{% endblock %}
{% block content %}
<div class="app-layout">
  <nav class="top-nav">
    <span class="brand-text">Nadlan AI</span>
  </nav>
  <div class="chat-container" id="chat-container">
    <div class="bubble bot">
      <div class="avatar bot-avatar">AI</div>
      <div class="message">שלום 👋 שאל אותי כל שאלה על שוק הנדל״ן בישראל — מחירים, מגמות, רחובות.</div>
    </div>
  </div>
  <div class="input-bar">
    <input type="text" id="question-input" placeholder="שאל שאלה..." autocomplete="off">
    <button id="send-btn" onclick="sendQuestion()">↑</button>
  </div>
</div>
{% endblock %}
{% block scripts %}
<script src="{{ url_for('static', filename='chat.js') }}"></script>
{% endblock %}
```

- [ ] **Step 4: Create report.html and admin.html**

Create `templates/report.html`:

```html
{% extends "base.html" %}
{% block title %}דוח — Nadlan AI{% endblock %}
{% block content %}
<div class="report-layout">
  <div class="report-nav">
    <a href="/" class="back-link">← חזרה לצ׳אט</a>
    <span class="report-title">{{ report.street or report.settlement or 'דוח' }}</span>
  </div>
  <iframe src="{{ url_for('report_file', report_id=report_id) }}" class="report-frame" title="דוח נדל״ן"></iframe>
</div>
{% endblock %}
```

Create `templates/admin.html`:

```html
{% extends "base.html" %}
{% block title %}ניהול — Nadlan AI{% endblock %}
{% block content %}
<div class="admin-layout">
  <h1 class="admin-title">ניהול לקוחות</h1>

  <div class="admin-card">
    <h2>יצירת קישור ללקוח חדש</h2>
    <form id="create-form" class="create-form" onsubmit="createLink(event)">
      <input type="text" id="client-name" placeholder="שם הלקוח" required>
      <button type="submit">✦ צור קישור</button>
    </form>
    <div id="link-result" class="link-result" style="display:none">
      <div class="link-label">קישור ללקוח (שלח ב-WhatsApp):</div>
      <div class="link-value" id="link-value"></div>
      <button onclick="copyLink()">העתק</button>
    </div>
  </div>

  <div class="admin-card">
    <h2>לקוחות פעילים</h2>
    <table class="admin-table">
      <tr><th>שם</th><th>תאריך הוספה</th><th>תפוגת קישור</th></tr>
      {% for u in users %}
      <tr>
        <td>{{ u.name }}</td>
        <td>{{ u.created_at[:10] }}</td>
        <td>{{ u.link_expires[:10] if u.link_expires else '—' }}</td>
      </tr>
      {% endfor %}
    </table>
  </div>
</div>
<script>
async function createLink(e) {
  e.preventDefault();
  const name = document.getElementById('client-name').value.trim();
  if (!name) return;
  const fd = new FormData();
  fd.append('name', name);
  const resp = await fetch('/admin/create-link', {method: 'POST', body: fd});
  const data = await resp.json();
  document.getElementById('link-value').textContent = data.link;
  document.getElementById('link-result').style.display = 'block';
  document.getElementById('client-name').value = '';
}
function copyLink() {
  navigator.clipboard.writeText(document.getElementById('link-value').textContent);
  alert('הקישור הועתק!');
}
</script>
{% endblock %}
```

- [ ] **Step 5: Create static/style.css**

Create `static/style.css`:

```css
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, 'Segoe UI', Arial, sans-serif;
  background: linear-gradient(135deg, #fff8f0 0%, #f0f4ff 100%);
  min-height: 100vh;
  color: #1a1a1a;
  direction: rtl;
}

.brand, .brand-text {
  font-weight: 800;
  background: linear-gradient(135deg, #e76f51, #457b9d);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* Auth */
.auth-container {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  min-height: 100vh; padding: 24px;
}
.auth-container .brand { font-size: 2em; margin-bottom: 24px; }
.auth-message {
  background: rgba(255,255,255,.9); border-radius: 12px;
  padding: 20px 32px; text-align: center;
  box-shadow: 0 4px 20px rgba(0,0,0,.08); line-height: 1.6;
}
.auth-message.error { border-right: 4px solid #e76f51; }

/* Chat layout */
.app-layout { display: flex; flex-direction: column; height: 100vh; }
.top-nav {
  padding: 12px 20px; background: rgba(255,255,255,.8);
  backdrop-filter: blur(8px); border-bottom: 1px solid rgba(0,0,0,.06);
  display: flex; align-items: center;
}
.top-nav .brand-text { font-size: 1.15em; }

.chat-container {
  flex: 1; overflow-y: auto; padding: 20px;
  display: flex; flex-direction: column; gap: 16px;
  max-width: 760px; width: 100%; margin: 0 auto;
}

.bubble { display: flex; gap: 10px; align-items: flex-start; max-width: 85%; }
.bubble.bot { flex-direction: row-reverse; align-self: flex-end; }
.bubble.user { align-self: flex-start; }

.avatar {
  width: 32px; height: 32px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; flex-shrink: 0; color: white;
}
.bot-avatar { background: linear-gradient(135deg, #457b9d, #2a9d8f); }
.user-avatar { background: #e76f51; }

.message {
  background: rgba(255,255,255,.95); border: 1px solid rgba(0,0,0,.07);
  padding: 10px 14px; border-radius: 12px 12px 12px 2px;
  font-size: .93em; line-height: 1.6; box-shadow: 0 2px 8px rgba(0,0,0,.05);
}
.bubble.user .message {
  background: linear-gradient(135deg, #457b9d, #2a9d8f);
  color: white; border: none; border-radius: 12px 12px 2px 12px;
}

/* SSE step colours */
.message .parsed   { color: #2a9d8f; display: block; }
.message .fetching,
.message .progress  { color: #457b9d; display: block; }
.message .analyzing,
.message .summarizing { color: #888; display: block; }
.message .error-text  { color: #e76f51; }

.report-btn {
  display: inline-block; margin-top: 8px;
  background: linear-gradient(135deg, #457b9d, #2a9d8f);
  color: white !important; padding: 6px 16px;
  border-radius: 20px; text-decoration: none;
  font-size: .88em; font-weight: 600;
}

/* Input bar */
.input-bar {
  padding: 12px 20px; background: rgba(255,255,255,.8);
  backdrop-filter: blur(8px); border-top: 1px solid rgba(0,0,0,.06);
  display: flex; gap: 10px;
  max-width: 760px; width: 100%; margin: 0 auto;
}
#question-input {
  flex: 1; border: none; background: rgba(255,255,255,.9);
  border-radius: 24px; padding: 10px 18px;
  font-size: .95em; outline: none;
  box-shadow: 0 2px 8px rgba(0,0,0,.08);
  direction: rtl; text-align: right; font-family: inherit;
}
#send-btn {
  width: 42px; height: 42px; border-radius: 50%;
  border: none; background: linear-gradient(135deg, #457b9d, #2a9d8f);
  color: white; font-size: 1.2em; cursor: pointer;
  box-shadow: 0 2px 8px rgba(69,123,157,.3); transition: opacity .2s;
}
#send-btn:disabled { opacity: .5; cursor: not-allowed; }

/* Report */
.report-layout { display: flex; flex-direction: column; height: 100vh; }
.report-nav {
  padding: 12px 20px; background: rgba(255,255,255,.9);
  backdrop-filter: blur(8px); border-bottom: 1px solid rgba(0,0,0,.06);
  display: flex; align-items: center; gap: 16px;
}
.back-link { color: #457b9d; text-decoration: none; font-size: .9em; font-weight: 600; }
.report-title { font-weight: 700; color: #1d3557; }
.report-frame { flex: 1; border: none; width: 100%; }

/* Admin */
.admin-layout { max-width: 680px; margin: 40px auto; padding: 20px; }
.admin-title {
  font-size: 1.6em; font-weight: 800; margin-bottom: 24px;
  background: linear-gradient(135deg, #e76f51, #457b9d);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.admin-card {
  background: rgba(255,255,255,.9); border-radius: 12px;
  padding: 20px 24px; margin-bottom: 20px;
  box-shadow: 0 2px 12px rgba(0,0,0,.06);
}
.admin-card h2 { font-size: 1em; color: #1d3557; margin-bottom: 14px; }
.create-form { display: flex; gap: 10px; margin-bottom: 14px; }
.create-form input {
  flex: 1; border: 1.5px solid #e0e0e0; border-radius: 8px;
  padding: 8px 14px; font-size: .95em; direction: rtl; outline: none;
}
.create-form input:focus { border-color: #457b9d; }
.create-form button, .admin-form button {
  background: linear-gradient(135deg, #457b9d, #2a9d8f);
  color: white; border: none; border-radius: 8px;
  padding: 8px 18px; font-size: .9em; cursor: pointer; white-space: nowrap;
}
.link-result { background: #eaf2fb; border-radius: 8px; padding: 12px 14px; margin-top: 10px; }
.link-label { font-size: .82em; color: #666; margin-bottom: 6px; }
.link-value { font-size: .88em; color: #457b9d; word-break: break-all; margin-bottom: 8px; }
.link-result button {
  background: #457b9d; color: white; border: none;
  border-radius: 6px; padding: 5px 14px; font-size: .85em; cursor: pointer;
}
.admin-table { width: 100%; border-collapse: collapse; font-size: .9em; }
.admin-table th { background: #1d3557; color: white; padding: 8px 12px; text-align: right; }
.admin-table td { padding: 8px 12px; border-bottom: 1px solid #f0f0f0; }
.admin-form { display: flex; flex-direction: column; gap: 10px; width: 280px; }
.admin-form input {
  border: 1.5px solid #e0e0e0; border-radius: 8px;
  padding: 10px 14px; font-size: .95em; direction: rtl; outline: none;
}
.form-error { color: #e76f51; font-size: .88em; }
```

- [ ] **Step 6: Verify templates render with test client**

```bash
python3 -m pytest tests/test_app.py::TestAuth::test_chat_with_session_returns_200 -v
```

Expected: PASS — confirms Jinja2 finds `chat.html`.

- [ ] **Step 7: Commit**

```bash
git add templates/ static/style.css
git commit -m "feat: add all templates and Modern Warm CSS"
```

---

## Task 4: chat.js — SSE client

**Files:**
- Create: `static/chat.js`

- [ ] **Step 1: Create static/chat.js**

Create `static/chat.js`:

```javascript
function appendBubble(role, content) {
  const container = document.getElementById('chat-container');
  const div = document.createElement('div');
  div.className = `bubble ${role}`;

  const avatar = document.createElement('div');
  avatar.className = `avatar ${role}-avatar`;
  avatar.textContent = role === 'bot' ? 'AI' : 'א';

  const msg = document.createElement('div');
  msg.className = 'message';
  msg.innerHTML = content;

  div.appendChild(avatar);
  div.appendChild(msg);
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

function handleEvent(event, bubble) {
  const msgEl = bubble.querySelector('.message');

  if (event.step === 'error') {
    msgEl.innerHTML = `<span class="error-text">${event.text}</span>`;
    return;
  }

  if (event.done) {
    let html = '';
    if (event.summary) {
      html += `<p style="margin-bottom:8px">${event.summary}</p>`;
    }
    if (event.report_id) {
      html += `<a href="/report/${event.report_id}" class="report-btn">📊 פתח דוח מלא</a>`;
    }
    msgEl.innerHTML = html || event.text;
    return;
  }

  // Append progress line
  const existing = msgEl.innerHTML;
  const line = `<span class="${event.step}">${event.text}</span>`;
  msgEl.innerHTML = existing ? existing + '\n' + line : line;
  bubble.parentElement.scrollTop = bubble.parentElement.scrollHeight;
}

async function sendQuestion() {
  const input = document.getElementById('question-input');
  const question = input.value.trim();
  if (!question) return;

  input.value = '';
  input.disabled = true;
  document.getElementById('send-btn').disabled = true;

  appendBubble('user', question);
  const botBubble = appendBubble('bot', '');

  try {
    const resp = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });

    if (!resp.ok) {
      botBubble.querySelector('.message').innerHTML =
        '<span class="error-text">שגיאה — נסה שוב</span>';
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            handleEvent(JSON.parse(line.slice(6)), botBubble);
          } catch (_) {}
        }
      }
    }
  } catch (e) {
    botBubble.querySelector('.message').innerHTML =
      '<span class="error-text">שגיאת חיבור — נסה שוב</span>';
  } finally {
    input.disabled = false;
    document.getElementById('send-btn').disabled = false;
    input.focus();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('question-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendQuestion();
    }
  });
});
```

- [ ] **Step 2: Verify JS is served correctly**

```bash
python3 -c "
from app import create_app
app = create_app({'TESTING': True, 'SECRET_KEY': 'x'})
with app.test_client() as c:
    resp = c.get('/static/chat.js')
    assert resp.status_code == 200, resp.status_code
    print('chat.js OK')
"
```

Expected: `chat.js OK`.

- [ ] **Step 3: Commit**

```bash
git add static/chat.js
git commit -m "feat: add chat.js — fetch SSE client with bubble rendering"
```

---

## Task 5: Full test suite + integration validation

**Files:** No new files — validation only.

- [ ] **Step 1: Run full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests PASS (db + app tests, ~23 total).

- [ ] **Step 2: Set required environment variables**

```bash
export ANTHROPIC_API_KEY="your-key-here"
export NADLAN_ADMIN_PASSWORD="yourpassword"
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
```

- [ ] **Step 3: Start the server**

```bash
python3 app.py
```

Expected output: `* Running on http://0.0.0.0:5000`

- [ ] **Step 4: Create a magic link via admin**

```
1. Open http://localhost:5000/admin/login
2. Enter your NADLAN_ADMIN_PASSWORD
3. Enter a client name → click "צור קישור"
4. Copy the generated link
```

- [ ] **Step 5: Test the full user flow**

```
1. Open the magic link in a new browser tab
2. Confirm auto-redirect to chat page
3. Type: "מה המחיר הממוצע ברחוב דיזנגוף בתל אביב?"
4. Confirm SSE progress appears live in the chat bubble
5. Confirm "פתח דוח מלא" button appears when done
6. Click it — confirm report opens with all fields:
   date, address, price, price/sqm, rooms, floor, area, type, year built, neighborhood
```

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "feat: Nadlan AI web app complete — chat UI, magic link auth, SSE, report viewer"
```

---

## Self-Review Notes

**Spec coverage:**
- ✅ Conversational chat UI (Hebrew RTL, Modern Warm style)
- ✅ Magic link auth (7-day expiry, SQLite-backed)
- ✅ SSE progress streaming during research
- ✅ Report opens in new page within site (iframe in report.html)
- ✅ Admin: create links, list clients
- ✅ Question parsing via Anthropic API (claude-haiku)
- ✅ Hebrew summary after analysis
- ✅ Detailed report table: date, address, price, price/sqm, rooms, floor, area, type, year built, neighborhood (rendered by existing report.py)
- ✅ Error handling: invalid link, empty question, subprocess failure

**No placeholders:** All code blocks are complete and runnable.

**Type consistency:** `db.get_report()` returns `dict` with keys `report_path`, `settlement`, `street` — used correctly in `report_page` route and `report.html` template.
