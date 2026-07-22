"""Runtime AI provider settings with root-only file persistence.

The API key never goes into SQLite, HTML, logs, or the Git repository.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

import config

_LOCK = threading.Lock()


def _path() -> Path:
    return Path(getattr(config, "AI_SETTINGS_PATH", "/etc/account-ai-ai.json"))


def normalize_base_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        raise ValueError("API 地址不能为空")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("API 地址格式不正确")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("远程 API 必须使用 HTTPS")
    if not parsed.path or parsed.path == "/":
        value += "/v1"
    return value.rstrip("/")


def defaults() -> dict[str, Any]:
    return {
        "provider": "环境变量",
        "base_url": config.AI_BASE.rstrip("/"),
        "api_key": config.AI_KEY,
        "model": config.AI_MODEL,
        "display_name": config.AI_MODEL_NAME,
        "enabled": bool(config.AI_KEY and config.AI_MODEL),
        "updated_at": 0,
    }


def _read_store() -> dict[str, Any]:
    try:
        saved = json.loads(_path().read_text(encoding="utf-8"))
        return saved if isinstance(saved, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _merge_settings(saved: Any) -> dict[str, Any]:
    data = defaults()
    if isinstance(saved, dict):
        data.update({k: saved[k] for k in data if k in saved})
    return data


def load_settings() -> dict[str, Any]:
    """Return active settings used by the classification engine."""
    store = _read_store()
    if "active" in store or "draft" in store:
        return _merge_settings(store.get("active"))
    return _merge_settings(store)


def load_draft() -> dict[str, Any]:
    store = _read_store()
    if "active" in store or "draft" in store:
        return _merge_settings(store.get("draft") or store.get("active"))
    return _merge_settings(store)


def _mask(data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data)
    key = str(data.get("api_key") or "")
    data["key_configured"] = bool(key)
    data["masked_key"] = (key[:5] + "••••••••" + key[-4:]) if len(key) >= 12 else ("已配置" if key else "未配置")
    data.pop("api_key", None)
    return data


def public_settings() -> dict[str, Any]:
    return _mask(load_settings())


def admin_public_settings() -> dict[str, Any]:
    draft = _mask(load_draft())
    active = public_settings()
    draft["active_enabled"] = bool(active.get("enabled") and active.get("key_configured") and active.get("model"))
    draft["active_provider"] = active.get("provider")
    draft["active_model"] = active.get("model")
    draft["active_display_name"] = active.get("display_name")
    return draft


def build_candidate(form: dict[str, str], *, keep_existing_key: bool = True, require_model: bool = True) -> dict[str, Any]:
    current = load_draft()
    key = (form.get("api_key") or "").strip()
    if not key and keep_existing_key:
        key = str(current.get("api_key") or "")
    provider = (form.get("provider") or "OpenAI 兼容平台").strip()[:80]
    model = (form.get("model") or "").strip()[:160]
    display = (form.get("display_name") or model or provider).strip()[:120]
    base = normalize_base_url(form.get("base_url") or "")
    if not key:
        raise ValueError("API Key 不能为空")
    if require_model and not model:
        raise ValueError("模型名称不能为空")
    return {
        "provider": provider,
        "base_url": base,
        "api_key": key,
        "model": model,
        "display_name": display,
        "enabled": bool(model),
        "updated_at": int(__import__("time").time()),
    }


def _write_store(store: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with _LOCK:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(store, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(str(tmp), str(path))
            os.chmod(str(path), 0o600)
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass


def save_settings(data: dict[str, Any]) -> None:
    """Activate a tested configuration and mirror it to the editable draft."""
    payload = {k: data.get(k) for k in defaults()}
    store = _read_store()
    if "active" not in store and "draft" not in store:
        store = {}
    store["active"] = payload
    store["draft"] = dict(payload)
    _write_store(store)


def save_draft(data: dict[str, Any]) -> None:
    payload = {k: data.get(k) for k in defaults()}
    store = _read_store()
    if "active" not in store and "draft" not in store:
        legacy = _merge_settings(store) if store else defaults()
        store = {"active": {k: legacy.get(k) for k in defaults()}}
    store["draft"] = payload
    _write_store(store)


def disable_active() -> None:
    active = load_settings()
    active["enabled"] = False
    store = _read_store()
    if "active" not in store and "draft" not in store:
        store = {}
    store["active"] = {k: active.get(k) for k in defaults()}
    store.setdefault("draft", dict(store["active"]))
    _write_store(store)


def list_models(base_url: str, api_key: str) -> list[str]:
    response = requests.get(
        normalize_base_url(base_url) + "/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=(8, 30),
    )
    response.raise_for_status()
    payload = response.json()
    return sorted({str(x.get("id")) for x in (payload.get("data") or []) if isinstance(x, dict) and x.get("id")})


def test_connection(data: dict[str, Any]) -> dict[str, Any]:
    base = normalize_base_url(str(data.get("base_url") or ""))
    key = str(data.get("api_key") or "")
    model = str(data.get("model") or "").strip()
    if not key:
        return {"ok": False, "message": "API Key 不能为空", "models": []}
    model_list_error = ""
    try:
        models = list_models(base, key)
    except Exception as exc:
        models = []
        model_list_error = f"模型列表请求失败：{type(exc).__name__}"
    if not model:
        message = f"发现 {len(models)} 个模型" if models else (model_list_error or "认证成功，但平台返回 0 个可用模型")
        return {"ok": bool(models), "message": message, "models": models}
    try:
        response = requests.post(
            base + "/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply exactly: OK"}],
                "temperature": 0,
                "max_tokens": 8,
            },
            timeout=(8, 45),
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", {}).get("message")
            except Exception:
                detail = None
            return {"ok": False, "message": (detail or f"HTTP {response.status_code}")[:240], "models": models}
        return {"ok": True, "message": "连接和模型调用成功", "models": models}
    except Exception as exc:
        return {"ok": False, "message": f"模型调用失败：{type(exc).__name__}", "models": models}
