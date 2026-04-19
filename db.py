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
