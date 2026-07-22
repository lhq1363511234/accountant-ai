#!/usr/bin/env python3
"""纯 SVG 图表生成（不依赖任何前端库/CDN）。
所有函数返回内联 SVG 字符串，可直接嵌入 HTML。"""
from __future__ import annotations

import html
import math
from typing import Any, Dict, List

# 与主题一致的配色
PALETTE = [
    "#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed",
    "#0891b2", "#db2777", "#65a30d", "#ea580c", "#4f46e5",
    "#0d9488", "#c026d3",
]
INK = "#0f172a"
MUTED = "#64748b"
LINE = "#e5e9f0"
POS = "#059669"
NEG = "#dc2626"


def _fmt(v: float) -> str:
    try:
        v = float(v)
    except Exception:
        return str(v)
    if abs(v) >= 1_0000_0000:
        return f"{v/1_0000_0000:.2f}亿"
    if abs(v) >= 1_0000:
        return f"{v/1_0000:.2f}万"
    return f"{v:,.0f}"


def _esc(s: Any) -> str:
    return html.escape(str(s))


def empty(msg: str = "暂无数据") -> str:
    return f"<div class='chart-empty'>{_esc(msg)}</div>"


# ---------------- 环形图 ----------------
def donut(data: List[Dict[str, Any]], *, size: int = 220, hole: float = 0.62,
          value_key: str = "amount", label_key: str = "name",
          center_title: str = "", center_value: str = "", max_items: int = 8) -> str:
    items = [d for d in data if float(d.get(value_key) or 0) > 0]
    if not items:
        return empty()
    # 合并超出部分为“其他”
    if len(items) > max_items:
        head = items[:max_items - 1]
        rest = items[max_items - 1:]
        other = sum(float(d.get(value_key) or 0) for d in rest)
        head.append({label_key: "其他", value_key: other})
        items = head
    total = sum(float(d.get(value_key) or 0) for d in items)
    if total <= 0:
        return empty()

    cx = cy = size / 2
    r = size / 2 - 6
    ir = r * hole
    stroke = r - ir
    rad = (r + ir) / 2
    circ = 2 * math.pi * rad

    segs = []
    offset = 0.0
    legend = []
    for i, d in enumerate(items):
        val = float(d.get(value_key) or 0)
        frac = val / total
        color = PALETTE[i % len(PALETTE)]
        dash = frac * circ
        gap = circ - dash
        segs.append(
            f"<circle cx='{cx}' cy='{cy}' r='{rad:.2f}' fill='none' "
            f"stroke='{color}' stroke-width='{stroke:.2f}' "
            f"stroke-dasharray='{dash:.2f} {gap:.2f}' "
            f"stroke-dashoffset='{-offset:.2f}' transform='rotate(-90 {cx} {cy})'>"
            f"<title>{_esc(d.get(label_key))}: {_fmt(val)} ({frac*100:.1f}%)</title></circle>"
        )
        offset += dash
        pct = f"{frac*100:.1f}%"
        legend.append(
            f"<div class='lg-item'><span class='lg-dot' style='background:{color}'></span>"
            f"<span class='lg-name' title='{_esc(d.get(label_key))}'>{_esc(d.get(label_key))}</span>"
            f"<span class='lg-val'>{pct}</span></div>"
        )

    ctext = ""
    if center_title or center_value:
        ctext = (
            f"<text x='{cx}' y='{cy-6}' text-anchor='middle' font-size='12' fill='{MUTED}'>{_esc(center_title)}</text>"
            f"<text x='{cx}' y='{cy+16}' text-anchor='middle' font-size='18' font-weight='700' fill='{INK}'>{_esc(center_value)}</text>"
        )
    svg = (
        f"<svg viewBox='0 0 {size} {size}' width='{size}' height='{size}' class='svg-chart'>"
        f"{''.join(segs)}{ctext}</svg>"
    )
    return f"<div class='donut-wrap'>{svg}<div class='legend'>{''.join(legend)}</div></div>"


# ---------------- 水平条形图 ----------------
def hbar(data: List[Dict[str, Any]], *, value_key: str = "amount", label_key: str = "name",
         width: int = 460, bar_h: int = 26, gap: int = 10, color: str = "#2563eb",
         sub_key: str = "") -> str:
    items = [d for d in data if float(d.get(value_key) or 0) != 0]
    if not items:
        return empty()
    maxv = max(abs(float(d.get(value_key) or 0)) for d in items) or 1
    label_w = 150
    bar_area = width - label_w - 90
    rows = []
    y = 0
    for i, d in enumerate(items):
        val = float(d.get(value_key) or 0)
        w = max(2, abs(val) / maxv * bar_area)
        c = color if isinstance(color, str) else PALETTE[i % len(PALETTE)]
        name = _esc(d.get(label_key))
        sub = ""
        if sub_key and d.get(sub_key) is not None:
            sub = f" · {_esc(d.get(sub_key))}笔"
        rows.append(
            f"<g transform='translate(0 {y})'>"
            f"<text x='{label_w-8}' y='{bar_h/2+4}' text-anchor='end' font-size='12' fill='{INK}'>"
            f"{name[:12]}</text>"
            f"<rect x='{label_w}' y='2' width='{w:.1f}' height='{bar_h-4}' rx='5' fill='{c}'>"
            f"<title>{name}: {_fmt(val)}{sub}</title></rect>"
            f"<text x='{label_w+w+8}' y='{bar_h/2+4}' font-size='12' fill='{MUTED}'>{_fmt(val)}</text>"
            f"</g>"
        )
        y += bar_h + gap
    h = y
    return f"<svg viewBox='0 0 {width} {h}' width='100%' height='{h}' class='svg-chart'>{''.join(rows)}</svg>"


# ---------------- 分组柱状：三大活动净额 ----------------
def activity_bars(activity_net: List[Dict[str, Any]], *, width: int = 460, height: int = 240) -> str:
    items = activity_net
    if not items or all(float(d.get("net") or 0) == 0 for d in items):
        return empty("三大活动净额均为 0")
    pad_l, pad_r, pad_t, pad_b = 20, 20, 20, 40
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    vals = [float(d.get("net") or 0) for d in items]
    maxv = max(abs(v) for v in vals) or 1
    zero_y = pad_t + plot_h / 2
    scale = (plot_h / 2 - 6) / maxv
    n = len(items)
    slot = plot_w / n
    bw = min(70, slot * 0.5)
    bars = []
    # 零线
    bars.append(f"<line x1='{pad_l}' y1='{zero_y}' x2='{pad_l+plot_w}' y2='{zero_y}' stroke='{LINE}'/>")
    for i, d in enumerate(items):
        v = float(d.get("net") or 0)
        cx = pad_l + slot * i + slot / 2
        bh = abs(v) * scale
        c = POS if v >= 0 else NEG
        if v >= 0:
            y = zero_y - bh
        else:
            y = zero_y
        bars.append(
            f"<rect x='{cx-bw/2:.1f}' y='{y:.1f}' width='{bw:.1f}' height='{max(1,bh):.1f}' rx='6' fill='{c}'>"
            f"<title>{_esc(d.get('name'))}: {_fmt(v)}</title></rect>"
        )
        bars.append(f"<text x='{cx:.1f}' y='{height-pad_b+18}' text-anchor='middle' font-size='12' fill='{INK}'>{_esc(d.get('name'))}</text>")
        ty = y - 6 if v >= 0 else y + bh + 16
        bars.append(f"<text x='{cx:.1f}' y='{ty:.1f}' text-anchor='middle' font-size='12' font-weight='700' fill='{c}'>{_fmt(v)}</text>")
    return f"<svg viewBox='0 0 {width} {height}' width='100%' height='{height}' class='svg-chart'>{''.join(bars)}</svg>"


# ---------------- 趋势折线/面积图 ----------------
def trend_lines(trend: List[Dict[str, Any]], *, width: int = 720, height: int = 260) -> str:
    if not trend or len(trend) < 2:
        return empty("需要至少两个不同日期的流水才能画趋势")
    pad_l, pad_r, pad_t, pad_b = 54, 20, 16, 46
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(trend)
    ins = [d["in"] for d in trend]
    outs = [d["out"] for d in trend]
    cums = [d["cumulative"] for d in trend]
    maxv = max(max(ins), max(outs), 1)
    cmin, cmax = min(cums), max(cums)
    if cmax == cmin:
        cmax = cmin + 1

    def x(i):
        return pad_l + (plot_w * i / (n - 1) if n > 1 else 0)

    def y_bar(v):
        return pad_t + plot_h - (v / maxv) * plot_h

    def y_cum(v):
        return pad_t + plot_h - ((v - cmin) / (cmax - cmin)) * plot_h

    parts = []
    # 网格线 + Y 轴刻度（金额）
    for g in range(5):
        gy = pad_t + plot_h * g / 4
        gv = maxv * (4 - g) / 4
        parts.append(f"<line x1='{pad_l}' y1='{gy:.1f}' x2='{pad_l+plot_w}' y2='{gy:.1f}' stroke='{LINE}'/>")
        parts.append(f"<text x='{pad_l-8}' y='{gy+4:.1f}' text-anchor='end' font-size='10' fill='{MUTED}'>{_fmt(gv)}</text>")

    # 柱：收入(绿)/支出(红) 并排
    bw = max(3, min(14, plot_w / n / 3))
    for i, d in enumerate(trend):
        xi = x(i)
        yi_in = y_bar(d["in"])
        yi_out = y_bar(d["out"])
        parts.append(f"<rect x='{xi-bw-1:.1f}' y='{yi_in:.1f}' width='{bw:.1f}' height='{pad_t+plot_h-yi_in:.1f}' fill='{POS}' opacity='0.75'><title>{d['date']} 流入 {_fmt(d['in'])}</title></rect>")
        parts.append(f"<rect x='{xi+1:.1f}' y='{yi_out:.1f}' width='{bw:.1f}' height='{pad_t+plot_h-yi_out:.1f}' fill='{NEG}' opacity='0.75'><title>{d['date']} 流出 {_fmt(d['out'])}</title></rect>")

    # 累计净额折线（蓝）
    pts = " ".join(f"{x(i):.1f},{y_cum(d['cumulative']):.1f}" for i, d in enumerate(trend))
    parts.append(f"<polyline points='{pts}' fill='none' stroke='#2563eb' stroke-width='2.5'/>")
    for i, d in enumerate(trend):
        parts.append(f"<circle cx='{x(i):.1f}' cy='{y_cum(d['cumulative']):.1f}' r='3' fill='#2563eb'><title>{d['date']} 累计 {_fmt(d['cumulative'])}</title></circle>")

    # X 轴标签（最多显示 ~8 个，避免拥挤）
    step = max(1, n // 8)
    for i, d in enumerate(trend):
        if i % step == 0 or i == n - 1:
            parts.append(f"<text x='{x(i):.1f}' y='{height-pad_b+18}' text-anchor='middle' font-size='10' fill='{MUTED}'>{_esc(d['date'][5:])}</text>")

    legend = (
        f"<div class='chart-legend'>"
        f"<span><i style='background:{POS}'></i>流入</span>"
        f"<span><i style='background:{NEG}'></i>流出</span>"
        f"<span><i style='background:#2563eb'></i>累计净额</span></div>"
    )
    svg = f"<svg viewBox='0 0 {width} {height}' width='100%' height='{height}' class='svg-chart'>{''.join(parts)}</svg>"
    return svg + legend


# ---------------- 收支双向对比条 ----------------
def inout_bar(total_in: float, total_out: float, *, width: int = 460) -> str:
    total = total_in + total_out
    if total <= 0:
        return empty()
    in_pct = total_in / total * 100
    out_pct = total_out / total * 100
    return (
        f"<div class='inout'>"
        f"<div class='inout-bar'>"
        f"<div class='inout-in' style='width:{in_pct:.1f}%' title='流入 {_fmt(total_in)}'></div>"
        f"<div class='inout-out' style='width:{out_pct:.1f}%' title='流出 {_fmt(total_out)}'></div>"
        f"</div>"
        f"<div class='inout-legend'>"
        f"<span><i style='background:{POS}'></i>流入 {_fmt(total_in)}（{in_pct:.0f}%）</span>"
        f"<span><i style='background:{NEG}'></i>流出 {_fmt(total_out)}（{out_pct:.0f}%）</span>"
        f"</div></div>"
    )
