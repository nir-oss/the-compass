import glob
import json
import os
import subprocess
import warnings
import urllib3
from pathlib import Path

# Load .env file if present
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())
from functools import wraps
from pathlib import Path

warnings.filterwarnings("ignore", category=urllib3.exceptions.NotOpenSSLWarning)

from flask import (
    Flask, Response, abort, redirect, render_template,
    request, send_file, session, stream_with_context, url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from anthropic import Anthropic

import threading

import db

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", str(Path(__file__).parent / "output"))
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

limiter = Limiter(key_func=get_remote_address, default_limits=[])

_research_lock = threading.Semaphore(1)


def parse_refinement(answer, settlement):
    """Parse user's clarification answer: extract street/neighborhood and optional property params."""
    client = Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        messages=[{
            "role": "user",
            "content": (
                f"המשתמש חיפש נדל\"ן ב{settlement} ואמר: '{answer}'\n"
                "חלץ: רחוב, שכונה/רובע, חדרים, סוג נכס. "
                "אם רוצה כל העיר ('הכל', 'כל העיר') — street=null, neighborhood=null.\n"
                "החזר JSON בלבד:\n"
                "{\"street\":\"...\",\"neighborhood\":\"...\","
                "\"rooms\":\"3/4.5/5+/null\","
                "\"property_type\":\"דירה/פנטהאוס/קוטג'/null\"}"
            ),
        }],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def parse_question(question, last_settlement=None):
    """Extract location and property parameters from a Hebrew real-estate question."""
    client = Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=220,
        messages=[{
            "role": "user",
            "content": (
                "אתה מנתח שאלות על נדל\"ן בישראל. חלץ את כל הפרמטרים הבאים:\n"
                "החזר JSON בלבד:\n"
                "{\n"
                "  \"settlement\": \"שם ישוב או null\",\n"
                "  \"street\": \"שם רחוב בלבד (לא שכונה/רובע) או null\",\n"
                "  \"neighborhood\": \"שם שכונה/רובע/אזור או null\",\n"
                "  \"rooms\": \"מספר חדרים כמחרוזת (3 / 4.5 / 5+) או null\",\n"
                "  \"property_type\": \"דירה / פנטהאוס / קוטג' / דו-משפחתי / בית פרטי / null\",\n"
                "  \"min_price\": מספר_שלם_בשקלים_או_null,\n"
                "  \"max_price\": מספר_שלם_בשקלים_או_null\n"
                "}\n"
                "כללים חשובים:\n"
                "- רחוב ושכונה לא יחד — אם יש רחוב, neighborhood=null\n"
                "- 'רובע X' (כגון רובע ג, רובע טו) = שכונה, לא רחוב → neighborhood\n"
                "- 'שכונת X', 'אזור X', 'הצפון הישן' = שכונה → neighborhood\n"
                "- 'רחוב X', 'ברחוב X' = רחוב → street\n"
                "- '3-4 חדרים' או '3 עד 4 חדרים' = rooms: '3-4'\n"
                "דוגמאות:\n"
                "'דירת 3 חדרים ברחוב הרצל תל אביב' → {\"settlement\":\"תל אביב\",\"street\":\"הרצל\",\"neighborhood\":null,\"rooms\":\"3\",\"property_type\":\"דירה\",\"min_price\":null,\"max_price\":null}\n"
                "'רובע טו אשדוד 4.5 חדרים' → {\"settlement\":\"אשדוד\",\"street\":null,\"neighborhood\":\"רובע טו\",\"rooms\":\"4.5\",\"property_type\":null,\"min_price\":null,\"max_price\":null}\n"
                "'עד 3 מיליון נווה שאנן' → {\"settlement\":\"תל אביב\",\"street\":null,\"neighborhood\":\"נווה שאנן\",\"rooms\":null,\"property_type\":null,\"min_price\":null,\"max_price\":3000000}\n"
                "'פנטהאוס 5 חדרים בהרצליה' → {\"settlement\":\"הרצליה\",\"street\":null,\"neighborhood\":null,\"rooms\":\"5+\",\"property_type\":\"פנטהאוס\",\"min_price\":null,\"max_price\":null}\n"
                "שאלה: " + question +
                (f"\n(הקשר: המשתמש חיפש לאחרונה ב-{last_settlement} — אם השאלה לא מציינת ישוב מפורש, השתמש בו)" if last_settlement else "")
            ),
        }],
    )
    text = msg.content[0].text.strip()
    # Strip markdown code fences if Claude wrapped the JSON
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def generate_suggestions(settlement, street, neighborhood, rooms, property_type):
    """Return 2–3 contextual follow-up question chips."""
    s = []
    loc = street or neighborhood or settlement or ""
    # Drill-down suggestions
    if not street and not neighborhood:
        s.append(f"עסקאות ברחוב ספציפי ב{settlement}?")
        s.append(f"עסקאות בשכונה מסוימת ב{settlement}?")
    # Room filter suggestions
    if not rooms:
        s += [f"עסקאות דירות 3 חדרים ב{loc}?", f"עסקאות דירות 4 חדרים ב{loc}?", f"עסקאות דירות 5+ חדרים ב{loc}?"]
    else:
        s.append(f"עסקאות 3 חדרים ב{loc}?")
        s.append(f"עסקאות 5 חדרים ב{loc}?")
    # Property type
    if not property_type:
        s.append(f"עסקאות פנטהאוס ב{loc}?")
    # Trend
    s.append(f"מגמת עסקאות ב{loc}?")
    # Deduplicate and cap
    seen, out = set(), []
    for x in s:
        if x not in seen:
            seen.add(x); out.append(x)
        if len(out) == 3:
            break
    return out


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
                f'ענה בעברית (3-4 משפטים) על שאלה זו לגבי עסקאות נדל"ן שבוצעו: "{question}"\n'
                f'חשוב: הנתונים הם עסקאות שכבר בוצעו (לא הערכת שווי). '
                f'השתמש בניסוחים כמו "עסקאות בוצעו במחיר ממוצע", "נמכרו ב-", "מחיר עסקאות" — לא "עולה" או "שווה".\n'
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


def run_research(question, session_id, pre_settlement=None,
                 pre_neighborhood=None,
                 pre_rooms=None, pre_property_type=None, no_more_clarify=False,
                 pre_min_year=None, no_year_clarify=False,
                 last_settlement=None):
    """SSE generator: [clarify location?] → [clarify rooms?] → fetch → analyze → done."""

    if pre_settlement:
        # User answered a clarification — parse street/neighborhood (and any property params)
        settlement = pre_settlement
        rooms = pre_rooms or ""
        property_type = pre_property_type or ""
        try:
            refined = parse_refinement(question, settlement)
        except Exception as e:
            yield _sse({"step": "error", "text": f"לא הצלחתי לזהות: {e}", "done": True})
            return
        street = refined.get("street") or ""
        neighborhood = refined.get("neighborhood") or pre_neighborhood or ""
        # Allow refinement to also specify rooms/type if not pre-set
        if not rooms:
            rooms = refined.get("rooms") or ""
        if not property_type:
            property_type = refined.get("property_type") or ""
    else:
        try:
            parsed = parse_question(question, last_settlement=last_settlement)
        except Exception as e:
            yield _sse({"step": "error", "text": f"לא הצלחתי לזהות מיקום: {e}", "done": True})
            return
        settlement = parsed.get("settlement", "")
        street = parsed.get("street") or ""
        neighborhood = parsed.get("neighborhood") or ""
        rooms = parsed.get("rooms") or ""
        property_type = parsed.get("property_type") or ""

    # Parse price range (from original or refinement)
    min_price = None
    max_price = None
    if not pre_settlement:
        min_price = parsed.get("min_price")
        max_price = parsed.get("max_price")

    label = street or neighborhood or settlement

    if not settlement:
        yield _sse({"step": "error", "text": "לא זיהיתי עיר — נסה לציין עיר ספציפית.", "done": True})
        return

    # Validate settlement looks like an Israeli place name (not food/random words)
    suspicious_words = {"מנגו", "תפוח", "בננה", "pizza", "burger", "test", "טסט"}
    if settlement.lower() in suspicious_words or (len(settlement) < 2):
        yield _sse({"step": "error", "text": f"לא זיהיתי כתובת תקינה בשאלה שלך. נסה לכתוב למשל: 'עסקאות ברחוב הרצל תל אביב'", "done": True})
        return

    # Step A: if only a city was detected, ask user to narrow location
    if not street and not neighborhood and not pre_settlement:
        yield _sse({
            "step": "clarify",
            "text": f"זיהיתי: {settlement} — רחוב, שכונה, או כל העיר?",
            "settlement": settlement,
            "rooms": rooms or None,
            "property_type": property_type or None,
            "done": True,
        })
        return

    # Step B: no rooms/type filter yet → ask. Applies to city and neighborhood level.
    if not street and not rooms and not property_type and not no_more_clarify:
        loc_name = neighborhood or settlement
        yield _sse({
            "step": "clarify_rooms",
            "text": f"מצוין! כמה חדרים מעניין אותך ב{loc_name}?",
            "settlement": settlement,
            "street": "",
            "neighborhood": neighborhood,
            "done": True,
        })
        return

    # Step C: ask how many years of data to show (city and neighborhood level)
    if not street and pre_min_year is None and not no_year_clarify:
        from datetime import datetime as _dt
        cur_year = _dt.now().year
        loc_name = neighborhood or settlement
        yield _sse({
            "step": "clarify_years",
            "text": f"כמה שנות עסקאות תרצה לראות ב{loc_name}?",
            "settlement": settlement,
            "neighborhood": neighborhood,
            "cur_year": cur_year,
            "done": True,
        })
        return

    location_parts = [settlement]
    if street:
        location_parts.append(street)
    elif neighborhood:
        location_parts.append(neighborhood)
    prop_parts = []
    if rooms:
        prop_parts.append(f"{rooms} חד'")
    if property_type:
        prop_parts.append(property_type)
    location_str = ", ".join(location_parts)
    if prop_parts:
        location_str += f" | {', '.join(prop_parts)}"
    yield _sse({"step": "parsed", "text": f"✓ זיהיתי: {location_str}"})

    report_id = db.create_report(session_id, question, settlement, street or neighborhood)

    project_dir = Path(__file__).parent
    cmd = ["python3", str(project_dir / "research.py"), "--settlement", settlement, "--limit", "150"]
    if street:
        cmd += ["--street", street]
    elif neighborhood:
        cmd += ["--neighborhood", neighborhood]
    if rooms:
        cmd += ["--rooms", str(rooms)]
    if property_type:
        cmd += ["--property-type", property_type]
    if min_price:
        cmd += ["--min-price", str(int(min_price))]
    if max_price:
        cmd += ["--max-price", str(int(max_price))]
    if pre_min_year:
        cmd += ["--min-year", str(int(pre_min_year))]

    # Signal loading (single event — client shows spinner, not verbose progress)
    yield _sse({"step": "loading", "text": "מעבד..."})

    acquired = _research_lock.acquire(blocking=True, timeout=5)
    if not acquired:
        yield _sse({"step": "error", "text": "המערכת עמוסה כרגע — נסה שוב בעוד כמה שניות.", "done": True})
        return

    output_lines = []
    proc = None
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", cwd=str(project_dir),
        )
        try:
            stdout_data, _ = proc.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            yield _sse({"step": "error", "text": "הבקשה ארכה יותר מדי (90 שניות) — נסה שנית.", "done": True})
            return
        # Collect output for error reporting only — don't stream to client
        for line in stdout_data.splitlines():
            output_lines.append(line.strip())
    except Exception as e:
        import logging, traceback
        logging.error("research.py subprocess exception: %s\n%s", e, traceback.format_exc())
        yield _sse({"step": "error", "text": f"שגיאה: {e}", "done": True})
        return
    finally:
        _research_lock.release()

    if proc.returncode != 0:
        import logging
        logging.error(
            "research.py failed (exit %d) cmd=%s\nOutput:\n%s",
            proc.returncode, cmd,
            "\n".join(output_lines[-30:])
        )
        # Check if it's a "no deals" situation vs real failure
        last_lines = " ".join(output_lines[-10:])
        if "אין עסקאות" in last_lines or "0 deals" in last_lines or "נמצאו 0" in last_lines:
            yield _sse({"step": "error", "text": f"לא נמצאו עסקאות עבור {label} עם הפרמטרים שבחרת. נסה לשנות את הסינון או לחפש אזור רחב יותר.", "done": True})
        else:
            error_hint = output_lines[-1] if output_lines else "no output"
            yield _sse({"step": "error", "text": f"אירעה שגיאה בשליפת הנתונים — נסה שוב. ({error_hint})", "done": True})
        return

    # Resolve the actual label that research.py used (may differ from user input
    # e.g. "רובע טו" → "רובע ט\"ו" after neighborhood lookup)
    actual_label = label
    analysis_files = sorted(glob.glob(f"{OUTPUT_DIR}/analysis_*.json"), key=os.path.getmtime, reverse=True)
    if analysis_files:
        newest_stem = Path(analysis_files[0]).stem  # "analysis_רובע ט\"ו"
        actual_label = newest_stem[len("analysis_"):]  # strip prefix

    # Update DB with actual label so /api/deals can find the raw file
    db.update_report_label(report_id, actual_label)

    # Find the most-recently generated HTML report
    html_files = sorted(glob.glob(f"{OUTPUT_DIR}/report_*.html"), key=os.path.getmtime, reverse=True)
    report_path = html_files[0] if html_files else None

    # Generate Hebrew summary from analysis JSON
    summary = ""
    total_deals = 0
    analysis_path = Path(OUTPUT_DIR) / f"analysis_{actual_label}.json"
    if analysis_path.exists():
        try:
            stats = json.loads(analysis_path.read_text(encoding="utf-8"))
            total_deals = stats.get("meta", {}).get("total_deals", 0)
            summary = generate_summary(stats, question)
        except Exception:
            import traceback
            traceback.print_exc()

    if report_path:
        db.update_report(report_id, report_path, summary)

    suggestions = generate_suggestions(settlement, street, neighborhood, rooms, property_type)

    yield _sse({
        "step": "done", "text": "✓ הדוח מוכן",
        "report_id": report_id, "summary": summary,
        "total_deals": total_deals, "label": actual_label,
        "settlement": settlement,
        "suggestions": suggestions,
        "done": True,
    })


def create_app(config=None):
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
    app.config["ADMIN_PASSWORD"] = os.environ.get("NADLAN_ADMIN_PASSWORD", "changeme")

    if config:
        app.config.update(config)

    db.init_db()
    limiter.init_app(app)

    # Start background reCAPTCHA token refresh (headless Playwright)
    import token_cache
    token_cache.start(settlement_id=5000)

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
        resp.set_cookie(
            "nadlan_session", session_token,
            max_age=7 * 86400,
            httponly=True,
            samesite="Lax",
            secure=not app.debug,
        )
        return resp

    @app.route("/")
    def chat():
        return render_template("chat.html")

    @app.route("/auth-error")
    def auth_error():
        return render_template("auth.html", error=True), 401

    @app.route("/ask", methods=["POST"])
    @limiter.limit("30 per hour; 10 per minute")
    def ask():
        data = request.get_json() or {}
        question = data.get("question", "").strip()
        pre_settlement = data.get("settlement", "").strip()
        pre_neighborhood = data.get("neighborhood", "").strip()
        pre_rooms = data.get("rooms") or ""
        pre_property_type = data.get("property_type", "").strip()
        no_more_clarify = bool(data.get("no_more_clarify", False))
        pre_min_year = data.get("min_year") or None
        no_year_clarify = bool(data.get("no_year_clarify", False))
        last_settlement = (data.get("last_settlement") or "").strip() or None
        if not question:
            return {"error": "שאלה ריקה"}, 400

        session_id = None

        return Response(
            stream_with_context(run_research(
                question, session_id,
                pre_settlement=pre_settlement or None,
                pre_neighborhood=pre_neighborhood or None,
                pre_rooms=str(pre_rooms) if pre_rooms else None,
                pre_property_type=pre_property_type or None,
                no_more_clarify=no_more_clarify,
                pre_min_year=int(pre_min_year) if pre_min_year else None,
                no_year_clarify=no_year_clarify,
                last_settlement=last_settlement,
            )),
            content_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.route("/api/deals/<int:report_id>")
    def api_deals(report_id):
        """Return paginated raw deals for a report (for inline chat display)."""
        report = db.get_report(report_id)
        if not report:
            abort(404)
        label = report.get("street") or report.get("settlement", "")
        raw_path = Path(OUTPUT_DIR) / f"deals_raw_{label}.json"
        if not raw_path.exists():
            return {"deals": [], "total": 0}
        deals_raw = json.loads(raw_path.read_text(encoding="utf-8"))
        offset = max(0, int(request.args.get("offset", 0)))
        limit  = min(50, max(1, int(request.args.get("limit", 20))))
        page   = [
            {
                "date":    d.get("dealDate") or "",
                "address": d.get("address") or "",
                "price":   d.get("dealAmount") or 0,
                "rooms":   d.get("roomNum") or "",
                "floor":   d.get("floor") or "",
                "area":    d.get("assetArea") or "",
                "type":    d.get("dealNature") or "",
            }
            for d in deals_raw[offset: offset + limit]
        ]
        return {"deals": page, "total": len(deals_raw), "offset": offset}

    @app.route("/report/<int:report_id>")
    def report_page(report_id):
        report = db.get_report(report_id)
        if not report:
            abort(404)
        return render_template("report.html", report=report, report_id=report_id)

    @app.route("/report/<int:report_id>/file")
    def report_file(report_id):
        report = db.get_report(report_id)
        if not report or not report.get("report_path"):
            abort(404)
        path = Path(report["report_path"])
        if not path.exists():
            abort(404)
        output_dir = Path(OUTPUT_DIR).resolve()
        resolved = path.resolve()
        if not resolved.is_relative_to(output_dir):
            abort(403)
        return send_file(str(resolved), mimetype="text/html")

    @app.errorhandler(429)
    def rate_limit_handler(e):
        return {"error": "יותר מדי בקשות — נסה שוב בעוד מספר דקות."}, 429

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
    port = int(os.environ.get("PORT", 9000))
    create_app().run(debug=True, host="0.0.0.0", port=port)
