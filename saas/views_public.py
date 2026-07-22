#!/usr/bin/env python3
"""公开页面：落地页、定价、注册、登录、登出。"""
from __future__ import annotations

import html
import time
import hashlib
import hmac
import secrets
from flask import Blueprint, request, redirect, session, current_app

import config
from models import db, User, EmailVerification, current_period
from theme import public_shell, P
import mailer

public = Blueprint("public", __name__)

# 轻量登录限速：单进程内按 IP+邮箱记录失败次数，生产环境可替换为 Redis。
_LOGIN_FAILURES = {}
LOGIN_WINDOW = 10 * 60
LOGIN_MAX_FAILURES = 8


def _current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return db.session.get(User, uid)


def _code_hash(email: str, code: str) -> str:
    message = f"{email}:{code}".encode("utf-8")
    return hmac.new(config.SECRET_KEY.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _new_code() -> str:
    return f"{secrets.randbelow(900000) + 100000:06d}"


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        local = local[:1] + "*"
    else:
        local = local[:2] + "*" * min(5, len(local) - 2)
    return f"{local}@{domain}"


def _send_registration_code(email: str, password: str, company: str) -> tuple[bool, str]:
    now = time.time()
    ip = request.remote_addr or "unknown"
    recent = EmailVerification.query.filter(
        EmailVerification.request_ip == ip,
        EmailVerification.created_at >= now - 3600,
    ).all()
    if sum(v.send_count or 0 for v in recent) >= config.EMAIL_VERIFY_MAX_PER_HOUR:
        return False, "验证码发送次数过多，请一小时后再试"

    pending = EmailVerification.query.filter_by(email=email).order_by(EmailVerification.created_at.desc()).first()
    if pending and now - (pending.sent_at or 0) < config.EMAIL_VERIFY_RESEND_COOLDOWN:
        wait = max(1, int(config.EMAIL_VERIFY_RESEND_COOLDOWN - (now - pending.sent_at)))
        session["pending_email"] = email
        return False, f"验证码已发送，请 {wait} 秒后再重新发送"

    code = _new_code()
    draft = User(email=email, company=company, plan=config.DEFAULT_PLAN)
    draft.set_password(password)
    try:
        mailer.send_verification_email(email, code)
    except Exception:
        current_app.logger.exception("registration verification email failed for %s", email)
        return False, "验证码发送失败，请稍后重试"

    if pending:
        if now - pending.created_at >= 3600:
            pending.created_at = now
            pending.send_count = 1
        else:
            pending.send_count = (pending.send_count or 0) + 1
        pending.password_hash = draft.password_hash
        pending.company = company
        pending.code_hash = _code_hash(email, code)
        pending.expires_at = now + config.EMAIL_VERIFY_TTL
        pending.attempts = 0
        pending.sent_at = now
        pending.request_ip = ip
    else:
        pending = EmailVerification(
            email=email,
            password_hash=draft.password_hash,
            company=company,
            code_hash=_code_hash(email, code),
            expires_at=now + config.EMAIL_VERIFY_TTL,
            attempts=0,
            sent_at=now,
            created_at=now,
            request_ip=ip,
            send_count=1,
        )
        db.session.add(pending)
    db.session.commit()
    session["pending_email"] = email
    return True, ""


@public.route("/")
def landing():
    user = _current_user()
    feats = [
        ("🤖", "AI 逐行分类", "结合规则引擎与 Grok 4.5 大模型，银行流水逐行判定现金流量表项目，给出依据与置信度。"),
        ("📊", "现金流量表 23 类", "严格按《企业会计准则第31号》经营/投资/筹资口径，覆盖 23 个现金流项目。"),
        ("📎", "多文件合并", "多个账户流水一次上传合并处理，合同/回单/说明可作为分类依据一起分析。"),
        ("✅", "人工复核优先", "低置信度自动标记待复核，会计确认一次即沉淀为规则，越用越准。"),
        ("📤", "一键导出台账", "分类结果、判断依据、汇总表导出 Excel，直接用于编表和归档。"),
        ("🔒", "数据自主可控", "文件与结果仅保存在你的服务器，按账号隔离，互不可见。"),
    ]
    feat_cards = "".join(
        f"<div class='card feat'><div class='ic'>{i}</div><h3>{html.escape(t)}</h3><p>{html.escape(d)}</p></div>"
        for i, t, d in feats
    )
    steps = [
        ("上传流水", "拖入银行流水 Excel/CSV，可同时上传合同、回单等文档。"),
        ("AI 分类", "系统逐行判定现金流项目，标出需要复核的行。"),
        ("复核导出", "确认或修改分类，一键导出分类台账与汇总表。"),
    ]
    step_cards = "".join(
        f"<div class='card'><h3>{html.escape(t)}</h3><p>{html.escape(d)}</p></div>"
        for t, d in steps
    )
    body = f"""
<section class='hero'><div class='wrap'>
  <span class='pill'>Grok 4.5 大模型 + 会计准则口径</span>
  <h1>银行流水，<span class='g'>一键生成现金流量表分类</span></h1>
  <p class='sub'>{html.escape(config.SITE_TAGLINE)}。面向中小企业财务与代账会计，把逐笔归类的重复工作交给 AI，你只做复核。</p>
  <div class='cta'>
    <a class='btn primary lg' href='{P}/register'>免费开始，无需信用卡</a>
    <a class='btn lg' href='{P}/pricing'>查看定价</a>
  </div>
  <p class='muted' style='margin-top:16px;font-size:13px'>免费版每月 {config.PLANS['free']['rows_per_month']} 行额度</p>
</div></section>

<section class='section' id='features'><div class='wrap'>
  <h2>把最花时间的归类交给 AI</h2>
  <p class='lead'>不是简单关键词匹配，而是结合方向、对方、摘要、金额与你的会计口径综合判断。</p>
  <div class='grid c3'>{feat_cards}</div>
</div></section>

<section class='section' style='background:#fff' id='how'><div class='wrap'>
  <h2>三步出结果</h2>
  <p class='lead'>从上传到导出台账，通常几分钟。</p>
  <div class='grid c3 steps'>{step_cards}</div>
  <div style='text-align:center;margin-top:36px'><a class='btn primary lg' href='{P}/register'>立即免费试用</a></div>
</div></section>
"""
    return public_shell(config.SITE_NAME, body, user)


@public.route("/pricing")
def pricing():
    user = _current_user()
    order = ["free", "pro", "team"]
    cards = []
    for code in order:
        p = config.PLANS[code]
        hot = "hot" if code == "pro" else ""
        tag = "<span class='tag'>最受欢迎</span>" if code == "pro" else ""
        price = "免费" if p["price_month"] == 0 else f"¥{p['price_month']}<small>/月</small>"
        feats = "".join(f"<li>{html.escape(x)}</li>" for x in p["features"])
        if user:
            if user.plan == code:
                btn = "<a class='btn block' style='pointer-events:none;opacity:.6'>当前套餐</a>"
            elif code == "free":
                btn = f"<a class='btn block' href='{P}/app'>进入控制台</a>"
            else:
                btn = f"<a class='btn primary block' href='{P}/app/checkout/{code}'>升级到{html.escape(p['name'])}</a>"
        else:
            btn = f"<a class='btn {'primary' if hot else ''} block' href='{P}/register'>{'免费开始' if code=='free' else '选择'+p['name']}</a>"
        cards.append(f"<div class='plan {hot}'>{tag}<h3>{html.escape(p['name'])}</h3><div class='price'>{price}</div>"
                     f"<p class='muted' style='margin:0'>每月 {p['rows_per_month']:,} 行流水额度</p><ul>{feats}</ul>{btn}</div>")
    body = f"""
<section class='section'><div class='wrap'>
  <h2>简单透明的定价</h2>
  <p class='lead'>按每月可处理的流水行数计费。随时升级，免费版永久可用。</p>
  <div class='price-grid'>{''.join(cards)}</div>
  <p class='muted' style='text-align:center;margin-top:28px;font-size:13px'>付费套餐当前为线下开通模式，下单后我们会尽快为你的账号开通对应额度。</p>
</div></section>
"""
    return public_shell(f"定价 · {config.SITE_NAME}", body, user)


@public.route("/register", methods=["GET", "POST"])
def register():
    if _current_user():
        return redirect(f"{P}/app")
    msg = ""
    values = {"email": "", "company": ""}
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        company = (request.form.get("company") or "").strip()[:255]
        values = {"email": email, "company": company}
        if not email or "@" not in email or len(email) > 255:
            msg = "请输入有效邮箱"
        elif len(pw) < 8:
            msg = "密码至少 8 位"
        elif len(pw) > 128:
            msg = "密码不能超过 128 位"
        elif db.session.query(User).filter_by(email=email).first():
            msg = "该邮箱已注册，请直接登录"
        else:
            sent, msg = _send_registration_code(email, pw, company)
            if sent:
                return redirect(f"{P}/verify-email")
    err = f"<div class='err'>{html.escape(msg)}</div>" if msg else ""
    body = f"""
<div class='auth'><div class='card'>
  <h1>创建账号</h1><p class='muted'>完成邮箱验证后即可使用，每月免费 {config.PLANS['free']['rows_per_month']} 行。</p>
  {err}
  <form method='post'>
    <label>工作邮箱</label><input type='email' name='email' required autofocus autocomplete='email' value='{html.escape(values['email'], quote=True)}' placeholder='you@company.com'>
    <p class='field-help'>我们会向这个邮箱发送 6 位验证码。</p>
    <label>公司名称（选填）</label><input type='text' name='company' autocomplete='organization' value='{html.escape(values['company'], quote=True)}' placeholder='XX 有限公司'>
    <label>密码</label><input type='password' name='password' required minlength='8' maxlength='128' autocomplete='new-password' placeholder='至少 8 位'>
    <div style='margin-top:18px'><button class='btn primary block' type='submit'>发送验证码</button></div>
  </form>
  <p class='muted' style='margin-top:16px;text-align:center'>已有账号？<a href='{P}/login'>登录</a></p>
</div></div>
"""
    return public_shell(f"注册 · {config.SITE_NAME}", body)


@public.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    if _current_user():
        return redirect(f"{P}/app")
    email = (session.get("pending_email") or "").strip().lower()
    if not email:
        return redirect(f"{P}/register")
    msg = ""
    if request.method == "POST":
        code = (request.form.get("code") or "").strip()
        pending = EmailVerification.query.filter_by(email=email).order_by(EmailVerification.created_at.desc()).first()
        now = time.time()
        if not pending:
            msg = "验证信息不存在，请重新注册"
        elif pending.expires_at < now:
            msg = "验证码已过期，请重新发送"
        elif pending.attempts >= config.EMAIL_VERIFY_MAX_ATTEMPTS:
            msg = "验证码尝试次数过多，请重新发送"
        elif not hmac.compare_digest(pending.code_hash, _code_hash(email, code)):
            pending.attempts = (pending.attempts or 0) + 1
            db.session.commit()
            remaining = max(0, config.EMAIL_VERIFY_MAX_ATTEMPTS - pending.attempts)
            msg = f"验证码不正确，还可尝试 {remaining} 次"
        elif User.query.filter_by(email=email).first():
            EmailVerification.query.filter_by(email=email).delete()
            db.session.commit()
            msg = "该邮箱已注册，请直接登录"
        else:
            user = User(email=email, company=pending.company or "", plan=config.DEFAULT_PLAN)
            user.password_hash = pending.password_hash
            if email in config.ADMIN_EMAILS:
                user.is_admin = True
            db.session.add(user)
            EmailVerification.query.filter_by(email=email).delete()
            db.session.commit()
            session.clear()
            session["uid"] = user.id
            return redirect(f"{P}/app")
    err = f"<div class='err'>{html.escape(msg)}</div>" if msg else ""
    body = f"""
<div class='auth'><div class='card verify-card'>
  <div class='verify-icon'>@</div><h1>验证邮箱</h1>
  <p class='muted'>6 位验证码已发送到 <strong>{html.escape(_mask_email(email))}</strong>，{config.EMAIL_VERIFY_TTL // 60} 分钟内有效。</p>
  {err}
  <form method='post'>
    <label>邮箱验证码</label>
    <input class='otp-input' type='text' name='code' required autofocus inputmode='numeric' pattern='[0-9]{{6}}' maxlength='6' autocomplete='one-time-code' placeholder='000000'>
    <div style='margin-top:18px'><button class='btn primary block' type='submit'>验证并创建账号</button></div>
  </form>
  <div class='verify-actions'>
    <form method='post' action='{P}/resend-code'><button class='btn ghost' type='submit'>重新发送验证码</button></form>
    <a class='btn ghost' href='{P}/register'>更换邮箱</a>
  </div>
</div></div>
"""
    return public_shell(f"验证邮箱 · {config.SITE_NAME}", body)


@public.route("/resend-code", methods=["POST"])
def resend_code():
    if _current_user():
        return redirect(f"{P}/app")
    email = (session.get("pending_email") or "").strip().lower()
    pending = EmailVerification.query.filter_by(email=email).order_by(EmailVerification.created_at.desc()).first() if email else None
    if not pending:
        return redirect(f"{P}/register")
    now = time.time()
    if now - (pending.sent_at or 0) < config.EMAIL_VERIFY_RESEND_COOLDOWN:
        return redirect(f"{P}/verify-email")
    if pending.send_count >= config.EMAIL_VERIFY_MAX_PER_HOUR and now - pending.created_at < 3600:
        return redirect(f"{P}/verify-email")
    code = _new_code()
    try:
        mailer.send_verification_email(email, code)
    except Exception:
        current_app.logger.exception("resend verification email failed for %s", email)
        return redirect(f"{P}/verify-email")
    if now - pending.created_at >= 3600:
        pending.created_at = now
        pending.send_count = 1
    else:
        pending.send_count = (pending.send_count or 0) + 1
    pending.code_hash = _code_hash(email, code)
    pending.expires_at = now + config.EMAIL_VERIFY_TTL
    pending.attempts = 0
    pending.sent_at = now
    db.session.commit()
    return redirect(f"{P}/verify-email")


@public.route("/login", methods=["GET", "POST"])
def login():
    if _current_user():
        return redirect(f"{P}/app")
    msg = ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        key = (request.remote_addr or "unknown", email)
        now = time.time()
        failures = [t for t in _LOGIN_FAILURES.get(key, []) if now - t < LOGIN_WINDOW]
        if len(failures) >= LOGIN_MAX_FAILURES:
            msg = "尝试次数过多，请 10 分钟后再试"
        else:
            u = db.session.query(User).filter_by(email=email).first()
            if u and u.check_password(pw):
                _LOGIN_FAILURES.pop(key, None)
                session.clear()
                session["uid"] = u.id
                return redirect(f"{P}/app")
            failures.append(now)
            _LOGIN_FAILURES[key] = failures
            msg = "邮箱或密码不正确"
    err = f"<div class='err'>{html.escape(msg)}</div>" if msg else ""
    body = f"""
<div class='auth'><div class='card'>
  <h1>登录</h1><p class='muted'>欢迎回来。</p>
  {err}
  <form method='post'>
    <label>邮箱</label><input type='email' name='email' required autofocus>
    <label>密码</label><input type='password' name='password' required>
    <div style='margin-top:18px'><button class='btn primary block' type='submit'>登录</button></div>
  </form>
  <p class='muted' style='margin-top:16px;text-align:center'>还没有账号？<a href='{P}/register'>免费注册</a></p>
</div></div>
"""
    return public_shell(f"登录 · {config.SITE_NAME}", body)


@public.route("/logout")
def logout():
    session.clear()
    return redirect(f"{P}/")
