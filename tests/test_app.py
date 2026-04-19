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

    def test_auth_error_returns_401(self, client):
        resp = client.get("/auth-error")
        assert resp.status_code == 401

    def test_valid_magic_link_sets_cookie(self, client):
        uid = db.create_user("רוני")
        token = db.create_magic_link(uid)
        resp = client.get(f"/auth/{token}")
        assert "nadlan_session" in resp.headers.get("Set-Cookie", "")


class TestAdmin:
    def test_admin_requires_login(self, client):
        resp = client.get("/admin")
        assert resp.status_code == 302

    def test_admin_login_wrong_password(self, client):
        resp = client.post("/admin/login", data={"password": "wrong"})
        assert resp.status_code == 200
        assert b"error" in resp.data.lower() or "שגויה".encode() in resp.data

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

    def test_admin_with_session_returns_200(self, app, client):
        client.post("/admin/login", data={"password": app.config["ADMIN_PASSWORD"]})
        resp = client.get("/admin")
        assert resp.status_code == 200

    def test_create_link_empty_name_returns_400(self, app, client):
        client.post("/admin/login", data={"password": app.config["ADMIN_PASSWORD"]})
        resp = client.post("/admin/create-link", data={"name": ""})
        assert resp.status_code == 400


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

    def test_report_without_session_redirects(self, client):
        resp = client.get("/report/1")
        assert resp.status_code == 302

    def test_report_file_without_session_returns_401(self, client):
        resp = client.get("/report/1/file")
        assert resp.status_code == 401

    def test_report_file_not_found_returns_404(self, client):
        _login_client(client)
        resp = client.get("/report/9999/file")
        assert resp.status_code == 404
