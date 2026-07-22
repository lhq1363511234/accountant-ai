#!/usr/bin/env python3
"""站点 UI：CSS 主题 + 公开页/应用页外壳。"""
from __future__ import annotations

import html
import re
from flask import session
import config

P = config.SITE_BASE_PATH  # /account


def _with_csrf(body: str) -> str:
    """Inject a hidden CSRF token into every POST form rendered by the string-based UI."""
    token = html.escape(str(session.get("csrf_token", "")), quote=True)
    hidden = f"<input type='hidden' name='csrf_token' value='{token}'>"
    return re.sub(r"(<form\b[^>]*\bmethod=['\"]post['\"][^>]*>)", r"\1" + hidden, body, flags=re.I)


LOADING_JS = """
<script>
(function(){
  function showLoading(form){
    if(form.dataset.loading==='1') return false;
    form.dataset.loading='1';
    var btn=form.querySelector('button[type=submit],button:not([type])');
    if(btn){btn.disabled=true;btn.dataset.oldText=btn.textContent;btn.textContent='处理中…';}
    var overlay=document.getElementById('global-loading');
    if(overlay) overlay.classList.add('show');
  }
  document.addEventListener('submit',function(e){
    var form=e.target;
    if(form.matches('form') && form.method.toLowerCase()==='post') showLoading(form);
  });
  document.addEventListener('change',function(e){
    if(e.target.matches('input[type=file]')){
      var out=document.querySelector('[data-file-names]');
      if(out && e.target.files) out.textContent=Array.from(e.target.files).map(function(x){return x.name;}).join('、');
    }
  });

  function initResults(){
    var tabs=Array.from(document.querySelectorAll('[data-result-tab]'));
    var panels=Array.from(document.querySelectorAll('[data-result-panel]'));
    if(!tabs.length) return;
    function activate(name){
      tabs.forEach(function(b){b.classList.toggle('active',b.dataset.resultTab===name);});
      panels.forEach(function(p){p.classList.toggle('active',p.dataset.resultPanel===name);});
      if(history.replaceState) history.replaceState(null,'','#'+name);
      window.scrollTo({top:0,behavior:'smooth'});
    }
    tabs.forEach(function(b){b.addEventListener('click',function(){activate(b.dataset.resultTab);});});
    document.querySelectorAll('[data-go-review]').forEach(function(b){b.addEventListener('click',function(){activate('review');});});
    var initial=(location.hash||'').slice(1);
    if(['overview','charts','review'].indexOf(initial)>=0) activate(initial);

    var rows=Array.from(document.querySelectorAll('.results-table tbody tr'));
    var search=document.querySelector('[data-result-search]');
    var filters=Array.from(document.querySelectorAll('[data-result-filter]'));
    var pager=document.querySelector('[data-result-pagination]');
    var prev=document.querySelector('[data-page-prev]');
    var next=document.querySelector('[data-page-next]');
    var pageInfo=document.querySelector('[data-page-info]');
    var count=document.querySelector('[data-result-count]');
    var empty=document.querySelector('[data-empty-filter]');
    var mode=rows.some(function(r){return r.dataset.review==='1';})?'review':'all';
    var page=1;
    var pageSize=20;
    function render(){
      var q=(search&&search.value||'').trim().toLowerCase();
      var matched=rows.filter(function(r){return (mode==='all'||r.dataset.review==='1')&&(!q||(r.dataset.search||'').indexOf(q)>=0);});
      var totalPages=Math.max(1,Math.ceil(matched.length/pageSize));
      page=Math.min(Math.max(1,page),totalPages);
      var start=(page-1)*pageSize;
      var end=Math.min(start+pageSize,matched.length);
      rows.forEach(function(r){r.hidden=true;});
      matched.slice(start,end).forEach(function(r){r.hidden=false;});
      if(count) count.textContent=matched.length?('显示 '+(start+1)+'–'+end+' / '+matched.length+' 笔'):'0 笔';
      if(pageInfo) pageInfo.textContent='第 '+page+' / '+totalPages+' 页';
      if(prev) prev.disabled=page<=1;
      if(next) next.disabled=page>=totalPages;
      if(pager) pager.hidden=matched.length===0;
      if(empty) empty.hidden=matched.length!==0;
      filters.forEach(function(b){b.classList.toggle('active',b.dataset.resultFilter===mode);});
    }
    filters.forEach(function(b){b.addEventListener('click',function(){mode=b.dataset.resultFilter;page=1;render();});});
    if(search) search.addEventListener('input',function(){page=1;render();});
    if(prev) prev.addEventListener('click',function(){if(page>1){page--;render();document.querySelector('.review-card').scrollIntoView({behavior:'smooth'});}});
    if(next) next.addEventListener('click',function(){page++;render();document.querySelector('.review-card').scrollIntoView({behavior:'smooth'});});
    rows.forEach(function(r){var sel=r.querySelector('select');if(sel)sel.addEventListener('change',function(){r.classList.add('row-changed');});});
    render();
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',initResults); else initResults();
  if(window.matchMedia && window.matchMedia('(max-width: 860px)').matches){
    Array.from(document.querySelectorAll('.cf-act')).forEach(function(d,i){if(i>0)d.removeAttribute('open');});
  }
})();
</script>
"""

LOADING_HTML = "<div id='global-loading' class='loading-overlay'><div class='loading-box'><span class='spinner'></span><span>正在处理，请稍候…</span></div></div>"

CSS = """
:root{
  --bg:#f6f8fb; --panel:#ffffff; --ink:#0f172a; --muted:#64748b;
  --line:#e5e9f0; --brand:#2563eb; --brand2:#1d4ed8; --brand-soft:#eff4ff;
  --ok:#059669; --warn:#d97706; --danger:#dc2626; --radius:16px;
  --shadow:0 1px 2px rgba(15,23,42,.04),0 8px 24px rgba(15,23,42,.06);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  background:var(--bg);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:var(--brand);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
.nav{position:sticky;top:0;z-index:40;background:rgba(255,255,255,.9);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.nav .wrap{display:flex;align-items:center;justify-content:space-between;height:64px}
.brand{font-weight:800;font-size:19px;color:var(--ink);display:flex;align-items:center;gap:8px}
.brand .dot{width:10px;height:10px;border-radius:50%;background:var(--brand);display:inline-block}
.nav-links{display:flex;align-items:center;gap:8px}
.btn{display:inline-flex;align-items:center;gap:6px;padding:9px 16px;border-radius:10px;border:1px solid var(--line);
  background:#fff;color:var(--ink);font-size:14px;font-weight:600;cursor:pointer;transition:.15s;text-decoration:none}
.btn:hover{border-color:#cbd5e1;text-decoration:none}
.btn.primary{background:var(--brand);border-color:var(--brand);color:#fff}
.btn.primary:hover{background:var(--brand2)}
.btn.ghost{background:transparent;border-color:transparent;color:var(--muted)}
.btn.lg{padding:13px 26px;font-size:16px}
.btn.block{display:flex;width:100%;justify-content:center}
.hero{padding:72px 0 48px;text-align:center}
.hero .pill{display:inline-block;background:var(--brand-soft);color:var(--brand2);font-weight:600;
  font-size:13px;padding:6px 14px;border-radius:999px;margin-bottom:22px}
.hero h1{font-size:44px;line-height:1.15;margin:0 0 18px;letter-spacing:-1px;font-weight:800}
.hero h1 .g{background:linear-gradient(90deg,#2563eb,#7c3aed);-webkit-background-clip:text;background-clip:text;color:transparent}
.hero p.sub{font-size:19px;color:var(--muted);max-width:640px;margin:0 auto 30px}
.hero .cta{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
.section{padding:56px 0}
.section h2{font-size:30px;text-align:center;margin:0 0 8px;font-weight:800}
.section .lead{text-align:center;color:var(--muted);max-width:620px;margin:0 auto 40px;font-size:17px}
.grid{display:grid;gap:20px}
.grid.c3{grid-template-columns:repeat(3,1fr)}
.grid.c4{grid-template-columns:repeat(4,1fr)}
.grid.c2{grid-template-columns:repeat(2,1fr)}
@media(max-width:860px){.grid.c3,.grid.c4,.grid.c2{grid-template-columns:1fr}.hero h1{font-size:32px}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:24px;box-shadow:var(--shadow)}
.card h3{margin:0 0 8px;font-size:18px}
.card p{margin:0;color:var(--muted);font-size:14.5px}
.feat .ic{width:44px;height:44px;border-radius:12px;background:var(--brand-soft);display:flex;align-items:center;
  justify-content:center;font-size:22px;margin-bottom:14px}
.steps{counter-reset:s}
.steps .card{position:relative}
.steps .card::before{counter-increment:s;content:counter(s);position:absolute;top:-14px;left:20px;width:30px;height:30px;
  border-radius:50%;background:var(--brand);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700}
.price-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;align-items:stretch}
@media(max-width:860px){.price-grid{grid-template-columns:1fr}}
.plan{background:#fff;border:1px solid var(--line);border-radius:var(--radius);padding:28px 24px;display:flex;flex-direction:column;box-shadow:var(--shadow)}
.plan.hot{border:2px solid var(--brand);position:relative}
.plan.hot .tag{position:absolute;top:-12px;right:20px;background:var(--brand);color:#fff;font-size:12px;font-weight:700;padding:4px 12px;border-radius:999px}
.plan h3{font-size:20px;margin:0 0 4px}
.plan .price{font-size:38px;font-weight:800;margin:12px 0 2px}
.plan .price small{font-size:15px;color:var(--muted);font-weight:500}
.plan ul{list-style:none;padding:0;margin:18px 0;flex:1}
.plan li{padding:7px 0 7px 26px;position:relative;font-size:14.5px;color:#334155}
.plan li::before{content:"✓";position:absolute;left:0;color:var(--ok);font-weight:800}
footer{border-top:1px solid var(--line);padding:32px 0;color:var(--muted);font-size:13.5px;text-align:center;background:#fff}
.err{background:#fef2f2;border:1px solid #fecaca;color:#b91c1c;padding:11px 14px;border-radius:12px;margin:12px 0;font-size:14px}
.ok{background:#ecfdf5;border:1px solid #a7f3d0;color:#047857;padding:11px 14px;border-radius:12px;margin:12px 0;font-size:14px}
label{display:block;font-size:14px;font-weight:600;margin:14px 0 6px}
input[type=text],input[type=email],input[type=password],input[type=search],textarea,select{
  width:100%;padding:11px 13px;border:1px solid var(--line);border-radius:11px;font-size:15px;background:#fff;font-family:inherit}
input:focus,textarea:focus,select:focus{outline:none;border-color:var(--brand);box-shadow:0 0 0 3px var(--brand-soft)}
input[type=file]{width:100%;padding:11px;border:1.5px dashed #cbd5e1;border-radius:12px;background:#fafbfc}
.muted{color:var(--muted)}
.file-names{margin-top:8px;font-size:13px;min-height:22px;overflow-wrap:anywhere}
button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid rgba(37,99,235,.35);outline-offset:2px}
@media (prefers-reduced-motion: reduce){*,*::before,*::after{scroll-behavior:auto!important;animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}
.auth{max-width:420px;margin:48px auto}
.auth .card{padding:32px}
.auth h1{font-size:24px;margin:0 0 6px}
/* App shell */
.app{display:flex;min-height:calc(100vh - 64px)}
.side{width:230px;flex:none;background:#fff;border-right:1px solid var(--line);padding:20px 14px}
.side a{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:10px;color:#334155;font-weight:600;font-size:14.5px;margin-bottom:4px}
.side a:hover{background:var(--bg);text-decoration:none}
.side a.on{background:var(--brand-soft);color:var(--brand2)}
.main{flex:1;padding:28px 32px;min-width:0}
.main h1{font-size:24px;margin:0 0 4px}
.pagehead{margin-bottom:22px}
.pagehead p{color:var(--muted);margin:4px 0 0}
.quota{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:22px}
.stat{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px 20px;min-width:150px;box-shadow:var(--shadow)}
.stat .n{font-size:26px;font-weight:800}
.stat .l{color:var(--muted);font-size:13px}
.bar{height:8px;background:var(--bg);border-radius:999px;overflow:hidden;margin-top:8px}
.bar>i{display:block;height:100%;background:var(--brand)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:9px 11px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:#f8fafc;font-weight:700;color:#475569;font-size:13px;white-space:nowrap}
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px;max-height:560px}
.tag-s{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600}
.tag-review{background:#fffbeb;color:#b45309}
.tag-ok{background:#ecfdf5;color:#047857}
.pill-plan{display:inline-block;background:var(--brand-soft);color:var(--brand2);font-weight:700;font-size:12px;padding:3px 10px;border-radius:999px}
pre.doc{white-space:pre-wrap;max-height:340px;overflow:auto;background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px;font-size:13px}
.empty{text-align:center;color:var(--muted);padding:48px 20px}
.chat-q{font-weight:700;margin:0 0 8px}
.chat-a{white-space:pre-wrap;line-height:1.8}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-block;background:var(--brand-soft);color:var(--brand2);font-size:12px;font-weight:600;padding:5px 11px;border-radius:999px;border:1px solid #dbe6ff}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.num.in{color:var(--ok)}
.num.out{color:var(--danger)}
.alert{border-radius:12px;padding:12px 14px;margin:0 0 16px;font-size:14px;border:1px solid}
.alert.ok{background:#ecfdf5;border-color:#a7f3d0;color:#065f46}
.alert.warn{background:#fffbeb;border-color:#fde68a;color:#92400e}
.alert.err{background:#fef2f2;border-color:#fecaca;color:#991b1b}
.tbl{width:100%;border-collapse:collapse;font-size:13px}
.tbl th{position:sticky;top:0;background:#f8fafc;text-align:left;font-weight:700;color:#475569;padding:9px 10px;border-bottom:2px solid var(--line);white-space:nowrap}
.tbl td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
.tbl tbody tr:hover{background:#fafcff}
.tbl select{width:100%;min-width:150px;padding:5px 6px;border:1px solid var(--line);border-radius:8px;font-size:12px;background:#fff}
.cf-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:4px 0 6px}
.cf-act-summary{display:flex;align-items:center;justify-content:space-between;gap:12px;cursor:pointer;list-style:none;font-size:15px;font-weight:800;color:#334155;min-height:30px}.cf-act-summary::-webkit-details-marker{display:none}.cf-act-summary::after{content:'展开';font-size:11px;color:var(--muted);font-weight:600}.cf-act[open] .cf-act-summary::after{content:'收起'}.cf-act-title{font-size:12px;color:var(--muted);margin:12px 0 4px}.cf-act:not([open]){padding-bottom:13px}

.cf-act{border:1px solid var(--line);border-radius:14px;padding:14px 16px;background:#fff}
.cf-act h4{margin:0 0 10px;font-size:14px;color:#334155;display:flex;justify-content:space-between;align-items:center}
.cf-act .net{font-size:15px;font-weight:800;font-variant-numeric:tabular-nums}
.cf-line{display:flex;justify-content:space-between;gap:10px;font-size:12px;color:#475569;padding:4px 0;border-top:1px dashed #eef2f7}
.cf-line span:last-child{font-variant-numeric:tabular-nums;white-space:nowrap}
.cf-line.out span:first-child{color:#9a3412}
.cf-total{display:flex;justify-content:space-between;align-items:center;margin-top:12px;padding:14px 16px;background:linear-gradient(135deg,#eff6ff,#eef2ff);border:1px solid #dbe6ff;border-radius:14px}
.cf-total .big{font-size:22px;font-weight:800;font-variant-numeric:tabular-nums;color:var(--brand2)}
.pos{color:var(--ok)}
.neg{color:var(--danger)}
.kpi{display:flex;gap:18px;flex-wrap:wrap}
.kpi .item{flex:1;min-width:120px}
.kpi .item .v{font-size:20px;font-weight:800}
.kpi .item .l{font-size:12px;color:var(--muted)}

/* ===== 图表看板 ===== */
.dash-grid{display:grid;grid-template-columns:repeat(12,1fr);gap:16px}
.dash-grid .card{margin:0}
.col-4{grid-column:span 4}.col-6{grid-column:span 6}.col-8{grid-column:span 8}.col-12{grid-column:span 12}
@media(max-width:920px){.col-4,.col-6,.col-8{grid-column:span 12}}
.card h3.chart-title{margin:0 0 4px;font-size:15px}
.card .chart-sub{color:var(--muted);font-size:12px;margin:0 0 12px}
.svg-chart{max-width:100%;height:auto;display:block}
.chart-empty{color:var(--muted);font-size:13px;text-align:center;padding:34px 10px;background:#f8fafc;border:1px dashed var(--line);border-radius:12px}
.donut-wrap{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.donut-wrap .svg-chart{flex:0 0 auto}
.legend{flex:1;min-width:150px;display:flex;flex-direction:column;gap:7px}
.lg-item{display:flex;align-items:center;gap:8px;font-size:12.5px}
.lg-dot{width:11px;height:11px;border-radius:3px;flex:0 0 auto}
.lg-name{flex:1;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lg-val{color:var(--muted);font-variant-numeric:tabular-nums;font-weight:600}
.chart-legend{display:flex;gap:16px;justify-content:center;margin-top:8px;font-size:12px;color:var(--muted)}
.chart-legend span{display:inline-flex;align-items:center;gap:6px}
.chart-legend i,.inout-legend i{width:11px;height:11px;border-radius:3px;display:inline-block}
.inout{margin-top:4px}
.inout-bar{display:flex;height:26px;border-radius:8px;overflow:hidden;background:#f1f5f9}
.inout-in{background:var(--ok)}.inout-out{background:var(--danger)}
.inout-legend{display:flex;gap:18px;margin-top:10px;font-size:12.5px;color:var(--muted)}
.inout-legend span{display:inline-flex;align-items:center;gap:6px}
.kpi-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
@media(max-width:920px){.kpi-cards{grid-template-columns:repeat(2,1fr)}}
.kpi-card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px;box-shadow:var(--shadow)}
.kpi-card .v{font-size:24px;font-weight:800;font-variant-numeric:tabular-nums;line-height:1.1}
.kpi-card .l{font-size:12.5px;color:var(--muted);margin-top:6px}
.kpi-card .s{font-size:11.5px;color:var(--muted);margin-top:2px}
/* ---- 图表看板 ---- */
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:16px}
.kpi-card{background:linear-gradient(135deg,#f8fafc,#f1f5f9);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.kpi-card .k-l{font-size:12px;color:var(--muted)}
.kpi-card .k-v{font-size:22px;font-weight:800;font-variant-numeric:tabular-nums;margin:2px 0}
.kpi-card .k-s{font-size:11px}
.chart-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin-bottom:16px}
.chart-box{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px}
.chart-box.full{margin-bottom:16px}
.chart-title{font-size:13px;font-weight:700;color:var(--ink);margin-bottom:12px}
.svg-chart{display:block;max-width:100%;height:auto}
.chart-empty{color:var(--muted);font-size:13px;text-align:center;padding:32px 12px;background:#f8fafc;border-radius:10px}
.donut-wrap{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.donut-wrap .legend{flex:1;min-width:150px;display:flex;flex-direction:column;gap:6px}
.lg-item{display:flex;align-items:center;gap:8px;font-size:12px}
.lg-dot{width:10px;height:10px;border-radius:3px;flex:none}
.lg-name{flex:1;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lg-val{color:var(--muted);font-variant-numeric:tabular-nums}
.chart-legend{display:flex;gap:16px;justify-content:center;margin-top:8px;font-size:12px;color:var(--muted)}
.chart-legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:middle}
.inout{padding:8px 0}
.inout-bar{display:flex;height:32px;border-radius:8px;overflow:hidden;background:#f1f5f9}
.inout-in{background:#059669}
.inout-out{background:#dc2626}
.inout-legend{display:flex;justify-content:space-between;margin-top:12px;font-size:13px;color:var(--ink);flex-wrap:wrap;gap:8px}
.inout-legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:middle}


/* ===== Human-centered task and result information architecture ===== */
.page-head{display:flex;align-items:center;justify-content:space-between;gap:18px;margin:0 0 20px}
.page-head p{margin:3px 0 0}.section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:16px}
.section-head h2,.section-head h3{margin:0}.section-head p{margin:3px 0 0}.text-link{font-size:14px;font-weight:700;white-space:nowrap}
.cards-4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:16px}.cards-3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.stat-label{font-size:12px;color:var(--muted)}.stat-val{font-size:24px;font-weight:800;line-height:1.25;margin:4px 0;overflow-wrap:anywhere}
.usage-copy{display:flex;justify-content:space-between;gap:12px;font-size:13px;margin-bottom:8px}.usage-bar{height:9px;background:#e8edf5;border-radius:99px;overflow:hidden;margin-bottom:9px}.usage-bar span{display:block;height:100%;background:var(--brand);border-radius:99px}
.desktop-only{display:block}.mobile-only{display:none}.compact-table{max-height:none}.filename-cell{max-width:360px;overflow-wrap:anywhere;word-break:break-word}.row-actions{display:flex;align-items:center;gap:6px}.row-actions form{margin:0}
.danger-soft{color:#b91c1c;background:#fff;border-color:#fecaca}.danger-soft:hover{background:#fef2f2;border-color:#fca5a5}.empty-row{text-align:center!important;padding:28px!important}
.task-list{display:grid;gap:12px}.task-card{background:#fff;border:1px solid var(--line);border-radius:15px;padding:15px;box-shadow:var(--shadow);min-width:0}
.task-card-top{display:flex;align-items:center;justify-content:space-between;gap:10px}.task-kind{font-size:12px;font-weight:700;color:var(--brand2);background:var(--brand-soft);padding:3px 9px;border-radius:999px}
.task-filename{font-size:16px!important;line-height:1.45!important;margin:12px 0 10px!important;overflow-wrap:anywhere;word-break:break-word;white-space:normal}
.task-meta{display:flex;align-items:center;justify-content:space-between;gap:10px;color:var(--muted);font-size:13px;padding-top:10px;border-top:1px solid #f1f5f9}.task-meta b{color:var(--ink)}
.task-actions{display:flex;gap:8px;margin-top:13px}.task-actions>a{flex:1;justify-content:center}.task-actions form{margin:0}.task-actions form .btn{height:100%}
.empty-state{text-align:center;padding:34px 18px;background:#fff;border:1px dashed #cbd5e1;border-radius:14px}.empty-state h3{margin:0 0 5px}.empty-state p{margin:0 0 16px;color:var(--muted)}
.filename-context{max-width:70vw;overflow-wrap:anywhere}.result-tabs{display:flex;gap:6px;padding:5px;background:#e9eef6;border-radius:13px;margin:0 0 16px;position:sticky;top:72px;z-index:18}
.result-tab{flex:1;min-height:44px;border:0;background:transparent;border-radius:9px;color:#526071;font:inherit;font-size:14px;font-weight:700;cursor:pointer;padding:8px 12px}.result-tab.active{background:#fff;color:var(--brand2);box-shadow:0 1px 4px rgba(15,23,42,.1)}.result-tab span{display:inline-flex;min-width:20px;height:20px;align-items:center;justify-content:center;border-radius:99px;background:#fff;color:#b45309;font-size:11px;margin-left:3px}.result-tab.active span{background:#fff7ed}
.result-panel{display:none}.result-panel.active{display:block}.action-grid{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}.review-tools{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;margin-bottom:14px}.search-box{margin:0;flex:1;max-width:420px}.search-box span{display:block;font-size:12px;color:var(--muted);margin-bottom:5px}.filter-group{display:flex;background:#f1f5f9;padding:4px;border-radius:10px}.filter-btn{border:0;background:transparent;color:#64748b;border-radius:8px;min-height:38px;padding:7px 12px;font-weight:700;cursor:pointer}.filter-btn.active{background:#fff;color:var(--brand2);box-shadow:0 1px 3px rgba(15,23,42,.1)}
.review-counter{font-size:12px;color:var(--muted);white-space:nowrap}.reason-cell details{font-size:12px}.reason-cell summary{color:var(--brand2);font-weight:700;cursor:pointer}.reason-cell details div{margin-top:6px;line-height:1.65;color:#64748b}.result-pagination{display:flex;align-items:center;justify-content:center;gap:14px;margin:16px 0 2px}.result-pagination span{min-width:90px;text-align:center;color:var(--muted);font-size:13px;font-weight:700}.result-pagination .btn:disabled{opacity:.45;cursor:not-allowed}.empty-filter{text-align:center;padding:32px 16px;color:var(--muted)}.save-bar{display:flex;align-items:center;justify-content:flex-end;gap:14px;margin-top:14px}.results-table tr.row-changed{background:#fffdf2}

@media (max-width: 860px){
  .nav .wrap{padding:0 12px}.nav-links{gap:2px}.nav-links>a.ghost:first-child{display:none}.nav-links .btn{padding:8px 10px;font-size:13px}.nav-links .muted,.pill-plan{display:none}
  .app{display:block}.side{width:100%;display:flex;gap:6px;overflow-x:auto;padding:8px 12px;border-right:0;border-bottom:1px solid var(--line);position:sticky;top:64px;z-index:20;background:#fff;scrollbar-width:none}
  .side::-webkit-scrollbar{display:none}.side a{flex:0 0 auto;margin:0;padding:10px 12px;min-height:44px}.main{padding:16px 12px;max-width:100vw;overflow:hidden}
  .desktop-only{display:none!important}.mobile-only{display:block}.cards-4{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.cards-3,.cf-grid,.chart-grid{grid-template-columns:1fr}
  .page-head{gap:10px;align-items:flex-start;flex-wrap:wrap;margin-bottom:16px}.page-head>div{min-width:0;flex:1}.page-head>.btn{flex:none}.filename-context{max-width:100%;font-size:13px;overflow-wrap:anywhere}
  .card{padding:16px;border-radius:14px}.main h1{font-size:22px}.main h2{font-size:18px}.stat{min-width:0;padding:13px}.stat-val{font-size:20px}.quota-card{padding:14px}.task-section{padding:15px}
  .task-card{width:100%;overflow:hidden}.task-actions .btn{min-height:44px}.section-head{align-items:flex-start}.section-head>div{min-width:0}.section-head p{line-height:1.45}
  .result-tabs{top:12px;margin-left:-4px;margin-right:-4px;overflow-x:auto}.result-tab{padding:7px 8px;white-space:nowrap}.result-tab span{margin-left:1px}.result-panel>.card,.result-panel .card{margin-bottom:12px}
  .action-grid{display:grid;grid-template-columns:1fr 1fr}.action-grid .btn{justify-content:center}.review-tools{display:block}.search-box{max-width:none}.filter-group{margin-top:10px}.filter-btn{flex:1}.review-counter{display:none}
  .table-wrap{max-width:100%;-webkit-overflow-scrolling:touch}.btn{min-height:44px}.btn.sm{min-height:38px}.results-table{min-width:0}.results-scroll{overflow:visible;border:0;max-height:none}
  .results-table,.results-table tbody,.results-table tr,.results-table td{display:block;width:100%}.results-table thead{display:none}
  .results-table tr{background:#fff;border:1px solid var(--line);border-radius:13px;margin:0 0 12px;padding:10px 12px;box-shadow:0 2px 8px rgba(15,23,42,.04)}
  .results-table td{display:grid;grid-template-columns:72px minmax(0,1fr);gap:10px;padding:8px 0;border-bottom:1px solid #f1f5f9;min-height:40px;text-align:left;overflow-wrap:anywhere}
  .results-table td:last-child{border-bottom:0}.results-table td::before{content:attr(data-label);font-weight:700;color:#64748b;font-size:12px}.results-table td.num{text-align:left}.results-table td select{min-width:0;width:100%;padding:10px}.results-table .summary-cell{font-size:15px;font-weight:700;color:var(--ink)}.results-table .amount-cell{font-size:17px;font-weight:800}.reason-cell{max-width:none!important}.source-cell{font-size:12px!important}
  .result-pagination{justify-content:space-between;gap:8px}.result-pagination .btn{padding:8px 14px}.result-pagination span{min-width:78px}.save-bar{position:sticky;bottom:8px;background:rgba(255,255,255,.96);border:1px solid var(--line);border-radius:13px;padding:8px;box-shadow:0 8px 30px rgba(15,23,42,.16);z-index:16}.save-bar .muted{display:none}.save-bar .btn{width:100%;justify-content:center}
  .kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.kpi-card{padding:12px}.kpi-card .k-v{font-size:18px}.chart-box{padding:12px;overflow:hidden}.svg-chart{width:100%;height:auto}.inout-legend{display:block}.inout-legend span{display:flex;margin:6px 0}
}

.loading-overlay{display:none;position:fixed;inset:0;background:rgba(15,23,42,.22);z-index:100;align-items:center;justify-content:center}
.loading-overlay.show{display:flex}
.loading-box{display:flex;align-items:center;gap:10px;background:#fff;border-radius:14px;padding:16px 20px;box-shadow:0 12px 40px rgba(15,23,42,.22);font-size:14px;font-weight:600}
.spinner{width:18px;height:18px;border:3px solid #dbeafe;border-top-color:var(--brand);border-radius:50%;animation:spin .75s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

"""


def public_shell(title: str, body: str, user=None) -> str:
    if user:
        right = f"<a class='btn ghost' href='{P}/app'>控制台</a><a class='btn' href='{P}/logout'>退出</a>"
    else:
        right = f"<a class='btn ghost' href='{P}/login'>登录</a><a class='btn primary' href='{P}/register'>免费开始</a>"
    body = _with_csrf(body)
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>
<style>{CSS}</style></head><body>
<nav class='nav'><div class='wrap'>
<a class='brand' href='{P}/'><span class='dot'></span>{html.escape(config.SITE_NAME)}</a>
<div class='nav-links'>
<a class='btn ghost' href='{P}/#features'>功能</a>
<a class='btn ghost' href='{P}/pricing'>定价</a>
{right}
</div></div></nav>
{LOADING_HTML}{body}
{LOADING_JS}<footer>{html.escape(config.SITE_NAME)} · 银行流水智能分类，依据《企业会计准则第31号——现金流量表》口径整理，结果需会计人工复核 · 数据仅存于本服务器</footer>
</body></html>"""


def app_shell(title: str, active: str, body: str, user=None, quota=None) -> str:
    def item(key, href, icon, label):
        on = "on" if active == key else ""
        return f"<a class='{on}' href='{href}'>{icon} {label}</a>"
    plan_pill = f"<span class='pill-plan'>{quota['plan_name']}</span>" if quota else ""
    email = html.escape(user.email) if user else ""
    side = (
        item("dashboard", f"{P}/app", "📊", "控制台") +
        item("upload", f"{P}/app/upload", "⬆️", "上传处理") +
        item("jobs", f"{P}/app/jobs", "📁", "历史任务") +
        item("skill", f"{P}/app/skill", "📖", "财务 Skill") +
        item("pricing", f"{P}/pricing", "💎", "套餐升级") +
        (item("admin", f"{P}/app/admin", "🛠️", "管理后台") if user and user.is_admin else "")
    )
    body = _with_csrf(body)
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)} · {html.escape(config.SITE_NAME)}</title>
<style>{CSS}</style></head><body>
<nav class='nav'><div class='wrap'>
<a class='brand' href='{P}/app'><span class='dot'></span>{html.escape(config.SITE_NAME)}</a>
<div class='nav-links'>{plan_pill}<span class='muted' style='font-size:13px'>{email}</span>
<a class='btn ghost' href='{P}/'>官网</a><a class='btn' href='{P}/logout'>退出</a></div>
</div></nav>
<div class='app'><aside class='side'>{side}</aside><main class='main'>{body}</main></div>
{LOADING_HTML}{LOADING_JS}
</body></html>"""
