#!/usr/bin/env python3
"""项目内财务处理 Skill 注册表、选择校验和提示词组合。"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List

SKILL_DIR = Path(__file__).resolve().parent / "financial_skill_defs"
SKILLS: Dict[str, Dict[str, str]] = {
    "cashflow": {"name": "现金流量表分类", "tag": "基础必选", "desc": "按经营、投资、筹资活动逐笔分类并标记待确认项。", "file": "cashflow.md"},
    "income_expense": {"name": "收入与费用分析", "tag": "经营分析", "desc": "识别收入来源、费用结构、大额项目和变化趋势。", "file": "income_expense.md"},
    "counterparty": {"name": "往来单位分析", "tag": "客户/供应商", "desc": "汇总主要客户、供应商及交易对手的收付款与集中度。", "file": "counterparty.md"},
    "reconciliation": {"name": "银行对账与内部转账", "tag": "多账户", "desc": "识别账户间调拨、疑似重复流水及余额连续性风险。", "file": "reconciliation.md"},
    "risk_review": {"name": "异常流水复核", "tag": "风险检查", "desc": "筛查重复、大额、拆分、个人往来和方向冲突交易。", "file": "risk_review.md"},
    "cashflow_health": {"name": "现金流健康度", "tag": "资金管理", "desc": "分析净现金流、资金波动、集中度和持续承压信号。", "file": "cashflow_health.md"},
    "tax_review": {"name": "税费与合规支出", "tag": "税费整理", "desc": "归集税费、社保、公积金等支出并提示异常月份。", "file": "tax_review.md"},
}
DEFAULT_SKILLS = ["cashflow", "income_expense", "counterparty", "risk_review"]


def normalize_skill_ids(values) -> List[str]:
    if isinstance(values, str):
        values = values.split(",")
    picked = []
    for value in values or []:
        key = str(value).strip()
        if key in SKILLS and key not in picked:
            picked.append(key)
    if "cashflow" not in picked:
        picked.insert(0, "cashflow")
    return picked or list(DEFAULT_SKILLS)


def skill_names(values) -> List[str]:
    return [SKILLS[x]["name"] for x in normalize_skill_ids(values)]


def compose_skill(values, custom: str = "") -> str:
    ids = normalize_skill_ids(values)
    chunks = ["# 本次启用的财务处理 Skill\n执行顺序：数据标准化 → 现金流分类 → 专项分析 → 风险复核。"]
    for key in ids:
        path = SKILL_DIR / SKILLS[key]["file"]
        chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    if custom and custom.strip():
        chunks.append("# 企业自定义会计口径（优先于系统 Skill）\n" + custom.strip())
    return "\n\n".join(chunks)[:30000]
