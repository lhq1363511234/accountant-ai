import re

import pytest

from main import create_app
from models import db, User, Job, Usage, EmailVerification, current_period
import mailer
import ai_settings
import config
import engine


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AI_SETTINGS_PATH", str(tmp_path / "ai-settings.json"))
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "SESSION_COOKIE_SECURE": False,
        "WTF_CSRF_ENABLED": False,
    })
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app


def csrf(client, path="/account/login"):
    response = client.get(path)
    match = re.search(rb"name=['\"]csrf_token['\"] value=['\"]([^'\"]+)", response.data)
    assert match, response.data[:500]
    return match.group(1).decode()


def make_user(app, email="user@example.com"):
    with app.app_context():
        user = User(email=email, plan="free")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        return user.id


def login_session(client, uid):
    with client.session_transaction() as sess:
        sess["uid"] = uid
        sess["csrf_token"] = "test-token"


def test_health(app):
    r = app.test_client().get("/account/health")
    assert r.status_code == 200
    assert r.json["ok"] is True
    assert r.json["model"] == "Grok 4.5"


def test_csrf_rejects_post_without_token(app):
    r = app.test_client().post("/account/login", data={"email": "x@y.com", "password": "bad"})
    assert r.status_code == 400
    assert "安全令牌" in r.get_data(as_text=True)


def test_register_email_verification_and_dashboard(app, monkeypatch):
    sent = {}
    monkeypatch.setattr(mailer, "send_verification_email", lambda email, code: sent.update(email=email, code=code))
    client = app.test_client()
    token = csrf(client, "/account/register")
    r = client.post("/account/register", data={
        "csrf_token": token, "email": "new@example.com", "password": "password123", "company": "测试公司"
    })
    assert r.status_code == 302 and r.location.endswith("/account/verify-email")
    assert sent["email"] == "new@example.com" and len(sent["code"]) == 6
    with app.app_context():
        assert EmailVerification.query.filter_by(email="new@example.com").count() == 1
    r = client.post("/account/verify-email", data={"csrf_token": token, "code": sent["code"]}, follow_redirects=True)
    assert r.status_code == 200
    assert "控制台" in r.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter_by(email="new@example.com").count() == 1
        assert EmailVerification.query.filter_by(email="new@example.com").count() == 0


def test_email_verification_rejects_wrong_code(app, monkeypatch):
    monkeypatch.setattr(mailer, "send_verification_email", lambda email, code: None)
    client = app.test_client()
    token = csrf(client, "/account/register")
    client.post("/account/register", data={
        "csrf_token": token, "email": "wrong@example.com", "password": "password123"
    })
    r = client.post("/account/verify-email", data={"csrf_token": token, "code": "000000"})
    assert r.status_code == 200
    assert "验证码不正确" in r.get_data(as_text=True)
    with app.app_context():
        pending = EmailVerification.query.filter_by(email="wrong@example.com").one()
        assert pending.attempts == 1


def test_user_cannot_open_another_users_job(app):
    uid1 = make_user(app, "one@example.com")
    uid2 = make_user(app, "two@example.com")
    with app.app_context():
        job = Job(id="privatejob01", user_id=uid2, type="table", filename="private.csv")
        job.set_data({"columns": [], "rows": []})
        db.session.add(job)
        db.session.commit()
    client = app.test_client()
    login_session(client, uid1)
    assert client.get("/account/app/job/privatejob01").status_code == 404


def test_classify_is_idempotent_and_quota_charged_once(app, monkeypatch):
    uid = make_user(app)
    with app.app_context():
        job = Job(id="classifyjob1", user_id=uid, type="table", filename="test.csv", row_count=1)
        job.set_data({
            "columns": ["摘要", "收入"], "rows": [{"摘要": "销售回款", "收入": "100"}],
            "mapping": {"summary": "摘要", "income": "收入"}, "user_rules": ""
        })
        db.session.add(job)
        db.session.commit()

    def fake_classify(data, learned_rules, custom_skill):
        data = dict(data)
        data["results"] = [{
            "id": 0, "category": "销售商品、提供劳务收到的现金", "reason": "测试",
            "confidence": 1.0, "review": False, "source": "规则", "ctx": {"signed_amount": 100}
        }]
        return data

    monkeypatch.setattr(engine, "classify_job", fake_classify)
    client = app.test_client()
    login_session(client, uid)
    r1 = client.post("/account/app/job/classifyjob1/classify", data={"csrf_token": "test-token"})
    r2 = client.post("/account/app/job/classifyjob1/classify", data={"csrf_token": "test-token"})
    assert r1.status_code == 302 and r2.status_code == 302
    with app.app_context():
        usage = Usage.query.filter_by(user_id=uid, period=current_period()).one()
        assert usage.rows_used == 1


def test_admin_can_test_and_activate_ai_settings(app, monkeypatch):
    uid = make_user(app, "admin@example.com")
    with app.app_context():
        user = db.session.get(User, uid)
        user.is_admin = True
        db.session.commit()
    monkeypatch.setattr(ai_settings, "test_connection", lambda data: {"ok": True, "message": "连接成功", "models": [data["model"]]})
    client = app.test_client()
    login_session(client, uid)
    r = client.post("/account/app/admin/ai-settings", data={
        "csrf_token": "test-token",
        "action": "activate",
        "provider": "Test NewAPI",
        "base_url": "https://api.example.com",
        "model": "test-model",
        "display_name": "Test Model",
        "api_key": "sk-test-secret-value-123456",
    }, follow_redirects=True)
    assert r.status_code == 200
    page = r.get_data(as_text=True)
    assert "已切换为当前模型" in page
    assert "sk-test-secret-value-123456" not in page
    active = ai_settings.load_settings()
    assert active["enabled"] is True
    assert active["base_url"] == "https://api.example.com/v1"
    assert active["model"] == "test-model"


def test_failed_ai_test_keeps_previous_active_settings(app, monkeypatch):
    ai_settings.save_settings({
        "provider": "Working", "base_url": "https://working.example/v1", "api_key": "sk-working-secret-123",
        "model": "working-model", "display_name": "Working Model", "enabled": True, "updated_at": 1,
    })
    uid = make_user(app, "admin2@example.com")
    with app.app_context():
        user = db.session.get(User, uid)
        user.is_admin = True
        db.session.commit()
    monkeypatch.setattr(ai_settings, "test_connection", lambda data: {"ok": False, "message": "无可用模型", "models": []})
    client = app.test_client()
    login_session(client, uid)
    client.post("/account/app/admin/ai-settings", data={
        "csrf_token": "test-token", "action": "activate", "provider": "Broken",
        "base_url": "https://broken.example/v1", "model": "bad-model", "display_name": "Bad",
        "api_key": "sk-broken-secret-123",
    })
    active = ai_settings.load_settings()
    draft = ai_settings.load_draft()
    assert active["provider"] == "Working" and active["enabled"] is True
    assert draft["provider"] == "Broken" and draft["enabled"] is False
