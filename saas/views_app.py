#!/usr/bin/env python3
"""应用页路由：控制台 / 上传 / 映射 / 分类 / 结果复核 / 问答 / Skill / 管理 / 导出。
所有路由都要求登录，且任务数据按用户隔离。"""
from __future__ import annotations

import html
import re
import json
import time
from pathlib import Path
from typing import List, Tuple

import pandas as pd
from flask import (
    Blueprint, request, redirect, session, abort, send_file, g, Response,
)

import config
import engine
import charts
import billing
from theme import app_shell
from models import db, User, Job, current_period

def safe_filename(name: str, fallback: str = "file") -> str:
    """安全化文件名但保留中文：去掉路径分隔与危险字符，保留中文/字母/数字/常见符号。"""
    name = (name or "").strip().replace("\\", "/").split("/")[-1]
    # 去掉控制字符与不安全符号
    name = re.sub(r'[\x00-\x1f<>:"|?*]+', "", name)
    name = name.strip(" .")
    # 折叠空白
    name = re.sub(r"\s+", "_", name)
    return name or fallback


bp = Blueprint("app_views", __name__)
P = config.SITE_BASE_PATH


# ---------- 登录态 ----------
def current_user() -> User | None:
    uid = session.get("uid")
    if not uid:
        return None
    return db.session.get(User, uid)


@bp.before_request
def _require_login():
    g.user = current_user()
    if g.user is None:
        return redirect(f"{P}/login")


def _quota():
    return billing.quota_status(g.user)


def _learned_rules_path() -> Path:
    d = config.DATA_DIR / "user_rules"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{g.user.id}.json"


def load_learned_rules() -> list:
    p = _learned_rules_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_learned_rule(ctx: dict, category: str):
    import re
    text = " ".join(str(ctx.get(k, "")) for k in ("summary", "counterparty", "remark")).strip()
    if not text or category not in config.CATEGORIES or category == "待确认":
        return
    keywords = []
    for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", text):
        if token in ("转账", "交易", "银行", "公司", "有限", "账户", "摘要", "备注"):
            continue
        keywords.append(token[:16])
        if len(keywords) >= 3:
            break
    if not keywords:
        return
    rules = load_learned_rules()
    rule = {"keywords": keywords, "direction": ctx.get("direction", ""),
            "category": category, "created_at": time.time(), "sample": text[:120]}
    sig = (tuple(rule["keywords"]), rule["direction"], rule["category"])
    for r in rules:
        if (tuple(r.get("keywords", [])), r.get("direction", ""), r.get("category", "")) == sig:
            return
    rules.insert(0, rule)
    _learned_rules_path().write_text(
        json.dumps(rules[:200], ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- 任务存取（DB，用户隔离）----------
def get_job_or_404(job_id: str) -> Job:
    job = db.session.get(Job, job_id)
    if not job or job.user_id != g.user.id:
        abort(404)
    return job


# ---------- 控制台 ----------
@bp.route("/app")
def dashboard():
    q = _quota()
    jobs = Job.query.filter_by(user_id=g.user.id).order_by(Job.created_at.desc()).limit(6).all()
    pct = 0 if not q["limit"] else min(100, round(q["used"] * 100 / q["limit"]))
    recent = "".join(
        f"<tr><td>{html.escape(j.filename or '未命名')}</td>"
        f"<td>{'流水表' if j.type=='table' else '文档'}</td>"
        f"<td>{j.row_count or 0}</td>"
        f"<td><span class='tag tag-{j.status}'>{_status_label(j.status)}</span></td>"
        f"<td>{time.strftime('%m-%d %H:%M', time.localtime(j.created_at))}</td>"
        f"<td><a class='btn sm' href='{P}/app/job/{j.id}'>打开</a></td></tr>"
        for j in jobs
    ) or "<tr><td colspan='6' class='muted' style='text-align:center;padding:24px'>还没有任务，去上传第一份银行流水吧。</td></tr>"

    body = f"""
    <div class='page-head'><h1>控制台</h1><a class='btn primary' href='{P}/app/upload'>+ 上传处理</a></div>
    <div class='cards-4'>
      <div class='stat'><div class='stat-label'>当前套餐</div><div class='stat-val'>{q['plan_name']}</div><a class='muted' href='{P}/pricing'>升级 →</a></div>
      <div class='stat'><div class='stat-label'>本月已用行数</div><div class='stat-val'>{q['used']}</div><div class='muted'>周期 {current_period()}</div></div>
      <div class='stat'><div class='stat-label'>本月剩余额度</div><div class='stat-val'>{q['remaining']}</div><div class='muted'>共 {q['limit']} 行</div></div>
      <div class='stat'><div class='stat-label'>单次上限</div><div class='stat-val'>{q['max_rows_per_job']}</div><div class='muted'>行/任务</div></div>
    </div>
    <div class='card'><div class='usage-bar'><span style='width:{pct}%'></span></div>
    <p class='muted'>本月额度已使用 {pct}%。额度按“成功分类的流水行数”计算，文档问答不计费。</p></div>
    <div class='card'><h2>最近任务</h2>
    <table class='tbl'><thead><tr><th>文件</th><th>类型</th><th>行数</th><th>状态</th><th>时间</th><th></th></tr></thead>
    <tbody>{recent}</tbody></table>
    <p><a class='btn' href='{P}/app/jobs'>查看全部任务 →</a></p></div>
    """
    return app_shell("控制台", "dashboard", body, g.user, q)


def _status_label(s: str) -> str:
    return {"created": "待处理", "classified": "已分类", "answered": "已分析"}.get(s, s)


# ---------- 上传 ----------
@bp.route("/app/upload", methods=["GET", "POST"])
def upload():
    q = _quota()
    if request.method == "POST":
        return _handle_upload()
    body = f"""
    <div class='page-head'><h1>上传处理</h1></div>
    <div class='card'>
      <form action='{P}/app/upload' method='post' enctype='multipart/form-data'>
        <h2>选择文件（可多选）</h2>
        <p class='muted'>表格：.xlsx / .xls / .csv；文档：.txt / .md / .docx / .pdf。多个表格自动合并；文档作为分类参考材料。单次最多 {q['max_rows_per_job']} 行。</p>
        <div class='drop'><input type='file' name='file' accept='.xlsx,.xls,.csv,.txt,.md,.docx,.pdf' multiple required>
          <div class='muted file-names' data-file-names>选择后将显示文件名</div></div>
        <p style='margin-top:16px'><button class='btn primary' type='submit'>上传并处理</button></p>
      </form>
    </div>
    <div class='cards-3'>
      <div class='feature'><h3>多表合并</h3><p>自动加“来源文件”列，导出时可追溯每行来自哪个文件。</p></div>
      <div class='feature'><h3>文档做依据</h3><p>合同、回单、说明和流水一起上传，AI 分类时参考。</p></div>
      <div class='feature'><h3>结果可复核</h3><p>逐行给出分类、依据、置信度，人工修改后可沉淀规则。</p></div>
    </div>
    """
    return app_shell("上传处理", "upload", body, g.user, q)


def _err_page(msg: str):
    body = f"<div class='card'><div class='alert err'>{html.escape(msg)}</div><p><a class='btn' href='{P}/app/upload'>返回上传</a></p></div>"
    return app_shell("出错了", "upload", body, g.user, _quota())


def _handle_upload():
    files = [f for f in request.files.getlist("file") if f and f.filename]
    if not files:
        return _err_page("没有选择文件。")
    from models import gen_id
    job_id = gen_id()
    upload_dir = config.UPLOAD_DIR / g.user.id
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved: List[Tuple[str, Path]] = []
    for f in files:
        name = safe_filename(f.filename, f"file_{len(saved)+1}")
        suffix = Path(name).suffix.lower()
        if suffix not in config.ALLOWED_SUFFIXES:
            return _err_page(f"文件 {f.filename} 类型不支持。")
        path = upload_dir / f"{job_id}_{len(saved)+1}_{name}"
        f.save(str(path))
        try:
            with path.open("rb") as fh:
                signature = fh.read(8)
            if suffix in (".xlsx", ".xlsm", ".docx") and not signature.startswith(b"PK"):
                raise ValueError("文件签名与扩展名不匹配（应为 Office 文件）")
            if suffix == ".pdf" and not signature.startswith(b"%PDF"):
                raise ValueError("文件签名与扩展名不匹配（应为 PDF 文件）")
            if suffix == ".xls" and not signature.startswith(b"\xd0\xcf\x11\xe0"):
                raise ValueError("文件签名与扩展名不匹配（应为旧版 Excel 文件）")
        except Exception as e:
            path.unlink(missing_ok=True)
            for _, old_path in saved:
                old_path.unlink(missing_ok=True)
            return _err_page(f"文件 {f.filename} 校验失败：{e}")
        saved.append((name, path))

    table_files = [(n, p) for n, p in saved if engine.is_tabular_file(p)]
    doc_files = [(n, p) for n, p in saved if not engine.is_tabular_file(p)]

    supporting_docs = ""
    if doc_files:
        try:
            supporting_docs = engine.combine_document_texts(doc_files)
        except Exception as e:
            return _err_page(f"读取文档失败：{e}")

    # 纯文档任务
    if not table_files:
        filename = saved[0][0] if len(saved) == 1 else f"合并文档任务_{len(saved)}个文件"
        data = {
            "id": job_id, "type": "document", "filename": filename,
            "files": [n for n, _ in saved], "paths": [str(p) for _, p in saved],
            "doc_text": supporting_docs[:120000], "created_at": time.time(), "chat": [],
        }
        try:
            skill = engine.get_accounting_skill(g.user.custom_skill or "")
            ans = engine.deepseek_answer(config.DOCUMENT_DEFAULT_QUESTION, engine.job_ai_context(data), skill)
        except Exception as e:
            ans = f"AI 自动分析失败：{e}\n\n你可以稍后重新发送问题。"
        data["chat"] = [{"question": config.DOCUMENT_DEFAULT_QUESTION, "answer": ans, "created_at": time.time()}]
        job = Job(id=job_id, user_id=g.user.id, type="document", filename=filename, status="answered", row_count=0)
        job.set_data(data)
        db.session.add(job)
        db.session.commit()
        return redirect(f"{P}/app/job/{job_id}")

    # 表格任务
    dfs, read_errors = [], []
    for name, path in table_files:
        try:
            df = engine.read_file(path)
            df.insert(0, "来源文件", name)
            dfs.append(df)
        except Exception as e:
            read_errors.append(f"{name}: {e}")
    if read_errors:
        for _, old_path in saved:
            old_path.unlink(missing_ok=True)
        return _err_page("读取表格失败：" + "; ".join(read_errors))
    df = pd.concat(dfs, ignore_index=True, sort=False).fillna("")

    # 额度预检：按行数
    ok, why = billing.can_process(g.user, len(df))
    if not ok:
        for _, old_path in saved:
            old_path.unlink(missing_ok=True)
        return _err_page(why)

    cols = [str(c) for c in df.columns]
    filename = table_files[0][0] if len(saved) == 1 else f"合并处理任务_{len(saved)}个文件"
    data = {
        "id": job_id, "type": "table", "filename": filename,
        "files": [n for n, _ in saved], "paths": [str(p) for _, p in saved],
        "columns": cols, "rows": df.to_dict(orient="records"),
        "supporting_docs": supporting_docs[:120000], "created_at": time.time(),
    }
    job = Job(id=job_id, user_id=g.user.id, type="table", filename=filename, status="created", row_count=len(df))
    job.set_data(data)
    db.session.add(job)
    db.session.commit()
    return redirect(f"{P}/app/job/{job_id}/map")


# ---------- 列映射 ----------
@bp.route("/app/job/<job_id>/map", methods=["GET", "POST"])
def map_columns(job_id):
    job = get_job_or_404(job_id)
    data = job.data()
    cols = data.get("columns", [])
    guesses = {
        "date": engine.guess_col(cols, ["日期", "交易日", "记账日", "date"]),
        "summary": engine.guess_col(cols, ["摘要", "用途", "交易附言", "备注", "说明", "summary"]),
        "counterparty": engine.guess_col(cols, ["对方户名", "对方名称", "对方单位", "户名", "收款人", "付款人", "对方", "单位", "客户", "供应商", "counter"]),
        "income": engine.guess_col(cols, ["收入", "贷方", "收方", "转入", "credit"]),
        "expense": engine.guess_col(cols, ["支出", "借方", "付方", "转出", "debit"]),
        "amount": engine.guess_col(cols, ["金额", "发生额", "amount"]),
        "direction": engine.guess_col(cols, ["方向", "收支", "借贷", "类型"]),
        "remark": engine.guess_col(cols, ["备注", "附言", "说明", "用途", "remark"]),
    }
    if request.method == "POST":
        mapping = {k: request.form.get(k, "") for k in guesses}
        data["mapping"] = mapping
        data["user_rules"] = request.form.get("user_rules") or config.DEFAULT_RULES
        job.set_data(data)
        db.session.commit()
        return classify(job_id)

    labels = {"date": "日期", "summary": "摘要/用途", "counterparty": "对方户名",
              "income": "收入/贷方", "expense": "支出/借方", "amount": "金额（含正负）",
              "direction": "收支方向", "remark": "备注"}
    def options(sel=""):
        opts = "<option value=''>-- 不使用 --</option>"
        opts += "".join(f"<option {'selected' if c==sel else ''}>{html.escape(c)}</option>" for c in cols)
        return opts
    rows_map = "".join(
        f"<div class='map-row'><label>{labels[k]}</label><select name='{k}'>{options(v)}</select></div>"
        for k, v in guesses.items()
    )
    preview_rows = data.get("rows", [])[:8]
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols[:10])
    prev = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(r.get(c,''))[:60])}</td>" for c in cols[:10]) + "</tr>"
        for r in preview_rows
    )
    body = f"""
    <div class='page-head'><h1>字段映射</h1><span class='muted'>任务：{html.escape(engine.display_filename(data))} · 共 {job.row_count} 行</span></div>
    <div class='card'>
      <form method='post'>
        <h2>1. 告诉 AI 每一列是什么</h2>
        <div class='map-grid'>{rows_map}</div>
        <h2 style='margin-top:22px'>2. 补充分类规则（可选，AI 优先遵守）</h2>
        <textarea name='user_rules' style='min-height:180px'>{html.escape(config.DEFAULT_RULES)}</textarea>
        <p style='margin-top:16px'><button class='btn primary' type='submit'>开始分类</button></p>
      </form>
    </div>
    <div class='card'><h3>数据预览（前 8 行）</h3><div class='table-wrap'><table class='tbl'><thead><tr>{head}</tr></thead><tbody>{prev}</tbody></table></div></div>
    """
    return app_shell("字段映射", "jobs", body, g.user, _quota())


# ---------- 分类 ----------
@bp.route("/app/job/<job_id>/classify", methods=["POST"])
def classify(job_id):
    job = get_job_or_404(job_id)
    data = job.data()
    if data.get("results"):
        return redirect(f"{P}/app/job/{job_id}/results")
    if not data.get("mapping"):
        return redirect(f"{P}/app/job/{job_id}/map")

    # 二次额度校验并扣减；已完成任务不会重复消耗额度
    rows = len(data.get("rows") or [])
    ok, why = billing.can_process(g.user, rows)
    if not ok:
        return _err_page(why)

    data = engine.classify_job(data, load_learned_rules(), g.user.custom_skill or "")
    job.set_data(data)
    job.status = "classified"
    db.session.commit()
    billing.add_usage(g.user, rows)
    return redirect(f"{P}/app/job/{job_id}/results")


# ---------- 结果复核 ----------
@bp.route("/app/job/<job_id>/results", methods=["GET", "POST"])
def results(job_id):
    job = get_job_or_404(job_id)
    data = job.data()
    results = data.get("results") or []
    if not results:
        return redirect(f"{P}/app/job/{job_id}/map")

    if request.method == "POST":
        learned = 0
        for r in results:
            i = r.get("id")
            new_cat = request.form.get(f"cat_{i}")
            if new_cat and new_cat in config.CATEGORIES and new_cat != r.get("category"):
                r["category"] = new_cat
                r["source"] = "人工修正"
                r["review"] = False
                save_learned_rule(r.get("ctx") or {}, new_cat)
                learned += 1
        data["results"] = results
        job.set_data(data)
        db.session.commit()
        return redirect(f"{P}/app/job/{job_id}/results?saved={learned}")

    saved = request.args.get("saved")
    note = f"<div class='alert ok'>已保存修改，其中 {saved} 条已沉淀为你的学习规则，下次自动命中。</div>" if saved else ""

    # 汇总
    summary = {}
    for r in results:
        c = r.get("category", "")
        summary[c] = summary.get(c, 0) + 1
    chips = "".join(f"<span class='chip'>{html.escape(k)} · {v}</span>" for k, v in sorted(summary.items(), key=lambda x: -x[1]))

    # 现金流量表卡片
    cf = engine.cashflow_statement(data)
    def _fmt(v):
        try:
            return f"{float(v):,.2f}"
        except Exception:
            return str(v)
    act_cards = ""
    for act in cf["activities"]:
        lines = ""
        for r in act["inflow"]:
            lines += f"<div class='cf-line'><span>{html.escape(r['line'])}</span><span class='num in'>+{_fmt(r['amount'])}</span></div>"
        for r in act["outflow"]:
            lines += f"<div class='cf-line'><span>减：{html.escape(r['line'])}</span><span class='num out'>-{_fmt(r['amount'])}</span></div>"
        if not lines:
            lines = "<div class='cf-line muted'><span>本期无</span><span></span></div>"
        net = act["net"]
        net_cls = "in" if net >= 0 else "out"
        act_cards += (
            f"<div class='cf-act'><div class='cf-act-head'>{html.escape(act['activity'])}产生的现金流量</div>"
            f"{lines}"
            f"<div class='cf-line total'><span>{html.escape(act['activity'])}现金流量净额</span>"
            f"<span class='num {net_cls}'>{_fmt(net)}</span></div></div>"
        )
    ni = cf["net_increase"]
    ni_cls = "in" if ni >= 0 else "out"
    warn = ""
    if cf["unclassified_count"] or cf["review_count"]:
        bits = []
        if cf["unclassified_count"]:
            bits.append(f"{cf['unclassified_count']} 笔待确认（金额 {_fmt(cf['unclassified_amount'])}，未纳入净额）")
        if cf["review_count"]:
            bits.append(f"{cf['review_count']} 笔建议人工复核")
        warn = f"<div class='alert warn'>⚠️ {' · '.join(bits)}。请在下方表格核对后再出正式报表。</div>"
    cf_card = f"""
    <div class='card'>
      <div class='page-head' style='margin:0 0 4px'><h3 style='margin:0'>现金流量表（准则口径 · AI 自动汇总）</h3>
      <span class='num {ni_cls}' style='font-size:20px;font-weight:700'>净增加额 {_fmt(ni)}</span></div>
      <p class='muted' style='margin:2px 0 14px'>依据分类结果按经营/投资/筹资三大活动自动汇总，可导出 Excel 得到完整报表。</p>
      {warn}
      <div class='cf-grid'>{act_cards}</div>
    </div>
    """

    # ---------- 图表看板 ----------
    an = engine.analytics(data)
    def _m(v):
        try:
            return f"{float(v):,.2f}"
        except Exception:
            return str(v)
    net_cls = "pos" if an["net_increase"] >= 0 else "neg"
    kpis = f"""
    <div class='kpi-grid'>
      <div class='kpi-card'><div class='k-l'>流水笔数</div><div class='k-v'>{an['total']}</div><div class='k-s muted'>{an['in_count']} 收 / {an['out_count']} 支</div></div>
      <div class='kpi-card'><div class='k-l'>现金流入</div><div class='k-v pos'>{_m(an['total_in'])}</div><div class='k-s muted'>合计收到</div></div>
      <div class='kpi-card'><div class='k-l'>现金流出</div><div class='k-v neg'>{_m(an['total_out'])}</div><div class='k-s muted'>合计支出</div></div>
      <div class='kpi-card'><div class='k-l'>净增加额</div><div class='k-v {net_cls}'>{_m(an['net_increase'])}</div><div class='k-s muted'>流入-流出</div></div>
      <div class='kpi-card'><div class='k-l'>需复核</div><div class='k-v'>{an['review_count']}</div><div class='k-s muted'>{an['unclassified_count']} 笔待确认</div></div>
    </div>
    """
    # 各图表
    c_inout = charts.inout_bar(an["total_in"], an["total_out"])
    c_activity = charts.activity_bars(an["activity_net"])
    c_expense = charts.donut(an["expense_cats"], center_title="支出", center_value=_m(an["total_out"]))
    c_income = charts.donut(an["income_cats"], center_title="收入", center_value=_m(an["total_in"]))
    c_trend = charts.trend_lines(an["trend"])
    c_top = charts.hbar(an["top_counterparty"], color="#7c3aed", sub_key="count")
    conf_data = [{"name": k, "amount": v} for k, v in an["conf_buckets"].items() if v > 0]
    c_conf = charts.donut(conf_data, center_title="总笔数", center_value=str(an["total"]), max_items=6)
    src_data = [{"name": k, "amount": v} for k, v in an["src_dist"].items()]
    c_src = charts.hbar(src_data, color="#0891b2")

    dash = f"""
    <div class='card'>
      <div class='page-head' style='margin:0 0 12px'><h3 style='margin:0'>数据可视化看板</h3>
      <span class='muted' style='font-size:13px'>基于 {an['total']} 笔流水自动生成 · 图表可悬停查看明细</span></div>
      {kpis}
      <div class='chart-grid'>
        <div class='chart-box'><div class='chart-title'>收支占比</div>{c_inout}</div>
        <div class='chart-box'><div class='chart-title'>三大活动净额</div>{c_activity}</div>
      </div>
      <div class='chart-grid'>
        <div class='chart-box'><div class='chart-title'>支出结构</div>{c_expense}</div>
        <div class='chart-box'><div class='chart-title'>收入结构</div>{c_income}</div>
      </div>
      <div class='chart-box full'><div class='chart-title'>现金流趋势（流入/流出/累计净额）</div>{c_trend}</div>
      <div class='chart-grid'>
        <div class='chart-box'><div class='chart-title'>Top 交易对手（按金额）</div>{c_top}</div>
        <div class='chart-box'><div class='chart-title'>AI 置信度分布</div>{c_conf}</div>
      </div>
      <div class='chart-box full'><div class='chart-title'>分类来源分布（规则 / AI / 人工）</div>{c_src}</div>
    </div>
    """

    def opt(sel):
        return "".join(f"<option {'selected' if c==sel else ''}>{html.escape(c)}</option>" for c in config.CATEGORIES)
    trs = []
    for r in results:
        ctx = r.get("ctx") or {}
        conf = r.get("confidence", 0)
        review = "⚠️" if r.get("review") else ""
        trs.append(
            f"<tr><td data-label='日期'>{html.escape(str(ctx.get('date','')))}</td>"
            f"<td data-label='摘要'>{html.escape(str(ctx.get('summary','')))[:40]}</td>"
            f"<td data-label='对方'>{html.escape(str(ctx.get('counterparty','')))[:20]}</td>"
            f"<td data-label='金额' class='num'>{ctx.get('signed_amount','')}</td>"
            f"<td data-label='现金流分类'><select name='cat_{r.get('id')}'>{opt(r.get('category'))}</select></td>"
            f"<td data-label='判断依据' class='muted reason-cell' style='max-width:260px;font-size:12px'>{html.escape(str(r.get('reason','')))[:120]}</td>"
            f"<td data-label='置信' class='num'>{conf}{review}</td>"
            f"<td data-label='来源' class='muted' style='font-size:12px'>{html.escape(str(r.get('source','')))}</td></tr>"
        )
    body = f"""
    <div class='page-head'><h1>分类结果</h1><span class='muted'>{html.escape(engine.display_filename(data))} · {len(results)} 行</span></div>
    {note}
    {cf_card}
    {dash}
    <div class='card'><h3>分类汇总</h3><div class='chips'>{chips}</div>
    <p style='margin-top:14px'>
      <a class='btn primary' href='{P}/app/job/{job_id}/export'>导出 Excel</a>
      <a class='btn' href='{P}/app/job/{job_id}/ask'>问 AI</a>
      <a class='btn' href='{P}/app/job/{job_id}/report'>下载报告</a>
    </p></div>
    <div class='card'>
      <form method='post'>
        <p class='muted'>修改任意行的分类后点击保存，系统会记住你的判断，下次遇到相似流水自动套用（规则学习）。</p>
        <div class='mobile-hint'>左右滑动查看完整字段，或直接在卡片中修改分类</div><div class='table-wrap results-scroll'><table class='tbl results-table'><thead><tr><th>日期</th><th>摘要</th><th>对方</th><th>金额</th><th>现金流分类</th><th>依据</th><th>置信</th><th>来源</th></tr></thead>
        <tbody>{''.join(trs)}</tbody></table></div>
        <p style='margin-top:14px'><button class='btn primary' type='submit'>保存修改并学习</button></p>
      </form>
    </div>
    """
    return app_shell("分类结果", "jobs", body, g.user, _quota())


# ---------- 问 AI ----------
@bp.route("/app/job/<job_id>/ask", methods=["GET", "POST"])
def ask(job_id):
    job = get_job_or_404(job_id)
    data = job.data()
    default_q = config.DOCUMENT_DEFAULT_QUESTION
    if request.method == "POST":
        qtext = (request.form.get("question") or "").strip() or default_q
        try:
            skill = engine.get_accounting_skill(g.user.custom_skill or "")
            ans = engine.deepseek_answer(qtext, engine.job_ai_context(data), skill)
        except Exception as e:
            ans = f"AI 调用失败：{e}"
        chat = data.get("chat") or []
        chat.append({"question": qtext, "answer": ans, "created_at": time.time()})
        data["chat"] = chat[-20:]
        job.set_data(data)
        job.status = "answered"
        db.session.commit()
        return redirect(f"{P}/app/job/{job_id}/ask")

    if data.get("doc_text"):
        preview = f"<pre class='pre'>{html.escape(str(data.get('doc_text',''))[:6000])}</pre>"
    else:
        cols = data.get("columns") or []
        head = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols[:8])
        rws = "".join("<tr>" + "".join(f"<td>{html.escape(str(r.get(c,'')))[:80]}</td>" for c in cols[:8]) + "</tr>" for r in (data.get("rows") or [])[:8])
        preview = f"<div class='table-wrap'><table class='tbl'><thead><tr>{head}</tr></thead><tbody>{rws}</tbody></table></div>"
    chats = "".join(
        f"<div class='chat'><div class='chat-q'>Q：{html.escape(c.get('question',''))}</div><div class='chat-a'>{html.escape(c.get('answer',''))}</div></div>"
        for c in (data.get("chat") or [])[::-1]
    )
    body = f"""
    <div class='page-head'><h1>问 AI</h1><span class='muted'>{html.escape(engine.display_filename(data))}</span></div>
    <div class='card'>
      <form method='post'>
        <textarea name='question' style='min-height:96px'>{html.escape(default_q)}</textarea>
        <p style='margin-top:12px'>
          <button class='btn primary' type='submit'>发送</button>
          <a class='btn' href='{P}/app/job/{job_id}/report'>下载报告</a>
          <a class='btn ghost' href='{P}/app/jobs'>返回任务</a>
        </p>
      </form>
    </div>
    {chats}
    <div class='card'><h3>文件预览</h3>{preview}</div>
    """
    return app_shell("问 AI", "jobs", body, g.user, _quota())


# ---------- 历史任务 ----------
@bp.route("/app/jobs")
def jobs():
    all_jobs = Job.query.filter_by(user_id=g.user.id).order_by(Job.created_at.desc()).all()
    rows = "".join(
        f"<tr><td>{html.escape(j.filename or '未命名')}</td>"
        f"<td>{'流水表' if j.type=='table' else '文档'}</td>"
        f"<td>{j.row_count or 0}</td>"
        f"<td><span class='tag tag-{j.status}'>{_status_label(j.status)}</span></td>"
        f"<td>{time.strftime('%Y-%m-%d %H:%M', time.localtime(j.created_at))}</td>"
        f"<td><a class='btn sm' href='{P}/app/job/{j.id}'>打开</a> "
        f"<a class='btn sm ghost' href='{P}/app/job/{j.id}/delete' onclick=\"return confirm('确认删除该任务？')\">删除</a></td></tr>"
        for j in all_jobs
    ) or "<tr><td colspan='6' class='muted' style='text-align:center;padding:24px'>暂无任务</td></tr>"
    body = f"""
    <div class='page-head'><h1>历史任务</h1><a class='btn primary' href='{P}/app/upload'>+ 上传处理</a></div>
    <div class='card'><table class='tbl'><thead><tr><th>文件</th><th>类型</th><th>行数</th><th>状态</th><th>时间</th><th></th></tr></thead>
    <tbody>{rows}</tbody></table></div>
    """
    return app_shell("历史任务", "jobs", body, g.user, _quota())


@bp.route("/app/job/<job_id>")
def open_job(job_id):
    job = get_job_or_404(job_id)
    if job.type == "document":
        return redirect(f"{P}/app/job/{job_id}/ask")
    data = job.data()
    if data.get("results"):
        return redirect(f"{P}/app/job/{job_id}/results")
    if data.get("mapping"):
        return redirect(f"{P}/app/job/{job_id}/map")
    return redirect(f"{P}/app/job/{job_id}/map")


@bp.route("/app/job/<job_id>/delete", methods=["POST"])
def delete_job(job_id):
    job = get_job_or_404(job_id)
    data = job.data()
    paths = list(data.get("paths") or [])
    paths.append(str(config.EXPORT_DIR / f"cashflow_{g.user.id}_{job_id}.xlsx"))
    db.session.delete(job)
    db.session.commit()
    for raw in paths:
        try:
            Path(raw).unlink(missing_ok=True)
        except OSError:
            pass
    return redirect(f"{P}/app/jobs")


# ---------- 报告 / 导出 ----------
@bp.route("/app/job/<job_id>/report")
def report(job_id):
    job = get_job_or_404(job_id)
    text = engine.build_report_text(job.data())
    return Response(text, mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=report_{job_id}.txt"})


@bp.route("/app/job/<job_id>/export")
def export(job_id):
    job = get_job_or_404(job_id)
    data = job.data()
    if not data.get("results"):
        return redirect(f"{P}/app/job/{job_id}/map")
    out = config.EXPORT_DIR / f"cashflow_{g.user.id}_{job_id}.xlsx"
    engine.export_excel(data, out)
    return send_file(str(out), as_attachment=True, download_name=f"现金流分类_{job_id}.xlsx")


# ---------- 财务 Skill ----------
@bp.route("/app/skill", methods=["GET", "POST"])
def skill():
    q = _quota()
    is_team = g.user.plan == "team" or g.user.is_admin
    if request.method == "POST":
        if not is_team:
            return _err_page("自定义会计口径 Skill 为团队版功能，请升级。")
        g.user.custom_skill = request.form.get("skill", "")[:20000]
        db.session.commit()
        return redirect(f"{P}/app/skill?saved=1")
    saved = "<div class='alert ok'>已保存你的会计口径 Skill。</div>" if request.args.get("saved") else ""
    current = g.user.custom_skill or engine.get_accounting_skill("")
    lock = "" if is_team else "<div class='alert warn'>自定义 Skill 是团队版功能。以下为系统默认口径，升级后可编辑。</div>"
    disabled = "" if is_team else "readonly"
    body = f"""
    <div class='page-head'><h1>财务处理 Skill</h1></div>
    {saved}{lock}
    <div class='card'>
      <p class='muted'>这是 AI 分类时遵守的会计口径说明。团队版可按贵司口径自定义，个人/专业版使用系统默认。</p>
      <form method='post'>
        <textarea name='skill' style='min-height:440px' {disabled}>{html.escape(current)}</textarea>
        {"<p style='margin-top:14px'><button class='btn primary' type='submit'>保存</button></p>" if is_team else ""}
      </form>
    </div>
    """
    return app_shell("财务 Skill", "skill", body, g.user, q)


# ---------- 管理后台 ----------
@bp.route("/app/admin")
def admin():
    if not g.user.is_admin:
        abort(403)
    users = User.query.order_by(User.created_at.desc()).all()
    from models import Usage
    rows = ""
    for u in users:
        usage = Usage.query.filter_by(user_id=u.id, period=current_period()).first()
        used = usage.rows_used if usage else 0
        jobn = Job.query.filter_by(user_id=u.id).count()
        rows += (
            f"<tr><td>{html.escape(u.email)}</td><td>{html.escape(u.company or '')}</td>"
            f"<td>{config.PLANS.get(u.plan,{}).get('name',u.plan)}</td>"
            f"<td>{used}</td><td>{jobn}</td>"
            f"<td>{'管理员' if u.is_admin else ''}</td>"
            f"<td><form method='post' action='{P}/app/admin/setplan' style='display:flex;gap:6px'>"
            f"<input type='hidden' name='uid' value='{u.id}'>"
            f"<select name='plan'>" + "".join(f"<option value='{c}' {'selected' if u.plan==c else ''}>{p['name']}</option>" for c, p in config.PLANS.items()) + "</select>"
            f"<button class='btn sm' type='submit'>改套餐</button></form></td></tr>"
        )
    body = f"""
    <div class='page-head'><h1>管理后台</h1><span class='muted'>共 {len(users)} 个用户</span></div>
    <div class='card'><table class='tbl'><thead><tr><th>邮箱</th><th>公司</th><th>套餐</th><th>本月用量</th><th>任务数</th><th>角色</th><th>操作</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
    """
    return app_shell("管理后台", "admin", body, g.user, _quota())


@bp.route("/app/admin/setplan", methods=["POST"])
def admin_setplan():
    if not g.user.is_admin:
        abort(403)
    u = db.session.get(User, request.form.get("uid"))
    plan = request.form.get("plan")
    if u and plan in config.PLANS:
        u.plan = plan
        db.session.commit()
    return redirect(f"{P}/app/admin")
