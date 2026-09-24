from __future__ import annotations

import json
import secrets
import socket
import subprocess
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QObject, Signal
from .mobile_demo import DEMO_HTML


INDEX_HTML = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="theme-color" content="#081321">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="PUMA Mobile">
  <title>PUMA STOCK MOBILE</title>
  <link rel="manifest" href="/manifest.webmanifest">
  <link rel="icon" href="/icon.svg">
  <link rel="apple-touch-icon" href="/icon.svg">
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
<div id="pair" class="overlay">
  <div class="pair-card">
    <div class="logo">🐆</div>
    <h1>PUMA STOCK MOBILE</h1>
    <p>PC PUMA의 <b>모바일 연동</b> 탭에 표시된 6자리 연결코드를 입력하세요.</p>
    <input id="pairToken" inputmode="numeric" maxlength="6" placeholder="연결코드 6자리">
    <button class="primary" onclick="pair()">연결</button>
    <div id="pairMsg" class="muted"></div>
  </div>
</div>

<header>
  <div>
    <div class="brand">🐆 PUMA STOCK</div>
    <div id="subTitle" class="muted">PC 연결 확인 중…</div>
  </div>
  <div id="connBadge" class="badge off">OFFLINE</div>
</header>

<main>
  <section id="home" class="page active">
    <div class="grid2">
      <div class="card">
        <div class="k">PC / KIWOOM</div><div id="pcMode" class="v">-</div>
        <div id="pcStatus" class="muted">-</div>
      </div>
      <div class="card">
        <div class="k">현재 종목</div><div id="selName" class="v">-</div>
        <div id="selPrice" class="price">-</div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">통합 판정</div>
      <div id="stage" class="analysis big">데이터 대기</div>
    </div>
    <div class="card">
      <div class="card-title">활성 조건검색</div>
      <div id="homeCandidates" class="compact-list"></div>
    </div>
    <div class="card">
      <div class="card-title">최근 로그</div>
      <div id="homeLogs" class="log-list"></div>
    </div>
  </section>

  <section id="candidates" class="page">
    <div class="page-head">
      <div><b>조건검색 종목</b><div class="muted">종목을 누르면 PC PUMA도 같은 종목으로 이동</div></div>
      <button class="ghost" onclick="refreshNow()">새로고침</button>
    </div>
    <div id="candidateList" class="stock-list"></div>
  </section>

  <section id="stock" class="page">
    <div class="stock-head">
      <div><div id="stockName" class="v">종목 선택</div><div id="stockCode" class="muted">-</div></div>
      <div id="stockPrice" class="price">-</div>
    </div>
    <div class="card chart-card">
      <div class="chart-toolbar">
        <div><button id="dayBtn" class="mini active-mini" onclick="setChartMode('DAY')">일봉</button><button id="minBtn" class="mini" onclick="setChartMode('MIN')">5분</button></div>
        <span id="chartCount" class="muted">0봉</span>
      </div>
      <canvas id="chartCanvas"></canvas>
      <div class="legend">
        <span class="l112">— 112</span><span class="l224">— 224</span><span class="l448">— 448</span>
        <span>▲ 분홍/파랑/빨강/검정</span><span>🍉 수박</span>
      </div>
    </div>
    <div class="card">
      <div class="card-title">단타 DAY · 5분봉</div>
      <pre id="danta" class="analysis">-</pre>
    </div>
    <div class="card">
      <div class="card-title">역매공파 SWING</div>
      <pre id="swing" class="analysis">-</pre>
    </div>
    <div class="card">
      <div class="card-title">밥그릇3 LONG</div>
      <pre id="bowl" class="analysis">-</pre>
    </div>
  </section>

  <section id="account" class="page">
    <div class="card">
      <div class="card-title">보유 종목</div>
      <div id="positions" class="stock-list"></div>
    </div>
    <div class="card auto-card">
      <div class="card-title">자동매매</div>
      <div class="auto-status-row">
        <div><div class="k">현재 상태</div><div id="autoStatus" class="v">중지</div></div>
        <div id="autoScope" class="class-pill">-</div>
      </div>
      <div id="autoLock" class="warning">모바일 실전 잠금 해제 필요</div>
      <label>대상
        <select id="autoScopeSelect">
          <option value="ALL">전체 후보</option>
          <option value="SELECTED">현재 선택종목만</option>
        </select>
      </label>
      <label>후보 소스
        <select id="autoSource">
          <option value="WATCHLIST">관심종목</option>
          <option value="HERO4">영웅문 조건검색</option>
          <option value="BOTH">관심종목 + 조건검색</option>
        </select>
      </label>
      <div class="grid2">
        <label>종목당 투입금<input id="autoBudget" type="number" min="10000" step="10000"></label>
        <label>최대 보유종목<input id="autoMaxPositions" type="number" min="1" max="50"></label>
      </div>
      <div class="grid2">
        <label>일일 주문수<input id="autoDailyOrders" type="number" min="1" max="100"></label>
        <label>익절 %<input id="autoTP" type="number" step="0.1"></label>
      </div>
      <div class="grid2">
        <label>손절 %<input id="autoSL" type="number" step="0.1"></label>
        <label class="checklabel"><input id="autoTrailing" type="checkbox"> 트레일링 스탑</label>
      </div>
      <div class="grid2">
        <label>트레일링 시작 %<input id="autoTrailStart" type="number" step="0.1"></label>
        <label>고점대비 하락 %<input id="autoTrailGap" type="number" step="0.1"></label>
      </div>
      <button id="autoStartBtn" class="primary" onclick="startAuto()" disabled>▶ 자동매매 시작</button>
      <button class="ghost full stop-auto" onclick="stopAuto()">■ 자동매매 중지</button>
      <div class="muted small">모바일에서 실전 잠금을 최초 1회 해제하면 이후에는 추가 확인 없이 사용할 수 있습니다.</div>
    </div>
    <div class="card order-card">
      <div class="card-title">수동 주문</div>
      <div id="orderLock" class="warning">모바일 실전 잠금 해제 필요</div>
      <label>종목코드<input id="orderCode" maxlength="6" inputmode="numeric"></label>
      <div class="grid2">
        <label>구분<select id="orderSide"><option value="BUY">매수</option><option value="SELL">매도</option></select></label>
        <label>주문방식<select id="orderType"><option value="market">시장가</option><option value="limit">지정가</option><option value="stop_limit">스톱지정가</option></select></label>
      </div>
      <div class="grid2">
        <label>수량<input id="orderQty" type="number" min="1" value="1"></label>
        <label>가격<input id="orderPrice" type="number" min="0" value="0"></label>
      </div>
      <label>조건가격(스톱)<input id="condPrice" type="number" min="0" value="0"></label>
      <button id="orderBtn" class="primary danger" onclick="submitOrder()" disabled>주문 요청</button>
      <div class="muted small">최초 1회 실전 잠금 해제 후에는 주문마다 추가 문구 입력 없이 사용합니다.</div>
    </div>
    <div class="card">
      <div class="card-title">전체 로그</div>
      <div id="logs" class="log-list"></div>
    </div>
  </section>

  <section id="settings" class="page">
    <div class="card">
      <div class="card-title">연결</div>
      <div class="kv"><span>서버</span><b id="serverUrl">-</b></div>
      <div class="kv"><span>버전</span><b id="version">-</b></div>
      <div class="kv"><span>실전 잠금</span><b id="liveLockState">잠김</b></div>
      <button id="unlockLiveBtn" class="primary" onclick="unlockLive()">🔓 실전 기능 최초 1회 잠금 해제</button>
      <button id="lockLiveBtn" class="ghost full" onclick="lockLive()">🔒 실전 잠금 다시 걸기</button>
      <button class="ghost full" style="margin-top:7px" onclick="logout()">연결코드 초기화</button>
    </div>
    <div class="card">
      <div class="card-title">아이폰 설치</div>
      <p>Safari 공유 버튼 → <b>홈 화면에 추가</b>를 누르면 PUMA Mobile이 앱 아이콘으로 설치됩니다.</p>
    </div>
  </section>
</main>

<nav>
  <button data-page="home" class="active" onclick="showPage('home',this)">홈</button>
  <button data-page="candidates" onclick="showPage('candidates',this)">조건</button>
  <button data-page="stock" onclick="showPage('stock',this)">종목</button>
  <button data-page="account" onclick="showPage('account',this)">잔고·주문</button>
  <button data-page="settings" onclick="showPage('settings',this)">설정</button>
</nav>
<script src="/app.js"></script>
</body>
</html>
"""

STYLES_CSS = r"""
:root{--bg:#081321;--panel:#0e1e31;--panel2:#122842;--line:#26415f;--text:#edf5ff;--muted:#8eaac4;--green:#48d88a;--red:#ff5b68;--blue:#4f8fff;--gold:#ffd34d}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
body{padding-top:env(safe-area-inset-top);padding-bottom:calc(72px + env(safe-area-inset-bottom))}
header{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;padding:13px 16px;background:rgba(8,19,33,.96);border-bottom:1px solid var(--line);backdrop-filter:blur(14px)}
.brand{font-size:18px;font-weight:900;letter-spacing:.4px}.muted{color:var(--muted);font-size:12px}.small{font-size:11px}.badge{padding:6px 9px;border-radius:999px;font-weight:900;font-size:11px}.badge.on{background:#0a6b45;color:#8fffc2}.badge.off{background:#542331;color:#ff9cac}
main{max-width:760px;margin:0 auto;padding:12px}.page{display:none}.page.active{display:block}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}.card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:14px;padding:13px;margin-bottom:11px;box-shadow:0 5px 18px rgba(0,0,0,.18)}.card-title{font-weight:900;margin-bottom:9px}.k{font-size:11px;color:var(--muted)}.v{font-size:17px;font-weight:900}.price{font-size:21px;font-weight:900;color:var(--red);font-variant-numeric:tabular-nums}.analysis{white-space:pre-wrap;margin:0;color:#f4d46b;font:700 12px/1.55 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif}.analysis.big{font-size:13px;color:#68f29c}
.page-head,.stock-head,.chart-toolbar,.kv{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.stock-list,.compact-list,.log-list{display:flex;flex-direction:column;gap:7px}.stock-row{display:grid;grid-template-columns:1fr auto;gap:8px;padding:10px;background:#0b1b2c;border:1px solid #203b58;border-radius:10px}.stock-row:active{transform:scale(.995);background:#142f4e}.stock-title{font-weight:900}.stock-meta{font-size:11px;color:var(--muted);margin-top:3px}.class-pill{align-self:center;padding:5px 7px;border-radius:7px;background:#15395d;color:#6dc6ff;font-size:11px;font-weight:900}.inactive{opacity:.55}.log-row{display:grid;grid-template-columns:52px 70px 1fr;gap:7px;padding:7px 0;border-bottom:1px solid rgba(78,111,145,.25);font-size:11px}.log-kind{font-weight:900;color:#72bfff}.warning{background:#4a3011;color:#ffd77c;border:1px solid #7a5520;border-radius:9px;padding:9px;margin-bottom:10px;font-size:12px;font-weight:800}
button,input,select{font:inherit}button{border:0;border-radius:10px;padding:11px 13px;font-weight:900;color:white;background:#173c63}.primary{width:100%;background:#1679d2}.danger{background:#a63143}.ghost{background:#15314f;border:1px solid #315a84}.full{width:100%}button:disabled{opacity:.35}label{display:block;color:var(--muted);font-size:11px;margin:8px 0}input,select{width:100%;margin-top:4px;padding:11px;border-radius:9px;border:1px solid #31506f;background:#091a2c;color:#fff;outline:none}.order-card .grid2,.auto-card .grid2{gap:8px}.auto-status-row{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.auto-running{color:#5df29b}.auto-stopped{color:#ff9a72}.checklabel{display:flex;align-items:center;gap:8px;margin-top:25px}.checklabel input{width:auto;margin:0}.stop-auto{margin-top:7px}
.chart-card{padding:10px}.mini{padding:5px 9px;margin-right:5px;font-size:10px;background:#102a46;border:1px solid #315a84}.active-mini{background:#1c65a6;color:#fff}#chartCanvas{width:100%;height:310px;display:block;border-radius:9px;background:#071421}.legend{display:flex;gap:10px;flex-wrap:wrap;color:var(--muted);font-size:10px;margin-top:7px}.l112{color:#42df83}.l224{color:#ffb44b}.l448{color:#b8c1cc}
nav{position:fixed;left:0;right:0;bottom:0;z-index:20;height:calc(62px + env(safe-area-inset-bottom));padding-bottom:env(safe-area-inset-bottom);display:grid;grid-template-columns:repeat(5,1fr);background:rgba(7,17,29,.97);border-top:1px solid var(--line);backdrop-filter:blur(16px)}nav button{background:none;border-radius:0;color:#829db7;font-size:11px;padding:8px 2px}nav button.active{color:#65baff;border-top:2px solid #4da9ff}
.overlay{position:fixed;inset:0;z-index:100;background:rgba(3,9,16,.94);display:flex;align-items:center;justify-content:center;padding:24px}.overlay.hidden{display:none}.pair-card{width:min(400px,100%);padding:25px;background:#10233a;border:1px solid #315273;border-radius:20px;text-align:center}.pair-card .logo{font-size:54px}.pair-card h1{font-size:21px}.pair-card input{text-align:center;font-size:28px;letter-spacing:9px;font-weight:900;margin:14px 0}.pair-card button{margin-bottom:8px}
@media(max-width:390px){main{padding:9px}.grid2{gap:7px}.card{padding:11px}.chart-card{margin-left:-2px;margin-right:-2px}#chartCanvas{height:270px}}
"""

APP_JS = r"""
let token=localStorage.getItem('puma_token')||'';
let state=null, pollTimer=null, commandTimers={};

function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function money(v){let n=Number(String(v??0).replace(/[^\d.-]/g,''));return Number.isFinite(n)?Math.round(n).toLocaleString('ko-KR'):'-'}
async function api(path,opts={}){
  opts.headers=Object.assign({'X-Puma-Token':token,'Content-Type':'application/json'},opts.headers||{});
  const r=await fetch(path,opts);
  if(r.status===401) throw new Error('AUTH');
  let data={}; try{data=await r.json()}catch(e){}
  if(!r.ok) throw new Error(data.error||('HTTP '+r.status));
  return data;
}
async function pair(){
  token=document.getElementById('pairToken').value.trim();
  try{
    await api('/api/state');
    localStorage.setItem('puma_token',token);
    document.getElementById('pair').classList.add('hidden');
    startPolling();
  }catch(e){
    document.getElementById('pairMsg').textContent='연결코드를 확인하세요.';
  }
}
function logout(){localStorage.removeItem('puma_token');token='';location.reload()}
function showPage(id,btn){
  document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  document.querySelectorAll('nav button').forEach(x=>x.classList.remove('active'));
  if(btn)btn.classList.add('active');
  if(id==='stock'&&state) requestAnimationFrame(()=>drawChart(state.selected?.chart||{}));
}
function startPolling(){
  if(pollTimer)clearInterval(pollTimer);
  refreshNow();
  pollTimer=setInterval(refreshNow,1000);
}
async function refreshNow(){
  if(!token)return;
  try{
    const s=await api('/api/state');
    state=s; render(s);
    document.getElementById('connBadge').textContent='ONLINE';
    document.getElementById('connBadge').className='badge on';
  }catch(e){
    if(e.message==='AUTH'){document.getElementById('pair').classList.remove('hidden');}
    document.getElementById('connBadge').textContent='OFFLINE';
    document.getElementById('connBadge').className='badge off';
  }
}
function render(s){
  const sel=s.selected||{};
  document.getElementById('subTitle').textContent=(s.connected?'키움 연결 · ':'PC 연결 · ')+(s.updated_at||'');
  document.getElementById('pcMode').textContent=(s.live?'KIWOOM REAL':'SIM / MOCK')+(s.connected?' · 연결됨':' · 대기');
  document.getElementById('pcStatus').textContent=s.status||'-';
  document.getElementById('selName').textContent=sel.name||sel.code||'-';
  document.getElementById('selPrice').textContent=sel.price?money(sel.price)+' 원':'-';
  document.getElementById('stage').textContent=sel.stage||'데이터 대기';
  document.getElementById('stockName').textContent=sel.name||'종목 선택';
  document.getElementById('stockCode').textContent=sel.code||'-';
  document.getElementById('stockPrice').textContent=sel.price?money(sel.price)+' 원':'-';
  document.getElementById('danta').textContent=sel.analysis?.danta||'-';
  document.getElementById('swing').textContent=sel.analysis?.swing||'-';
  document.getElementById('bowl').textContent=sel.analysis?.bowl||'-';
  document.getElementById('orderCode').value=sel.code||document.getElementById('orderCode').value;
  document.getElementById('version').textContent=s.version||'-';
  document.getElementById('serverUrl').textContent=location.origin;
  const unlocked=!!s.mobile_live_unlocked;
  document.getElementById('liveLockState').textContent=unlocked?'해제됨':'잠김';
  document.getElementById('liveLockState').style.color=unlocked?'#5df29b':'#ff9a72';
  document.getElementById('unlockLiveBtn').style.display=unlocked?'none':'block';
  document.getElementById('lockLiveBtn').style.display=unlocked?'block':'none';
  const orderBtn=document.getElementById('orderBtn');
  orderBtn.disabled=!unlocked;
  document.getElementById('orderLock').style.display=unlocked?'none':'block';

  const au=s.auto||{};
  const autoStatus=document.getElementById('autoStatus');
  autoStatus.textContent=au.enabled?'실행 중':'중지';
  autoStatus.className='v '+(au.enabled?'auto-running':'auto-stopped');
  document.getElementById('autoScope').textContent=au.enabled?(au.scope_label||'-'):'-';
  document.getElementById('autoLock').style.display=unlocked?'none':'block';
  document.getElementById('autoStartBtn').disabled=!unlocked;
  setInputValue('autoBudget',au.settings?.order_budget);
  setInputValue('autoMaxPositions',au.settings?.max_positions);
  setInputValue('autoDailyOrders',au.settings?.max_daily_orders);
  setInputValue('autoTP',au.settings?.take_profit_pct);
  setInputValue('autoSL',au.settings?.stop_loss_pct);
  setInputValue('autoTrailStart',au.settings?.trailing_start_pct);
  setInputValue('autoTrailGap',au.settings?.trailing_gap_pct);
  if(document.activeElement?.id!=='autoTrailing') document.getElementById('autoTrailing').checked=!!au.settings?.trailing_enabled;
  if(document.activeElement?.id!=='autoSource' && au.settings?.candidate_source) document.getElementById('autoSource').value=au.settings.candidate_source;
  renderCandidates(s.candidates||[]);
  renderPositions(s.positions||[]);
  renderLogs(s.logs||[]);
  const chart=sel.chart||{};
  const cm=sel.chart_mode||'DAY';
  document.getElementById('dayBtn').classList.toggle('active-mini',cm==='DAY');
  document.getElementById('minBtn').classList.toggle('active-mini',cm==='MIN');
  document.getElementById('chartCount').textContent=(chart.candles?.length||0)+'봉';
  if(document.getElementById('stock').classList.contains('active')) drawChart(chart);
}
function setInputValue(id,v){
  const el=document.getElementById(id);
  if(!el||document.activeElement===el||v===undefined||v===null)return;
  el.value=v;
}
function candidateHtml(x){
  const sc=x.scores||{};
  return '<div class="stock-row '+(x.active?'':'inactive')+'" onclick="selectStock(\''+esc(x.code)+'\',\''+esc((x.name||'').replace(/'/g,"\\'"))+'\')">'+
    '<div><div class="stock-title">'+esc(x.name||x.code)+' <span class="muted">'+esc(x.code)+'</span></div>'+
    '<div class="stock-meta">'+esc(x.active?'편입':'이탈')+' · D '+(sc.danta??'-')+' / S '+(sc.swing??'-')+' / B '+(sc.bowl??'-')+'</div></div>'+
    '<div class="class-pill">'+esc(x.classification||'분석중')+'</div></div>';
}
function renderCandidates(xs){
  const active=xs.filter(x=>x.active);
  document.getElementById('candidateList').innerHTML=xs.length?xs.map(candidateHtml).join(''):'<div class="muted">조건검색 종목 없음</div>';
  document.getElementById('homeCandidates').innerHTML=active.length?active.slice(0,6).map(candidateHtml).join(''):'<div class="muted">활성 종목 없음</div>';
}
function renderPositions(xs){
  document.getElementById('positions').innerHTML=xs.length?xs.map(x=>
    '<div class="stock-row"><div><div class="stock-title">'+esc(x.name||x.code)+' <span class="muted">'+esc(x.code)+'</span></div>'+
    '<div class="stock-meta">수량 '+esc(x.qty)+' · 평균 '+money(x.avg_price)+' · 현재 '+money(x.current_price)+'</div></div>'+
    '<div class="class-pill">'+esc(x.pnl_pct??'-')+'%</div></div>').join(''):'<div class="muted">보유 종목 없음</div>';
}
function renderLogs(xs){
  const html=xs.map(x=>'<div class="log-row"><span>'+esc(x.time)+'</span><span class="log-kind">'+esc(x.kind)+'</span><span>'+esc(x.stock)+' · '+esc(x.text)+'</span></div>').join('');
  document.getElementById('logs').innerHTML=html||'<div class="muted">로그 없음</div>';
  document.getElementById('homeLogs').innerHTML=xs.slice(0,6).map(x=>'<div class="log-row"><span>'+esc(x.time)+'</span><span class="log-kind">'+esc(x.kind)+'</span><span>'+esc(x.stock)+' · '+esc(x.text)+'</span></div>').join('')||'<div class="muted">로그 없음</div>';
}
async function setChartMode(mode){
  try{
    const r=await api('/api/command',{method:'POST',body:JSON.stringify({type:'set_chart_mode',mode})});
    pollCommand(r.request_id);
  }catch(e){alert('차트 전환 실패: '+e.message)}
}
async function selectStock(code,name){
  try{
    const r=await api('/api/command',{method:'POST',body:JSON.stringify({type:'select_stock',code,name})});
    showPage('stock',document.querySelector('nav button[data-page="stock"]'));
    pollCommand(r.request_id);
  }catch(e){alert('종목 선택 실패: '+e.message)}
}
function pollCommand(id){
  let count=0;
  const t=setInterval(async()=>{
    try{
      const r=await api('/api/command/'+id);
      if(r.status==='done'||r.status==='error'){clearInterval(t);refreshNow();}
    }catch(e){clearInterval(t)}
    if(++count>20)clearInterval(t);
  },250);
}
async function unlockLive(){
  const phrase=prompt('최초 1회 실전 잠금 해제입니다. PUMA LIVE 를 입력하세요.')||'';
  if(phrase.trim().toUpperCase()!=='PUMA LIVE')return;
  try{
    const r=await api('/api/command',{method:'POST',body:JSON.stringify({type:'unlock_live',phrase})});
    pollAutoResult(r.request_id,'실전 잠금 해제');
  }catch(e){alert('잠금 해제 실패: '+e.message)}
}
async function lockLive(){
  if(!confirm('모바일 실전 잠금을 다시 걸까요?'))return;
  try{
    const r=await api('/api/command',{method:'POST',body:JSON.stringify({type:'lock_live'})});
    pollAutoResult(r.request_id,'실전 잠금');
  }catch(e){alert('잠금 설정 실패: '+e.message)}
}
async function startAuto(){
  if(!state?.mobile_live_unlocked){alert('설정에서 실전 잠금을 최초 1회 해제하세요.');return;}
  const scope=document.getElementById('autoScopeSelect').value;
  if(scope==='SELECTED'&&!state?.selected?.code){alert('먼저 종목을 선택하세요.');return}
  const payload={
    type:'auto_start',
    scope,
    code:state?.selected?.code||'',
    name:state?.selected?.name||'',
    candidate_source:document.getElementById('autoSource').value,
    order_budget:Number(document.getElementById('autoBudget').value||0),
    max_positions:Number(document.getElementById('autoMaxPositions').value||0),
    max_daily_orders:Number(document.getElementById('autoDailyOrders').value||0),
    take_profit_pct:Number(document.getElementById('autoTP').value||0),
    stop_loss_pct:Number(document.getElementById('autoSL').value||0),
    trailing_enabled:document.getElementById('autoTrailing').checked,
    trailing_start_pct:Number(document.getElementById('autoTrailStart').value||0),
    trailing_gap_pct:Number(document.getElementById('autoTrailGap').value||0)
  };
  const what=scope==='SELECTED'?(payload.name||payload.code)+' 한 종목':'전체 후보';
  if(!confirm(what+' 자동매매를 시작할까요?'))return;
  try{
    const r=await api('/api/command',{method:'POST',body:JSON.stringify(payload)});
    pollAutoResult(r.request_id,'시작');
  }catch(e){alert('자동매매 시작 실패: '+e.message)}
}
async function stopAuto(){
  if(!state?.auto?.enabled){refreshNow();return}
  if(!confirm('자동매매를 중지할까요?'))return;
  try{
    const r=await api('/api/command',{method:'POST',body:JSON.stringify({type:'auto_stop'})});
    pollAutoResult(r.request_id,'중지');
  }catch(e){alert('자동매매 중지 실패: '+e.message)}
}
function pollAutoResult(id,action){
  let count=0;
  const t=setInterval(async()=>{
    try{
      const r=await api('/api/command/'+id);
      if(r.status==='done'){clearInterval(t);alert('자동매매 '+action+': '+(r.result?.message||'완료'));refreshNow();}
      if(r.status==='error'){clearInterval(t);alert('자동매매 '+action+' 실패: '+(r.error||'오류'));}
    }catch(e){clearInterval(t)}
    if(++count>30){clearInterval(t);alert('처리 결과 확인 시간이 초과되었습니다. PC 로그를 확인하세요.');}
  },300);
}
async function submitOrder(){
  if(!state?.mobile_live_unlocked){alert('설정에서 실전 잠금을 최초 1회 해제하세요.');return;}
  const side=document.getElementById('orderSide').value;
  const code=document.getElementById('orderCode').value.trim();
  const qty=Number(document.getElementById('orderQty').value||0);
  const order_type=document.getElementById('orderType').value;
  const price=Number(document.getElementById('orderPrice').value||0);
  const cond_price=Number(document.getElementById('condPrice').value||0);
  if(!code||qty<1){alert('종목코드와 수량을 확인하세요.');return}
  const label=side==='BUY'?'매수':'매도';
  if(!confirm(code+' '+qty+'주 '+label+' 주문을 요청할까요?'))return;
  try{
    const r=await api('/api/command',{method:'POST',body:JSON.stringify({type:'order',side,code,qty,order_type,price,cond_price})});
    pollOrderResult(r.request_id);
  }catch(e){alert('주문 요청 실패: '+e.message)}
}
function pollOrderResult(id){
  let count=0;
  const t=setInterval(async()=>{
    try{
      const r=await api('/api/command/'+id);
      if(r.status==='done'){clearInterval(t);alert('주문 처리: '+(r.result?.message||'완료'));refreshNow();}
      if(r.status==='error'){clearInterval(t);alert('주문 실패: '+(r.error||'오류'));}
    }catch(e){clearInterval(t);alert('주문 결과 확인 실패: '+e.message)}
    if(++count>30){clearInterval(t);alert('주문 결과 확인 시간이 초과되었습니다. PC 로그를 확인하세요.');}
  },300);
}
function drawChart(chart){
  const canvas=document.getElementById('chartCanvas'), ctx=canvas.getContext('2d');
  const dpr=window.devicePixelRatio||1, w=canvas.clientWidth||350, h=canvas.clientHeight||300;
  canvas.width=Math.floor(w*dpr);canvas.height=Math.floor(h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,w,h);ctx.fillStyle='#071421';ctx.fillRect(0,0,w,h);
  const cs=chart.candles||[]; if(!cs.length){ctx.fillStyle='#7793ad';ctx.font='13px sans-serif';ctx.fillText('차트 데이터 대기',16,30);return}
  const pad={l:7,r:47,t:8,b:20}; const pw=w-pad.l-pad.r, ph=h-pad.t-pad.b;
  let vals=[]; cs.forEach(c=>{vals.push(Number(c.high),Number(c.low))});
  ['ema112','ema224','ema448'].forEach(k=>(chart[k]||[]).forEach(v=>{if(v!=null)vals.push(Number(v))}));
  let lo=Math.min(...vals),hi=Math.max(...vals); if(hi<=lo){hi=lo+1}; const extra=(hi-lo)*.05;lo-=extra;hi+=extra;
  const y=v=>pad.t+(hi-Number(v))/(hi-lo)*ph; const x=i=>pad.l+(i+.5)*pw/cs.length; const bw=Math.max(1,Math.min(6,pw/cs.length*.56));
  ctx.strokeStyle='rgba(120,150,180,.13)';ctx.lineWidth=1;
  for(let j=0;j<5;j++){let yy=pad.t+j*ph/4;ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke()}
  ctx.fillStyle='#7892aa';ctx.font='9px sans-serif';ctx.textAlign='left';
  for(let j=0;j<5;j++){let v=hi-j*(hi-lo)/4;ctx.fillText(Math.round(v).toLocaleString(),w-pad.r+4,pad.t+j*ph/4+3)}
  cs.forEach((c,i)=>{
    const up=Number(c.close)>=Number(c.open);ctx.strokeStyle=up?'#ff5965':'#4b8eff';ctx.fillStyle=ctx.strokeStyle;
    ctx.beginPath();ctx.moveTo(x(i),y(c.high));ctx.lineTo(x(i),y(c.low));ctx.stroke();
    let top=Math.min(y(c.open),y(c.close)),bot=Math.max(y(c.open),y(c.close));ctx.fillRect(x(i)-bw/2,top,bw,Math.max(1,bot-top));
  });
  function line(key,color,width=1.2){
    const a=chart[key]||[];ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();let started=false;
    a.forEach((v,i)=>{if(v==null)return;let xx=x(i),yy=y(v);if(!started){ctx.moveTo(xx,yy);started=true}else ctx.lineTo(xx,yy)});ctx.stroke();
  }
  line('ema112','#45df80',1.4);line('ema224','#ffad43',1.5);line('ema448','#c0c7d1',1.4);
  const defs=[['signal_pink','#ff31cf','분'],['signal_blue','#397dff','파'],['signal_red','#ff3945','빨'],['signal_black','#ffffff','검']];
  cs.forEach((c,i)=>{
    let stack=0;
    defs.forEach(([k,col,lab])=>{
      const a=chart[k]||[]; if(!a[i])return;
      const xx=x(i), yy=Math.min(h-pad.b-8,y(c.low)+10+stack*11);ctx.fillStyle=col;ctx.beginPath();ctx.moveTo(xx,yy-6);ctx.lineTo(xx-5,yy+3);ctx.lineTo(xx+5,yy+3);ctx.closePath();ctx.fill();
      ctx.font='bold 7px sans-serif';ctx.textAlign='left';ctx.fillText(lab,xx+5,yy+3);stack++;
    });
    const wm=chart.watermelon_display||[]; if(wm[i]){
      const xx=x(i),yy=Math.min(h-pad.b-10,y(c.low)+18+stack*11);ctx.fillStyle='#ef4c5b';ctx.strokeStyle='#42cf68';ctx.lineWidth=2;ctx.beginPath();ctx.arc(xx,yy,6,0,Math.PI*2);ctx.fill();ctx.stroke();
    }
  });
}
window.addEventListener('resize',()=>{if(state)drawChart(state.selected?.chart||{})});
if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(()=>{})}
if(token){document.getElementById('pair').classList.add('hidden');startPolling()}
"""

SW_JS = r"""
const CACHE='puma-mobile-v1';
const ASSETS=['/','/styles.css','/app.js','/manifest.webmanifest','/icon.svg'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS))));
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('fetch',e=>{
  if(e.request.url.includes('/api/')) return;
  e.respondWith(fetch(e.request).then(r=>{let x=r.clone();caches.open(CACHE).then(c=>c.put(e.request,x));return r}).catch(()=>caches.match(e.request)));
});
"""

ICON_SVG = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<rect width="512" height="512" rx="110" fill="#081321"/>
<circle cx="256" cy="256" r="172" fill="#142b46" stroke="#4aa9ff" stroke-width="18"/>
<text x="256" y="300" text-anchor="middle" font-size="190">🐆</text>
</svg>"""

MANIFEST = {
    "name": "PUMA STOCK MOBILE",
    "short_name": "PUMA Mobile",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#081321",
    "theme_color": "#081321",
    "icons": [{"src": "/icon.svg", "sizes": "512x512", "type": "image/svg+xml"}],
}


class _ReusableHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class MobileBridge(QObject):
    """Companion bridge for PUMA STOCK PRO over LAN or a private Tailscale IP.

    The HTTP server binds all PC interfaces. The HTTP thread never touches Qt
    widgets; the main UI publishes immutable state and commands are marshalled
    back to the Qt thread via Signal.
    """

    commandReceived = Signal(str, object)

    def __init__(self, parent=None, *, config_path: str | Path | None = None):
        super().__init__(parent)
        root = Path(__file__).resolve().parent.parent
        self.config_path = Path(config_path) if config_path else root / "config" / "mobile.json"
        self._state: dict = {}
        self._state_lock = threading.RLock()
        self._commands: dict[str, dict] = {}
        self._command_lock = threading.RLock()
        self._server: _ReusableHTTPServer | None = None
        self._thread: threading.Thread | None = None
        cfg = self._load_config()
        self.port = int(cfg.get("port", 8765) or 8765)
        self.token = str(cfg.get("token") or self._new_token())
        self._live_unlocked = bool(cfg.get("live_unlocked", False))
        if len(self.token) != 6 or not self.token.isdigit():
            self.token = self._new_token()
        self._save_config()

    @staticmethod
    def _new_token() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    def _load_config(self) -> dict:
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_config(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(
                json.dumps({
                    "port": self.port,
                    "token": self.token,
                    "live_unlocked": bool(self._live_unlocked),
                }, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    @property
    def running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    @property
    def live_unlocked(self) -> bool:
        return bool(self._live_unlocked)

    def unlock_live(self):
        self._live_unlocked = True
        self._save_config()

    def lock_live(self):
        self._live_unlocked = False
        self._save_config()

    def regenerate_token(self) -> str:
        self.token = self._new_token()
        # 새 연결코드는 새 모바일 페어링으로 간주하여 실전 잠금도 다시 건다.
        self._live_unlocked = False
        self._save_config()
        return self.token

    def local_ip(self) -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
        except Exception:
            try:
                return socket.gethostbyname(socket.gethostname())
            except Exception:
                return "127.0.0.1"
        finally:
            sock.close()

    def tailscale_ip(self) -> str:
        """Return this PC's Tailscale IPv4 (100.64.0.0/10) when available."""
        commands = [
            ["tailscale", "ip", "-4"],
            [r"C:\\Program Files\\Tailscale\\tailscale.exe", "ip", "-4"],
        ]
        for cmd in commands:
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=2.5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if proc.returncode != 0:
                    continue
                for line in str(proc.stdout or "").splitlines():
                    ip = line.strip()
                    parts = ip.split(".")
                    if len(parts) != 4:
                        continue
                    nums = [int(x) for x in parts]
                    # Tailscale CGNAT range: 100.64.0.0/10
                    if nums[0] == 100 and 64 <= nums[1] <= 127:
                        return ip
            except Exception:
                pass
        return ""

    def url(self) -> str:
        return f"http://{self.local_ip()}:{self.port}"

    def external_url(self) -> str:
        ip = self.tailscale_ip()
        return f"http://{ip}:{self.port}" if ip else ""

    def publish(self, state: dict):
        safe = json.loads(json.dumps(state, ensure_ascii=False, default=str))
        safe["mobile_live_unlocked"] = bool(self._live_unlocked)
        with self._state_lock:
            self._state = safe

    def state(self) -> dict:
        with self._state_lock:
            return dict(self._state)

    def queue_command(self, payload: dict) -> str:
        rid = uuid.uuid4().hex[:16]
        now = time.time()
        with self._command_lock:
            self._commands[rid] = {
                "status": "pending",
                "created_at": now,
                "payload": dict(payload),
                "result": None,
                "error": None,
            }
            self._prune_commands_locked(now)
        self.commandReceived.emit(rid, dict(payload))
        return rid

    def complete_command(self, request_id: str, result: dict | None = None, error: str | None = None):
        with self._command_lock:
            row = self._commands.get(request_id)
            if not row:
                return
            row["status"] = "error" if error else "done"
            row["result"] = result or {}
            row["error"] = str(error) if error else None
            row["completed_at"] = time.time()

    def command_status(self, request_id: str) -> dict | None:
        with self._command_lock:
            row = self._commands.get(request_id)
            if not row:
                return None
            return {
                "status": row.get("status"),
                "result": row.get("result"),
                "error": row.get("error"),
            }

    def _prune_commands_locked(self, now: float):
        stale = [k for k, v in self._commands.items() if now - float(v.get("created_at", now)) > 300]
        for key in stale:
            self._commands.pop(key, None)

    def start(self, port: int | None = None):
        if self.running:
            return {
                "url": self.url(),
                "external_url": self.external_url(),
                "token": self.token,
                "port": self.port,
            }
        if port is not None:
            self.port = max(1024, min(65535, int(port)))
        self._save_config()

        bridge = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "PUMAMobile/1.0"

            def log_message(self, fmt, *args):
                return

            def _send(self, status: int, body: bytes, content_type="application/json; charset=utf-8", extra=None):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store" if self.path.startswith("/api/") else "public, max-age=60")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                if extra:
                    for k, v in extra.items():
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def _json(self, status: int, obj: dict):
                self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

            def _token(self) -> str:
                header = str(self.headers.get("X-Puma-Token") or "").strip()
                if header:
                    return header
                query = parse_qs(urlparse(self.path).query)
                return str((query.get("token") or [""])[0]).strip()

            def _authorized(self) -> bool:
                supplied = self._token()
                return bool(supplied) and secrets.compare_digest(supplied, bridge.token)

            def _require_auth(self) -> bool:
                if self._authorized():
                    return True
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "연결코드가 올바르지 않습니다."})
                return False

            def do_GET(self):
                path = urlparse(self.path).path
                if path == "/":
                    return self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
                if path == "/demo":
                    return self._send(200, DEMO_HTML.encode("utf-8"), "text/html; charset=utf-8")
                if path == "/styles.css":
                    return self._send(200, STYLES_CSS.encode("utf-8"), "text/css; charset=utf-8")
                if path == "/app.js":
                    return self._send(200, APP_JS.encode("utf-8"), "application/javascript; charset=utf-8")
                if path == "/sw.js":
                    return self._send(200, SW_JS.encode("utf-8"), "application/javascript; charset=utf-8")
                if path == "/icon.svg":
                    return self._send(200, ICON_SVG.encode("utf-8"), "image/svg+xml")
                if path == "/manifest.webmanifest":
                    return self._send(
                        200,
                        json.dumps(MANIFEST, ensure_ascii=False).encode("utf-8"),
                        "application/manifest+json; charset=utf-8",
                    )
                if path == "/api/ping":
                    return self._json(200, {"ok": True, "name": "PUMA STOCK MOBILE", "running": bridge.running})
                if path == "/api/state":
                    if not self._require_auth():
                        return
                    return self._json(200, bridge.state())
                if path.startswith("/api/command/"):
                    if not self._require_auth():
                        return
                    rid = path.rsplit("/", 1)[-1]
                    row = bridge.command_status(rid)
                    if row is None:
                        return self._json(404, {"error": "요청을 찾을 수 없습니다."})
                    return self._json(200, row)
                return self._json(404, {"error": "not found"})

            def do_POST(self):
                path = urlparse(self.path).path
                if path != "/api/command":
                    return self._json(404, {"error": "not found"})
                if not self._require_auth():
                    return
                try:
                    size = min(64 * 1024, max(0, int(self.headers.get("Content-Length", "0") or 0)))
                    payload = json.loads(self.rfile.read(size).decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("object required")
                except Exception:
                    return self._json(400, {"error": "잘못된 요청입니다."})

                command_type = str(payload.get("type") or "").strip()
                if command_type not in ("select_stock", "set_chart_mode", "order", "auto_start", "auto_stop", "unlock_live", "lock_live"):
                    return self._json(400, {"error": "지원하지 않는 명령입니다."})
                if command_type in ("order", "auto_start") and not bridge.live_unlocked:
                    return self._json(403, {"error": "모바일에서 실전 잠금을 최초 1회 해제하세요."})
                rid = bridge.queue_command(payload)
                return self._json(202, {"accepted": True, "request_id": rid})

        try:
            self._server = _ReusableHTTPServer(("0.0.0.0", self.port), Handler)
        except Exception:
            self._server = None
            raise

        self._thread = threading.Thread(target=self._server.serve_forever, name="PUMA-Mobile-HTTP", daemon=True)
        self._thread.start()
        return {
            "url": self.url(),
            "external_url": self.external_url(),
            "token": self.token,
            "port": self.port,
        }

    def stop(self):
        server = self._server
        self._server = None
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
