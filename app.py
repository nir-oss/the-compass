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
        try:
            row = conn.execute("SELECT id FROM sessions WHERE token=?", (token,)).fetchone()
        finally:
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
