#!/usr/bin/env python3
"""数据库模型：用户 / 任务 / 用量 / 订单。使用 SQLAlchemy + SQLite。"""
from __future__ import annotations

import time
import uuid
import json
from datetime import datetime, timezone

import bcrypt
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def now_ts() -> float:
    return time.time()


def gen_id(n: int = 12) -> str:
    return uuid.uuid4().hex[:n]


def current_period() -> str:
    """当前计费周期，格式 YYYY-MM（UTC）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m")


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.String(12), primary_key=True, default=gen_id)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    company = db.Column(db.String(255), default="")
    plan = db.Column(db.String(20), default="free")
    is_admin = db.Column(db.Boolean, default=False)
    # 自定义会计口径 Skill（团队版可用），空则用全局默认
    custom_skill = db.Column(db.Text, default="")
    created_at = db.Column(db.Float, default=now_ts)

    jobs = db.relationship("Job", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, raw: str):
        self.password_hash = bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def check_password(self, raw: str) -> bool:
        try:
            return bcrypt.checkpw(raw.encode("utf-8"), self.password_hash.encode("utf-8"))
        except Exception:
            return False


class Job(db.Model):
    __tablename__ = "jobs"
    id = db.Column(db.String(12), primary_key=True, default=gen_id)
    user_id = db.Column(db.String(12), db.ForeignKey("users.id"), nullable=False, index=True)
    type = db.Column(db.String(20), default="table")      # table | document
    filename = db.Column(db.String(255), default="")
    # 大块 JSON（columns/rows/results/chat/mapping/...）序列化存这里
    payload = db.Column(db.Text, default="{}")
    row_count = db.Column(db.Integer, default=0)          # 计费用：本任务处理的流水行数
    status = db.Column(db.String(20), default="created")  # created | classified | answered
    created_at = db.Column(db.Float, default=now_ts)

    def data(self) -> dict:
        try:
            d = json.loads(self.payload or "{}")
        except Exception:
            d = {}
        d.setdefault("id", self.id)
        d.setdefault("type", self.type)
        d.setdefault("filename", self.filename)
        return d

    def set_data(self, d: dict):
        self.payload = json.dumps(d, ensure_ascii=False, default=str)


class Usage(db.Model):
    """按用户+周期累计已用流水行数。"""
    __tablename__ = "usage"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.String(12), db.ForeignKey("users.id"), nullable=False, index=True)
    period = db.Column(db.String(7), nullable=False, index=True)   # YYYY-MM
    rows_used = db.Column(db.Integer, default=0)
    __table_args__ = (db.UniqueConstraint("user_id", "period", name="uq_user_period"),)


class Order(db.Model):
    """订单：套餐购买记录（支付回调预留）。"""
    __tablename__ = "orders"
    id = db.Column(db.String(16), primary_key=True, default=lambda: gen_id(16))
    user_id = db.Column(db.String(12), db.ForeignKey("users.id"), nullable=False, index=True)
    plan = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default="pending")   # pending | paid | cancelled
    pay_method = db.Column(db.String(20), default="")      # wechat | alipay | manual
    created_at = db.Column(db.Float, default=now_ts)
    paid_at = db.Column(db.Float, default=0)


class EmailVerification(db.Model):
    """注册邮箱验证码；只保存摘要，不保存明文验证码。"""
    __tablename__ = "email_verifications"
    id = db.Column(db.String(16), primary_key=True, default=lambda: gen_id(16))
    email = db.Column(db.String(255), nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    company = db.Column(db.String(255), default="")
    code_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.Float, nullable=False, index=True)
    attempts = db.Column(db.Integer, default=0)
    sent_at = db.Column(db.Float, default=now_ts)
    created_at = db.Column(db.Float, default=now_ts, index=True)
    request_ip = db.Column(db.String(64), default="", index=True)
    send_count = db.Column(db.Integer, default=1)
