#!/usr/bin/env python3
"""额度与套餐辅助：查询/累计用量、检查额度、套餐信息。"""
from __future__ import annotations

from typing import Dict, Tuple

import config
from models import db, User, Usage, current_period


def plan_of(user: User) -> Dict:
    return config.PLANS.get(user.plan, config.PLANS[config.DEFAULT_PLAN])


def get_usage(user: User) -> Usage:
    period = current_period()
    u = Usage.query.filter_by(user_id=user.id, period=period).first()
    if not u:
        u = Usage(user_id=user.id, period=period, rows_used=0)
        db.session.add(u)
        db.session.commit()
    return u


def quota_status(user: User) -> Dict:
    plan = plan_of(user)
    used = get_usage(user).rows_used
    limit = plan["rows_per_month"]
    return {
        "plan_code": plan["code"],
        "plan_name": plan["name"],
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "max_rows_per_job": plan["max_rows_per_job"],
    }


def can_process(user: User, rows: int) -> Tuple[bool, str]:
    """检查用户是否可以处理 rows 行流水。返回 (是否允许, 原因)。"""
    plan = plan_of(user)
    if rows > plan["max_rows_per_job"]:
        return False, f"当前套餐单次最多处理 {plan['max_rows_per_job']} 行，本次 {rows} 行。请拆分文件或升级套餐。"
    st = quota_status(user)
    if rows > st["remaining"]:
        return False, f"本月剩余额度 {st['remaining']} 行，本次需要 {rows} 行。请升级套餐或下月再试。"
    return True, ""


def add_usage(user: User, rows: int):
    u = get_usage(user)
    u.rows_used = (u.rows_used or 0) + max(0, rows)
    db.session.commit()
