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
