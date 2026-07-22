#!/usr/bin/env python3
"""公开页面：落地页、定价、注册、登录、登出。"""
from __future__ import annotations

import html
import time
from flask import Blueprint, request, redirect, session, render_template_string

import config
from models import db, User, current_period
from theme import public_shell, P

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
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        company = (request.form.get("company") or "").strip()
        if not email or "@" not in email:
            msg = "请输入有效邮箱"
        elif len(pw) < 6:
            msg = "密码至少 6 位"
        elif db.session.query(User).filter_by(email=email).first():
            msg = "该邮箱已注册，请直接登录"
        else:
            u = User(email=email, company=company, plan=config.DEFAULT_PLAN)
            u.set_password(pw)
            if email in config.ADMIN_EMAILS:
                u.is_admin = True
            db.session.add(u)
            db.session.commit()
            session.clear()
            session["uid"] = u.id
            return redirect(f"{P}/app")
    err = f"<div class='err'>{html.escape(msg)}</div>" if msg else ""
    body = f"""
<div class='auth'><div class='card'>
  <h1>创建账号</h1><p class='muted'>免费版每月 {config.PLANS['free']['rows_per_month']} 行额度，立即可用。</p>
  {err}
  <form method='post'>
    <label>邮箱</label><input type='email' name='email' required autofocus placeholder='you@company.com'>
    <label>公司名称（选填）</label><input type='text' name='company' placeholder='XX 有限公司'>
    <label>密码</label><input type='password' name='password' required placeholder='至少 6 位'>
    <div style='margin-top:18px'><button class='btn primary block' type='submit'>免费注册</button></div>
  </form>
  <p class='muted' style='margin-top:16px;text-align:center'>已有账号？<a href='{P}/login'>登录</a></p>
</div></div>
"""
    return public_shell(f"注册 · {config.SITE_NAME}", body)


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
