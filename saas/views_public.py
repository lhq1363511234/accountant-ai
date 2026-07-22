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
    target = f"{P}/app" if user else f"{P}/register"
    target_text = "进入工作台" if user else "免费开始处理"
    doc_icon = """<svg viewBox='0 0 24 24' aria-hidden='true'><path d='M7 3h7l4 4v14H7z'/><path d='M14 3v5h5M10 12h5M10 16h5'/></svg>"""
    reports = [
        ("现金流量表", "按经营、投资、筹资活动自动汇总，保留待确认项目。"),
        ("资金收支总览", "集中查看流入、流出、净增加额、笔数和复核数量。"),
        ("每日资金收支表", "按日期展示流入、流出、当日净额和累计净额。"),
        ("收入分类分析", "按收入性质汇总金额，快速识别主要资金来源。"),
        ("费用支出分析", "按支出类别形成费用结构表，辅助费用复核。"),
        ("往来单位分析", "按客户、供应商和其他交易对手汇总收付款。"),
        ("待复核流水表", "单独整理低置信度和待确认流水，方便集中处理。"),
        ("多账户来源汇总", "多个银行账户或文件合并后仍可按来源追溯汇总。"),
    ]
    report_cards = "".join(
        f"<article class='report-card'><div class='report-icon'>{doc_icon}</div><div><span class='live-tag'>已上线</span>"
        f"<h3>{html.escape(title)}</h3><p>{html.escape(desc)}</p></div></article>"
        for title, desc in reports
    )
    capabilities = [
        ("自动识别复杂表头", "支持银行导出的 Excel、CSV，自动查找真实表头并清理前置说明行。"),
        ("多文件与多账户合并", "一次上传多个账户流水，并保留来源文件，减少人工复制粘贴。"),
        ("会计规则与 AI 协同", "先执行确定性规则，再由当前配置的大模型补充判断和依据。"),
        ("人工复核与规则学习", "优先呈现待确认项目，人工修改后沉淀为下次可复用规则。"),
        ("财务可视化分析", "提供收支趋势、活动净额、分类结构和交易对手分析。"),
        ("一套 Excel 完整交付", "分类台账、汇总、现金流量表和多维分析表一次导出。"),
    ]
    capability_cards = "".join(
        f"<article class='cap-card'><span class='cap-index'>{i:02d}</span><h3>{html.escape(title)}</h3><p>{html.escape(desc)}</p></article>"
        for i, (title, desc) in enumerate(capabilities, 1)
    )
    body = f"""
<section class='home-hero'><div class='wrap hero-grid'>
  <div class='hero-copy'>
    <span class='eyebrow'>AI 财务流水分析与报表平台</span>
    <h1>银行流水自动整理<span>多维财务报表一次生成</span></h1>
    <p class='hero-lead'>上传银行流水，自动完成字段识别、收支归类、现金流分类、风险复核和多维财务报表。财务人员保留判断权，系统负责第一轮整理。</p>
    <ul class='hero-points'><li>支持 Excel / CSV / 多账户合并</li><li>规则优先，AI 补充判断依据</li><li>一次导出多张可复核财务表</li></ul>
    <div class='hero-actions'><a class='btn primary lg' href='{target}'>{target_text}</a><a class='btn lg' href='#reports'>查看可生成的报表</a></div>
    <p class='hero-note'>免费版每月 {config.PLANS['free']['rows_per_month']} 行 · 无需信用卡 · 结果支持人工复核</p>
  </div>
  <div class='product-preview' aria-label='财务分析报表界面预览'>
    <div class='preview-head'><div><span class='preview-dot'></span><strong>本月资金分析</strong></div><span>已完成</span></div>
    <div class='preview-kpis'><div><small>现金流入</small><b>¥ 1,286,400</b></div><div><small>现金流出</small><b>¥ 936,820</b></div><div><small>净增加额</small><b class='positive'>¥ 349,580</b></div></div>
    <div class='preview-chart'><div class='chart-label'><span>每日资金趋势</span><small>近 30 天</small></div><svg viewBox='0 0 520 150' role='img' aria-label='现金流趋势示意图'><path class='area' d='M0 125 L45 110 L90 118 L135 75 L180 88 L225 55 L270 72 L315 38 L360 58 L405 32 L450 46 L500 18 L520 25 L520 150 L0 150Z'/><path class='line' d='M0 125 L45 110 L90 118 L135 75 L180 88 L225 55 L270 72 L315 38 L360 58 L405 32 L450 46 L500 18 L520 25'/></svg></div>
    <div class='preview-reports'><div><span>现金流量表</span><b>已生成</b></div><div><span>费用支出分析</span><b>已生成</b></div><div><span>待复核流水</span><b class='warning'>12 笔</b></div></div>
  </div>
</div></section>

<section class='trust-strip'><div class='wrap trust-grid'>
  <div><b>23 类</b><span>现金流项目口径</span></div><div><b>8+ 张</b><span>自动生成财务表</span></div>
  <div><b>多账户</b><span>合并与来源追溯</span></div><div><b>可复核</b><span>每笔保留依据与置信度</span></div>
</div></section>

<section class='section reports-section' id='reports'><div class='wrap'>
  <div class='section-intro'><span class='eyebrow'>报表中心</span><h2>不止现金流量表，一份流水生成多维财务分析</h2>
  <p>所有报表都来自上传流水和已确认分类，不虚构银行流水无法支持的资产负债或利润数据。</p></div>
  <div class='report-grid'>{report_cards}</div>
  <div class='report-cta'><div><strong>一次导出，形成完整财务工作底稿</strong><span>包含分类结果、处理文件、分类汇总及多张分析表。</span></div><a class='btn primary' href='{target}'>上传流水生成报表</a></div>
</div></section>

<section class='section capability-section' id='features'><div class='wrap'>
  <div class='section-intro'><span class='eyebrow'>核心能力</span><h2>不是黑盒自动编表，而是可解释、可复核的财务工作流</h2>
  <p>系统负责识别、整理和初步判断；财务人员可以逐笔修改，并让规则越来越贴合企业口径。</p></div>
  <div class='cap-grid'>{capability_cards}</div>
</div></section>

<section class='section workflow-section' id='how'><div class='wrap'>
  <div class='section-intro'><span class='eyebrow'>工作流程</span><h2>四步完成从原始流水到财务报表</h2></div>
  <ol class='workflow-list'>
    <li><span>01</span><div><h3>上传原始资料</h3><p>银行流水、合同、回单和业务说明可一起上传。</p></div></li>
    <li><span>02</span><div><h3>确认字段映射</h3><p>系统自动猜测日期、摘要、对方和金额列，你只需确认。</p></div></li>
    <li><span>03</span><div><h3>AI 分类与集中复核</h3><p>优先处理低置信度和待确认项目，不必逐行从头检查。</p></div></li>
    <li><span>04</span><div><h3>查看分析并导出</h3><p>查看趋势、结构和往来分析，一次下载完整 Excel 报表包。</p></div></li>
  </ol>
</div></section>

<section class='section role-section'><div class='wrap role-grid'>
  <div class='role-copy'><span class='eyebrow'>适用场景</span><h2>让财务人员把时间留给判断，而不是复制粘贴</h2><p>适用于月末流水整理、现金流编制、资金收支复盘、费用结构检查和往来单位分析。</p></div>
  <div class='role-cards'><article><h3>企业财务</h3><p>多账户流水合并、月度资金分析、异常流水复核。</p></article><article><h3>代账会计</h3><p>批量整理客户流水，统一分类口径并导出工作底稿。</p></article><article><h3>财务负责人</h3><p>快速查看资金流入流出、支出结构和重点往来单位。</p></article></div>
</div></section>

<section class='security-band'><div class='wrap security-grid'><div><span class='eyebrow'>数据与控制权</span><h2>AI 给建议，最终判断始终由财务人员确认</h2></div><ul><li>账号与任务数据隔离</li><li>低置信度自动进入复核</li><li>支持自定义会计口径 Skill</li><li>文件和结果保存在自有服务器</li></ul></div></section>

<section class='final-cta'><div class='wrap'><span class='eyebrow'>开始使用</span><h2>上传第一份流水，看看它能生成哪些财务报表</h2><p>无需改模板，先从现有银行流水开始。</p><a class='btn primary lg' href='{target}'>{target_text}</a></div></section>
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
