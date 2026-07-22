"""Registration mail adapter for the local Toolkit SMTP Console."""
from __future__ import annotations

import html
import requests

import config


def send_verification_email(to: str, code: str) -> None:
    subject = "现金流 AI 注册验证码"
    text = (
        f"你好，你正在注册{config.SITE_NAME}。\n\n"
        f"你的邮箱验证码是：{code}\n\n"
        f"验证码 {config.EMAIL_VERIFY_TTL // 60} 分钟内有效。若不是本人操作，请忽略此邮件。"
    )
    safe_code = html.escape(code)
    safe_name = html.escape(config.SITE_NAME)
    body_html = (
        f"<div style='font-family:Arial,sans-serif;line-height:1.7;color:#0f172a'>"
        f"<h2>{safe_name} 注册验证</h2><p>你好，你正在注册{safe_name}。</p>"
        f"<p style='font-size:28px;font-weight:800;letter-spacing:6px;color:#2563eb'>{safe_code}</p>"
        f"<p>验证码 {config.EMAIL_VERIFY_TTL // 60} 分钟内有效。若不是本人操作，请忽略此邮件。</p></div>"
    )
    response = requests.post(
        config.MAIL_API_URL,
        json={
            "to": [to],
            "subject": subject,
            "text": text,
            "html": body_html,
            "from_name": config.MAIL_FROM_NAME,
        },
        timeout=(5, 30),
    )
    try:
        payload = response.json()
    except Exception:
        payload = {}
    if response.status_code >= 400 or not payload.get("ok"):
        detail = payload.get("error") or response.text[:200] or "SMTP 发信失败"
        raise RuntimeError(str(detail))
