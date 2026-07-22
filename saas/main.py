#!/usr/bin/env python3
"""现金流 AI · 商业站主入口。
公开站点 + 多用户工作台 + 额度计费 + AI 现金流分类。
"""
from __future__ import annotations

from flask import Flask, request, redirect, session, g, abort, jsonify

import config
import secrets
from models import db, User
from views_public import public as bp_public
from views_app import bp as bp_app


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path=f"{config.SITE_BASE_PATH}/static")
    app.secret_key = config.SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{config.DB_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
    app.config["SESSION_COOKIE_SECURE"] = config.SESSION_COOKIE_SECURE
    app.config["SESSION_COOKIE_HTTPONLY"] = config.SESSION_COOKIE_HTTPONLY
    app.config["SESSION_COOKIE_SAMESITE"] = config.SESSION_COOKIE_SAMESITE
    app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 12
    if test_config:
        app.config.update(test_config)
    app.url_map.strict_slashes = False

    db.init_app(app)
    with app.app_context():
        db.create_all()

    app.register_blueprint(bp_public, url_prefix=config.SITE_BASE_PATH)
    app.register_blueprint(bp_app, url_prefix=config.SITE_BASE_PATH)

    P = config.SITE_BASE_PATH

    # 需要登录才能访问的前缀
    def login_required_path(path: str) -> bool:
        return path.startswith(f"{P}/app")

    @app.before_request
    def load_user_and_guard():
        g.user = None
        uid = session.get("uid")
        if uid:
            g.user = db.session.get(User, uid)
        session.setdefault("csrf_token", secrets.token_urlsafe(32))
        if request.method == "POST":
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not sent or not secrets.compare_digest(sent, session["csrf_token"]):
                abort(400, "CSRF token invalid")
        # 未登录访问 /app 区域 -> 去登录
        if login_required_path(request.path) and g.user is None:
            return redirect(f"{P}/login?next={request.path}")

    @app.get(f"{P}/health")
    def health():
        return jsonify({
            "ok": True,
            "model": config.AI_MODEL_NAME,
            "ai_configured": bool(config.AI_KEY),
            "database": "ok",
        })

    @app.errorhandler(400)
    def bad_request(error):
        return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>请求无效</title>"
                "<body style='font-family:sans-serif;max-width:680px;margin:80px auto;padding:24px'>"
                "<h1>请求已失效</h1><p>安全令牌无效或页面停留时间过长，请返回上一页刷新后重试。</p>"
                f"<p><a href='{P}/'>返回首页</a></p></body></html>"), 400

    @app.errorhandler(413)
    def too_large(error):
        return ("文件总大小超过 32 MB，请压缩或拆分后重新上传。", 413)

    @app.context_processor
    def inject_globals():
        return {"SITE_NAME": config.SITE_NAME, "BASE_PATH": P}

    return app


app = create_app()

if __name__ == "__main__":
    app.run("127.0.0.1", 5010, debug=False)
