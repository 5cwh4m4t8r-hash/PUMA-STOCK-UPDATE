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
  <meta name="theme-color" content="#070a0f">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="PUMA STOCK">
  <title>PUMA STOCK MOBILE</title>
  <link rel="manifest" href="/manifest.webmanifest">
  <link rel="icon" href="/icon.svg">
  <link rel="apple-touch-icon" href="/icon.svg">
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
<div id="pair" class="overlay">
  <div class="pair-card">
    <div class="brand-mark large">P</div>
    <div class="eyebrow">PUMA STOCK PRO</div>
    <h1>모바일 터미널 연결</h1>
    <p>PC PUMA의 <b>모바일 연동</b> 탭에 표시된 6자리 연결코드를 입력하세요.</p>
    <input id="pairToken" inputmode="numeric" maxlength="6" placeholder="000000">
    <button class="primary" onclick="pair()">PUMA 연결</button>
    <div id="pairMsg" class="muted"></div>
  </div>
</div>

<header>
  <div class="brand-wrap">
    <div class="brand-mark">P</div>
    <div>
      <div class="brand">PUMA STOCK <span>PRO</span></div>
      <div id="subTitle" class="muted">PC 연결 확인 중…</div>
    </div>
  </div>
  <div id="connBadge" class="badge off"><i></i> OFFLINE</div>
</header>

<main>
  <section id="home" class="page active">
    <div class="hero-card">
      <div class="hero-top">
        <div>
          <div class="eyebrow">TRADING TERMINAL</div>
          <div id="pcMode" class="hero-mode">-</div>
          <div id="pcStatus" class="muted">-</div>
        </div>
        <div class="live-dot"><span></span> LIVE</div>
      </div>
      <div class="hero-divider"></div>
      <div class="selected-strip">
        <div><div class="k">현재 종목</div><div id="selName" class="selected-name">-</div></div>
        <div id="selPrice" class="price hero-price">-</div>
      </div>
    </div>

    <div class="section-label">자동매매</div>
    <div class="card control-card">
      <div class="control-status">
        <div><div class="k">엔진 상태</div><div id="homeAutoStatus" class="v">동기화 중</div></div>
        <button class="compact-action" onclick="showPage('account',document.querySelector('nav [data-page=account]'))">제어</button>
      </div>
      <div class="metric-grid">
        <div class="metric"><span>복리 시드</span><b id="homeSeed">-</b></div>
        <div class="metric"><span>신규매수</span><b id="homeRisk">-</b></div>
      </div>
    </div>

    <div class="section-label">PUMA 판단</div>
    <div class="card decision-card"><div id="stage" class="analysis big">데이터 대기</div></div>

    <div class="section-head">
      <div class="section-label">실시간 후보</div>
      <button class="text-button" onclick="showPage('candidates',document.querySelector('nav [data-page=candidates]'))">전체 보기</button>
    </div>
    <div class="card list-card"><div id="homeCandidates" class="compact-list"></div></div>

    <div class="section-label">최근 이벤트</div>
    <div class="card list-card"><div id="homeLogs" class="log-list"></div></div>
  </section>

  <section id="candidates" class="page">
    <div class="page-title-row">
      <div><div class="eyebrow">LIVE SCANNER</div><h2>조건검색 후보</h2><div class="muted">종목을 누르면 PC PUMA와 즉시 동기화</div></div>
      <button class="icon-action" onclick="refreshNow()" aria-label="새로고침">↻</button>
    </div>
    <div id="candidateList" class="stock-list"></div>
  </section>

  <section id="stock" class="page">
    <div class="stock-head premium-head">
      <div><div class="eyebrow">SELECTED STOCK</div><div id="stockName" class="stock-name">종목 선택</div><div id="stockCode" class="muted">-</div></div>
      <div id="stockPrice" class="price">-</div>
    </div>
    <div class="card chart-card">
      <div class="chart-toolbar">
        <div class="segmented">
          <button id="dayBtn" class="mini active-mini" onclick="setChartMode('DAY')">일봉</button>
          <button id="minBtn" class="mini" onclick="setChartMode('MIN')">5분</button>
        </div>
        <span id="chartCount" class="muted">0봉</span>
      </div>
      <canvas id="chartCanvas"></canvas>
      <div class="legend">
        <span class="l112">112 EMA</span><span class="l224">224 EMA</span><span class="l448">448 EMA</span><span>▲ 신호</span><span>● 수박</span>
      </div>
    </div>
    <div class="analysis-grid">
      <div class="card analysis-card"><div class="analysis-title"><span>DAY</span> 단타 · 5분봉</div><pre id="danta" class="analysis">-</pre></div>
      <div class="card analysis-card"><div class="analysis-title"><span>SWING</span> 역매공파</div><pre id="swing" class="analysis">-</pre></div>
      <div class="card analysis-card"><div class="analysis-title"><span>LONG</span> 밥그릇3</div><pre id="bowl" class="analysis">-</pre></div>
    </div>
  </section>

  <section id="account" class="page">
    <div class="page-title-row">
      <div><div class="eyebrow">TRADE CONTROL</div><h2>잔고 · 자동매매</h2></div>
      <div id="autoScope" class="class-pill">-</div>
    </div>

    <div class="card auto-card">
      <div class="auto-status-row">
        <div><div class="k">자동매매 엔진</div><div id="autoStatus" class="auto-status">중지</div></div>
        <div id="autoStatusOrb" class="status-orb"></div>
      </div>
      <div id="autoLock" class="warning">모바일 실전 잠금 해제 필요</div>

      <div class="metric-grid four">
        <div class="metric"><span>현재 복리 시드</span><b id="autoSeed">-</b></div>
        <div class="metric"><span>동시 보유</span><b>1종목 고정</b></div>
        <div class="metric"><span>오늘 시드 손익</span><b id="autoDailyLoss">-</b></div>
        <div class="metric"><span>신규매수</span><b id="autoRiskState">-</b></div>
      </div>
      <div id="autoPhaseNote" class="muted small compound-note">1차 목표 300만원 · 하루 -4% 도달 시 신규매수 중단</div>

      <div class="form-block">
        <label>매매 대상
          <select id="autoScopeSelect">
            <option value="ALL">전체 후보 → PUMA 최우선 1종목</option>
            <option value="SELECTED">현재 선택종목만</option>
          </select>
        </label>
        <label>후보 경로
          <select id="autoSource" disabled>
            <option value="HERO4">단타 검색기 전체 → PUMA 최우선 1종목</option>
          </select>
        </label>
      </div>

      <details class="rules">
        <summary>가보자 고정 매매 규칙 보기</summary>
        <div class="fixed-rule-box">
          <div class="fixed-rule-line"><b>A</b> 차(눌림) 구간 진입</div>
          <div class="fixed-rule-line"><b>B</b> A 미진입 시 잠긴 1영 몸통 기준선 첫 돌파 진입</div>
          <div class="fixed-rule-line">A/B 중 한 곳에서만 1회 진입 · 윗꼬리 돌파 제외</div>
          <div class="fixed-rule-line">현재 복리 시드 전액 · 최우선 1종목만 진입 · 하루 -4% 신규매수 중단</div>
          <div class="fixed-rule-line">손절·익절·당일청산은 PC 가보자 엔진과 동일하게 실행</div>
        </div>
      </details>

      <div class="auto-actions">
        <button id="autoStartBtn" class="primary start-action" onclick="startAuto()" disabled>자동매매 시작</button>
        <button id="autoStopBtn" class="stop-action" onclick="stopAuto()" disabled>중지</button>
      </div>
      <div id="autoCommandMsg" class="muted small auto-command-msg">상태 동기화 중</div>
    </div>

    <div class="section-label">보유 종목</div>
    <div class="card list-card"><div id="positions" class="stock-list"></div></div>

    <details class="order-drawer">
      <summary>수동 주문 열기</summary>
      <div class="card order-card">
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
      </div>
    </details>

    <div class="section-label">전체 로그</div>
    <div class="card list-card"><div id="logs" class="log-list"></div></div>
  </section>

  <section id="settings" class="page">
    <div class="page-title-row"><div><div class="eyebrow">SYSTEM</div><h2>설정</h2></div></div>
    <div class="card settings-card">
      <div class="setting-row"><span>서버</span><b id="serverUrl">-</b></div>
      <div class="setting-row"><span>버전</span><b id="version">-</b></div>
      <div class="setting-row"><span>실전 잠금</span><b id="liveLockState">잠김</b></div>
      <div class="settings-actions">
        <button id="unlockLiveBtn" class="primary" onclick="unlockLive()">실전 기능 잠금 해제</button>
        <button id="lockLiveBtn" class="secondary full" onclick="lockLive()">실전 잠금 다시 걸기</button>
        <button class="secondary full" onclick="logout()">연결코드 초기화</button>
      </div>
    </div>
    <div class="card install-card">
      <div class="card-title">아이폰 홈 화면 설치</div>
      <p>Safari 공유 버튼 → <b>홈 화면에 추가</b>. 이후 일반 앱처럼 전체화면으로 실행됩니다.</p>
    </div>
  </section>
</main>

<nav>
  <button data-page="home" class="active" onclick="showPage('home',this)"><span class="nav-icon">⌂</span><span>홈</span></button>
  <button data-page="candidates" onclick="showPage('candidates',this)"><span class="nav-icon">◎</span><span>후보</span></button>
  <button data-page="stock" onclick="showPage('stock',this)"><span class="nav-icon">▥</span><span>차트</span></button>
  <button data-page="account" onclick="showPage('account',this)"><span class="nav-icon">↗</span><span>매매</span></button>
  <button data-page="settings" onclick="showPage('settings',this)"><span class="nav-icon">⚙︎</span><span>설정</span></button>
</nav>
<script src="/app.js"></script>
</body>
</html>"""

STYLES_CSS = r""":root{
  --bg:#070a0f;--bg2:#0b1017;--panel:#101720;--panel2:#131d28;--panel3:#0d141c;
  --line:#202c39;--line2:#2a3b4c;--text:#f4f7fb;--muted:#8493a5;--muted2:#5d6a79;
  --accent:#2da8ff;--accent2:#6bc7ff;--green:#38d996;--red:#ff6070;--gold:#f1c75b;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html{background:var(--bg)}
html,body{margin:0;color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Apple SD Gothic Neo","Noto Sans KR",sans-serif}
body{min-height:100vh;background:radial-gradient(circle at 50% -18%,#14283a 0,#0a1119 30%,var(--bg) 62%);padding-top:env(safe-area-inset-top);padding-bottom:calc(84px + env(safe-area-inset-bottom));font-variant-numeric:tabular-nums}
button,input,select{font:inherit}
button{border:0;color:var(--text);cursor:pointer;-webkit-appearance:none}
button:active{transform:scale(.985)}
button:disabled{opacity:.34;transform:none}
header{position:sticky;top:0;z-index:20;display:flex;align-items:center;justify-content:space-between;min-height:64px;padding:10px 15px;background:rgba(7,10,15,.84);border-bottom:1px solid rgba(255,255,255,.06);backdrop-filter:blur(22px) saturate(150%)}
.brand-wrap{display:flex;align-items:center;gap:10px;min-width:0}
.brand-mark{display:grid;place-items:center;width:34px;height:34px;border-radius:10px;background:linear-gradient(145deg,#36b3ff,#1369d7);box-shadow:0 8px 24px rgba(31,142,236,.28);font-size:19px;font-weight:1000;color:white;letter-spacing:-1px}
.brand-mark.large{width:58px;height:58px;border-radius:17px;margin:0 auto 14px;font-size:31px}
.brand{font-size:15px;font-weight:1000;letter-spacing:.35px;white-space:nowrap}.brand span{font-size:9px;color:var(--accent2);vertical-align:top;margin-left:3px}
.muted{color:var(--muted);font-size:11px}.small{font-size:10.5px}.eyebrow{font-size:9px;font-weight:900;letter-spacing:1.4px;color:#72869b;text-transform:uppercase}
.badge{display:flex;align-items:center;gap:6px;padding:6px 9px;border:1px solid var(--line2);border-radius:999px;background:#0d151e;font-weight:900;font-size:9px;letter-spacing:.45px}
.badge i{display:block;width:6px;height:6px;border-radius:50%}.badge.on{color:#80efbc}.badge.on i{background:var(--green);box-shadow:0 0 10px rgba(56,217,150,.8)}.badge.off{color:#f48a97}.badge.off i{background:var(--red)}
main{max-width:760px;margin:0 auto;padding:12px 12px 20px}.page{display:none}.page.active{display:block;animation:pagein .16s ease-out}@keyframes pagein{from{opacity:.3;transform:translateY(3px)}to{opacity:1;transform:none}}
.hero-card{padding:17px;margin-bottom:17px;border:1px solid #253748;border-radius:19px;background:linear-gradient(145deg,#142231 0,#101820 58%,#0c1219 100%);box-shadow:0 12px 34px rgba(0,0,0,.24),inset 0 1px rgba(255,255,255,.03)}
.hero-top,.selected-strip,.control-status,.auto-status-row,.section-head,.page-title-row,.stock-head,.chart-toolbar,.setting-row{display:flex;align-items:center;justify-content:space-between;gap:12px}
.hero-mode{margin-top:5px;font-size:18px;font-weight:950;letter-spacing:-.3px}.live-dot{align-self:flex-start;display:flex;align-items:center;gap:6px;padding:5px 8px;border-radius:999px;background:rgba(56,217,150,.08);color:#7cebb9;font-size:9px;font-weight:1000;letter-spacing:.7px}.live-dot span{width:6px;height:6px;border-radius:50%;background:var(--green);box-shadow:0 0 10px rgba(56,217,150,.7)}
.hero-divider{height:1px;background:linear-gradient(90deg,transparent,#263746 18%,#263746 82%,transparent);margin:14px 0}
.selected-name{margin-top:3px;font-size:17px;font-weight:950}.hero-price{font-size:24px}
.section-label{margin:16px 4px 7px;font-size:11px;font-weight:950;color:#b9c4d0;letter-spacing:.2px}.section-head .section-label{margin-right:auto}.text-button{padding:6px 4px;background:none;color:var(--accent2);font-size:10px;font-weight:900}
.card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:14px;margin-bottom:11px;box-shadow:0 8px 24px rgba(0,0,0,.15)}
.list-card{padding:7px}.card-title{font-size:13px;font-weight:950;margin-bottom:10px}.k{font-size:10px;color:var(--muted);font-weight:700}.v{font-size:16px;font-weight:950}.price{font-size:21px;font-weight:1000;color:#ff7180;letter-spacing:-.4px}
.control-card{padding:14px}.compact-action,.icon-action{background:#15283a;border:1px solid #2d475e;color:#8dd2ff;font-weight:900}.compact-action{padding:8px 13px;border-radius:9px;font-size:11px}.icon-action{width:38px;height:38px;border-radius:12px;font-size:19px;padding:0}
.metric-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}.metric-grid.four{margin:12px 0 8px}.metric{min-width:0;padding:10px 11px;border:1px solid #1e2d3b;border-radius:11px;background:#0b1219}.metric span{display:block;font-size:9.5px;color:var(--muted);margin-bottom:4px}.metric b{display:block;overflow:hidden;text-overflow:ellipsis;font-size:13px;font-weight:950;white-space:nowrap}
.decision-card{position:relative;overflow:hidden}.decision-card:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:linear-gradient(var(--green),#188de0)}.analysis{white-space:pre-wrap;margin:0;color:#e8edf3;font:650 11.5px/1.55 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif}.analysis.big{font-size:12.5px;font-weight:800;color:#8ff0bd}
.page-title-row{margin:4px 2px 15px}.page-title-row h2{margin:3px 0 2px;font-size:22px;line-height:1.15;letter-spacing:-.6px}.premium-head{padding:4px 2px 12px}.stock-name{margin-top:3px;font-size:22px;font-weight:1000;letter-spacing:-.6px}
.stock-list,.compact-list,.log-list{display:flex;flex-direction:column;gap:6px}.stock-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:9px;align-items:center;min-height:58px;padding:10px 11px;background:#0c141d;border:1px solid #1d2b39;border-radius:12px}.stock-row:active{background:#122231;border-color:#31506b}.stock-title{overflow:hidden;text-overflow:ellipsis;font-size:13px;font-weight:950;white-space:nowrap}.stock-meta{overflow:hidden;text-overflow:ellipsis;font-size:10px;color:var(--muted);margin-top:4px;white-space:nowrap}.class-pill{align-self:center;padding:5px 7px;border:1px solid #244b67;border-radius:8px;background:#102436;color:#74caff;font-size:9.5px;font-weight:950}.inactive{opacity:.5}
.log-row{display:grid;grid-template-columns:44px 62px minmax(0,1fr);gap:7px;padding:8px 5px;border-bottom:1px solid rgba(255,255,255,.05);font-size:10px}.log-row:last-child{border-bottom:0}.log-kind{overflow:hidden;text-overflow:ellipsis;color:#79c6ff;font-weight:900;white-space:nowrap}
.chart-card{padding:9px}.segmented{display:flex;padding:3px;border:1px solid #243647;border-radius:10px;background:#0a1118}.mini{min-width:58px;padding:7px 11px;border-radius:7px;background:transparent;color:#728395;font-size:10px;font-weight:900}.active-mini{background:#1a3650;color:#a9dcff;box-shadow:0 2px 8px rgba(0,0,0,.25)}#chartCanvas{width:100%;height:322px;display:block;border-radius:11px;background:#080e14}.legend{display:flex;gap:11px;flex-wrap:wrap;padding:8px 4px 2px;color:var(--muted);font-size:9px}.l112{color:#49db8c}.l224{color:#f3b65a}.l448{color:#c8d0da}.analysis-grid{display:grid;gap:9px}.analysis-card{margin-bottom:0}.analysis-title{margin-bottom:9px;font-size:12px;font-weight:950}.analysis-title span{display:inline-block;min-width:43px;margin-right:7px;color:#71c8ff;font-size:9px;letter-spacing:.8px}
.auto-card{padding:15px;border-color:#273b4c}.auto-status{margin-top:3px;font-size:23px;font-weight:1000;letter-spacing:-.6px}.status-orb{width:12px;height:12px;border-radius:50%;background:#354353;box-shadow:0 0 0 5px rgba(90,112,133,.08)}.status-orb.on{background:var(--green);box-shadow:0 0 0 5px rgba(56,217,150,.08),0 0 18px rgba(56,217,150,.42)}
.warning{margin:11px 0;padding:9px 10px;border:1px solid #745524;border-radius:10px;background:rgba(110,77,19,.22);color:#f2cf76;font-size:10.5px;font-weight:850}
.form-block{margin:12px 0;padding:10px;border:1px solid #1f2f3e;border-radius:12px;background:#0b1219}
label{display:block;color:var(--muted);font-size:10px;font-weight:750;margin:8px 0}input,select{width:100%;margin-top:5px;padding:11px 12px;border:1px solid #2a3d4f;border-radius:10px;background:#080f16;color:#f1f5f9;outline:none}input:focus,select:focus{border-color:#3377a9;box-shadow:0 0 0 3px rgba(45,168,255,.08)}
.rules,.order-drawer{margin:10px 0}.rules summary,.order-drawer>summary{list-style:none;padding:11px 12px;border:1px solid #243545;border-radius:11px;background:#0d151e;color:#aebac7;font-size:10.5px;font-weight:900;cursor:pointer}.rules summary::-webkit-details-marker,.order-drawer>summary::-webkit-details-marker{display:none}.rules summary:after,.order-drawer>summary:after{content:"+";float:right;color:#6e8195;font-size:15px}.rules[open] summary:after,.order-drawer[open]>summary:after{content:"−"}.fixed-rule-box{margin:7px 0 0;padding:10px 11px;border:1px solid #1f3040;border-radius:10px;background:#091119}.fixed-rule-line{padding:5px 0;border-bottom:1px solid rgba(255,255,255,.045);font-size:10.5px;line-height:1.45;color:#c9d3dd}.fixed-rule-line:last-child{border-bottom:0}.fixed-rule-line b{display:inline-grid;place-items:center;width:18px;height:18px;margin-right:5px;border-radius:5px;background:#133452;color:#79caff}
.auto-actions{display:grid;grid-template-columns:minmax(0,1fr) 88px;gap:8px;margin-top:12px}.primary,.secondary,.stop-action{min-height:44px;border-radius:11px;padding:11px 13px;font-weight:950}.primary{width:100%;background:linear-gradient(180deg,#168bea,#0870cf);box-shadow:0 7px 18px rgba(0,112,207,.18)}.secondary{background:#121e29;border:1px solid #2a3e50}.stop-action{background:#29171b;border:1px solid #61313a;color:#ff8490}.danger{background:linear-gradient(180deg,#c94455,#a92d3e)}.auto-command-msg{min-height:17px;margin:8px 2px 1px}.auto-command-msg.ok{color:#6ee4a9}.auto-command-msg.busy{color:#e9c65d}.auto-command-msg.err{color:#ff7b89}.auto-running{color:#55e5a3}.auto-stopped{color:#ff8d78}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px}.order-card{margin-top:8px}.order-drawer .card{border-radius:0 0 14px 14px;margin-top:-1px}.compound-note{margin:7px 2px 0;line-height:1.45}
.settings-card{padding:5px 14px 14px}.setting-row{min-height:46px;border-bottom:1px solid rgba(255,255,255,.055);font-size:11px}.setting-row span{color:var(--muted)}.setting-row b{max-width:68%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px}.settings-actions{display:grid;gap:8px;padding-top:12px}.install-card p{margin:0;color:#a8b4c1;font-size:11px;line-height:1.55}
nav{position:fixed;left:0;right:0;bottom:0;z-index:30;height:calc(72px + env(safe-area-inset-bottom));padding:0 4px env(safe-area-inset-bottom);display:grid;grid-template-columns:repeat(5,1fr);background:rgba(6,9,13,.92);border-top:1px solid rgba(255,255,255,.07);backdrop-filter:blur(24px) saturate(160%)}nav button{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;min-width:0;padding:6px 1px;background:none;border-radius:0;color:#617184;font-size:9.5px;font-weight:850}nav button .nav-icon{font-size:18px;line-height:18px;font-weight:500}nav button.active{color:#79caff}nav button.active .nav-icon{filter:drop-shadow(0 0 8px rgba(45,168,255,.45))}
.overlay{position:fixed;inset:0;z-index:100;display:flex;align-items:center;justify-content:center;padding:22px;background:rgba(3,6,10,.94);backdrop-filter:blur(14px)}.overlay.hidden{display:none}.pair-card{width:min(390px,100%);padding:26px 22px;border:1px solid #263847;border-radius:22px;background:linear-gradient(160deg,#131e29,#0d141c);box-shadow:0 24px 70px rgba(0,0,0,.45);text-align:center}.pair-card h1{margin:5px 0 7px;font-size:22px;letter-spacing:-.6px}.pair-card p{margin:0;color:#8e9cab;font-size:11px;line-height:1.6}.pair-card input{text-align:center;font-size:26px;letter-spacing:9px;font-weight:950;margin:16px 0 10px}
@media(min-width:620px){main{padding-left:18px;padding-right:18px}.analysis-grid{grid-template-columns:1fr 1fr}.analysis-grid .analysis-card:first-child{grid-column:1/-1}}
@media(max-width:390px){main{padding:9px}.hero-card{padding:15px}.card{padding:12px}.metric-grid.four{grid-template-columns:1fr 1fr}.chart-card{margin-left:-1px;margin-right:-1px}#chartCanvas{height:280px}.hero-price{font-size:22px}}"""

APP_JS = r"""
let token=localStorage.getItem('puma_token')||'';
let state=null, pollTimer=null, commandTimers={};
let autoCommandBusy=false, autoCommandWanted=null;

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
    document.getElementById('connBadge').innerHTML='<i></i> ONLINE';
    document.getElementById('connBadge').className='badge on';
  }catch(e){
    if(e.message==='AUTH'){document.getElementById('pair').classList.remove('hidden');}
    document.getElementById('connBadge').innerHTML='<i></i> OFFLINE';
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
  const homeAutoStatus=document.getElementById('homeAutoStatus');
  const homeSeed=document.getElementById('homeSeed');
  const homeRisk=document.getElementById('homeRisk');
  if(homeAutoStatus){
    homeAutoStatus.textContent=au.enabled?'실행 중':'중지';
    homeAutoStatus.className='v '+(au.enabled?'auto-running':'auto-stopped');
  }
  const autoStatus=document.getElementById('autoStatus');
  const actuallyEnabled=!!au.enabled;
  const shownEnabled=autoCommandBusy && autoCommandWanted!==null ? !!autoCommandWanted : actuallyEnabled;
  autoStatus.textContent=autoCommandBusy
    ? (autoCommandWanted?'시작 처리 중…':'중지 처리 중…')
    : (actuallyEnabled?'실행 중':'중지');
  autoStatus.className='auto-status '+(shownEnabled?'auto-running':'auto-stopped');
  const autoStatusOrb=document.getElementById('autoStatusOrb');
  if(autoStatusOrb)autoStatusOrb.className='status-orb '+(shownEnabled?'on':'');
  document.getElementById('autoScope').textContent=actuallyEnabled?(au.scope_label||'-'):'-';
  document.getElementById('autoLock').style.display=unlocked?'none':'block';
  const startBtn=document.getElementById('autoStartBtn');
  const stopBtn=document.getElementById('autoStopBtn');
  startBtn.disabled=!unlocked || actuallyEnabled || autoCommandBusy;
  stopBtn.disabled=!actuallyEnabled || autoCommandBusy;
  startBtn.textContent=autoCommandBusy&&autoCommandWanted?'시작 처리 중…':'▶ 자동매매 시작';
  stopBtn.textContent=autoCommandBusy&&autoCommandWanted===false?'중지 처리 중…':'■ 자동매매 중지';
  if(!autoCommandBusy){
    const msg=document.getElementById('autoCommandMsg');
    if(msg && !msg.classList.contains('err')){
      msg.textContent=actuallyEnabled?'PC 자동매매 실행 중':'PC 자동매매 중지';
      msg.className='muted small auto-command-msg '+(actuallyEnabled?'ok':'');
    }
  }
  const autoSettings=au.settings||{};
  const seed=Number(autoSettings.seed_capital??autoSettings.order_budget??0);
  const dayStartSeed=Number(autoSettings.daily_start_seed??seed);
  const lossPct=Number(autoSettings.daily_loss_pct??0);
  if(homeSeed)homeSeed.textContent=money(seed)+' 원';
  if(homeRisk){
    homeRisk.textContent=autoSettings.daily_loss_locked?'중단':'가능';
    homeRisk.style.color=autoSettings.daily_loss_locked?'#ff7b89':'#6ee4a9';
  }
  const seedEl=document.getElementById('autoSeed');
  const lossEl=document.getElementById('autoDailyLoss');
  const riskEl=document.getElementById('autoRiskState');
  const phaseEl=document.getElementById('autoPhaseNote');
  seedEl.textContent=money(seed)+' 원';
  lossEl.textContent=(lossPct>0?'+':'')+lossPct.toFixed(2)+'%';
  lossEl.style.color=lossPct<0?'#ff7885':(lossPct>0?'#61ff8f':'#edf5ff');
  if(autoSettings.phase1_complete){
    riskEl.textContent='1차 목표 도달';
    riskEl.style.color='#ffd65a';
  }else if(autoSettings.daily_loss_locked){
    riskEl.textContent='오늘 신규매수 중단';
    riskEl.style.color='#ff7885';
  }else{
    riskEl.textContent='신규매수 가능';
    riskEl.style.color='#61ff8f';
  }
  phaseEl.textContent='당일 시작 시드 '+money(dayStartSeed)+'원 · 1차 목표 3,000,000원 · 하루 -4% 도달 시 그날 신규매수 중단';
  if(document.getElementById('autoSource')) document.getElementById('autoSource').value='HERO4';
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
  if(autoCommandBusy)return;
  if(state?.auto?.enabled){setAutoMessage('이미 자동매매 실행 중입니다.','ok');return;}
  if(!state?.mobile_live_unlocked){setAutoMessage('설정에서 실전 잠금을 최초 1회 해제하세요.','err');return;}
  const scope=document.getElementById('autoScopeSelect').value;
  if(scope==='SELECTED'&&!state?.selected?.code){setAutoMessage('먼저 종목을 선택하세요.','err');return}
  const payload={
    type:'auto_start',
    scope,
    code:state?.selected?.code||'',
    name:state?.selected?.name||'',
    candidate_source:(scope==='ALL'?'HERO4':document.getElementById('autoSource').value)
  };
  setAutoPending(true);
  try{
    const r=await api('/api/command',{method:'POST',body:JSON.stringify(payload)});
    pollAutoResult(r.request_id,true);
  }catch(e){
    finishAutoPending(false,'자동매매 시작 실패: '+e.message,true);
  }
}
async function stopAuto(){
  if(autoCommandBusy)return;
  if(!state?.auto?.enabled){setAutoMessage('이미 자동매매 중지 상태입니다.');return;}
  setAutoPending(false);
  try{
    const r=await api('/api/command',{method:'POST',body:JSON.stringify({type:'auto_stop'})});
    pollAutoResult(r.request_id,false);
  }catch(e){
    finishAutoPending(true,'자동매매 중지 실패: '+e.message,true);
  }
}
function setAutoPending(wanted){
  autoCommandBusy=true;
  autoCommandWanted=!!wanted;
  setAutoMessage(wanted?'PC에 자동매매 시작 요청 중…':'PC에 자동매매 중지 요청 중…','busy');
  if(state)render(state);
}
function finishAutoPending(actual,message,isError=false){
  autoCommandBusy=false;
  autoCommandWanted=null;
  if(state?.auto)state.auto.enabled=!!actual;
  setAutoMessage(message,isError?'err':(actual?'ok':''));
  if(state)render(state);
  refreshNow();
}
function setAutoMessage(message,kind=''){
  const el=document.getElementById('autoCommandMsg');
  if(!el)return;
  el.textContent=message||'';
  el.className='muted small auto-command-msg '+kind;
}
function pollAutoResult(id,wanted){
  let count=0, stopped=false;
  const finish=(actual,message,error=false)=>{
    if(stopped)return;
    stopped=true;
    clearInterval(t);
    finishAutoPending(actual,message,error);
  };
  const check=async()=>{
    try{
      const r=await api('/api/command/'+id);
      if(r.status==='done'){
        finish(!!wanted,r.result?.message||('자동매매 '+(wanted?'시작':'중지')+' 완료'));
        return;
      }
      if(r.status==='error'){
        finish(!wanted,'자동매매 '+(wanted?'시작':'중지')+' 실패: '+(r.error||'오류'),true);
        return;
      }
    }catch(e){
      finish(!wanted,'처리 결과 확인 실패: '+e.message,true);
      return;
    }
    if(++count>40){
      finish(!wanted,'처리 결과 확인 시간이 초과되었습니다. PC 상태를 다시 확인하세요.',true);
    }
  };
  const t=setInterval(check,150);
  check();
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
const CACHE='puma-mobile-v2';
const ASSETS=['/','/styles.css','/app.js','/manifest.webmanifest','/icon.svg'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS))));
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('fetch',e=>{
  if(e.request.url.includes('/api/')) return;
  e.respondWith(fetch(e.request).then(r=>{let x=r.clone();caches.open(CACHE).then(c=>c.put(e.request,x));return r}).catch(()=>caches.match(e.request)));
});
"""

ICON_SVG = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#39b8ff"/><stop offset="1" stop-color="#086fd4"/></linearGradient></defs>
<rect width="512" height="512" rx="118" fill="#070a0f"/>
<rect x="70" y="70" width="372" height="372" rx="96" fill="url(#g)"/>
<path d="M170 354V158h103c58 0 96 31 96 82 0 53-39 85-101 85h-40v29h-58zm58-78h37c28 0 44-12 44-35 0-22-16-34-44-34h-37v69z" fill="white"/>
</svg>"""

MANIFEST = {
    "name": "PUMA STOCK MOBILE",
    "short_name": "PUMA Mobile",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#070a0f",
    "theme_color": "#070a0f",
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
