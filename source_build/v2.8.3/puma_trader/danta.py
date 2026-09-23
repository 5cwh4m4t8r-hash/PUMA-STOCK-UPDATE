from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Dict, List, Optional

from .swing import ema, normalize_candles


@dataclass
class DantaAnalysis:
    stage: str
    score: int
    candidate: bool
    in_time: bool
    current_price: float
    kijun: float
    volume_ratio_5m: float
    day_volume_ratio: float
    momentum_pct: float
    breakout: bool
    pullback_hold: bool
    details: Dict[str, str]


def _date_key(raw) -> str:
    return "".join(ch for ch in str(raw or "") if ch.isdigit())[:8]


def _hm(raw) -> str:
    s = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(s) >= 12:
        return s[8:10] + ":" + s[10:12]
    return ""


def market_open_volume_ratio(candles_raw: List[dict], lookback_days: int = 5) -> dict:
    """09:00 이후 현재까지 누적 거래량을 최근 N일 같은 장초 구간과 비교."""
    candles = normalize_candles(candles_raw or [])
    if not candles:
        return {
            "ratio": 0.0, "current_volume": 0.0, "reference_volume": 0.0,
            "bars": 0, "days": 0, "open_price": 0.0, "price_from_open_pct": 0.0,
        }

    latest_day = _date_key(candles[-1].get("date"))
    today = [
        c for c in candles
        if _date_key(c.get("date")) == latest_day
        and (_hm(c.get("date")) == "" or _hm(c.get("date")) >= "09:00")
    ]
    if not today:
        return {
            "ratio": 0.0, "current_volume": 0.0, "reference_volume": 0.0,
            "bars": 0, "days": 0, "open_price": 0.0, "price_from_open_pct": 0.0,
        }

    bars = len(today)
    current_volume = sum(float(c.get("volume", 0) or 0) for c in today)
    open_price = float(today[0].get("open", 0) or 0)
    current_price = float(today[-1].get("close", 0) or 0)
    price_from_open_pct = ((current_price / open_price - 1.0) * 100.0) if open_price > 0 else 0.0

    prior_days = sorted({
        _date_key(c.get("date"))
        for c in candles
        if _date_key(c.get("date")) and _date_key(c.get("date")) < latest_day
    })[-max(1, int(lookback_days)):]

    comparable = []
    for day in prior_days:
        session = [
            c for c in candles
            if _date_key(c.get("date")) == day
            and (_hm(c.get("date")) == "" or _hm(c.get("date")) >= "09:00")
        ]
        if not session:
            continue
        # 현재 장의 경과 봉 수와 동일한 첫 N개 5분봉 누적량끼리 비교.
        sample = session[:bars]
        if len(sample) < min(bars, 2):
            continue
        vol = sum(float(c.get("volume", 0) or 0) for c in sample)
        if vol > 0:
            comparable.append(vol)

    reference = mean(comparable) if comparable else 0.0
    ratio = current_volume / reference if reference > 0 else 0.0
    return {
        "ratio": ratio,
        "current_volume": current_volume,
        "reference_volume": reference,
        "bars": bars,
        "days": len(comparable),
        "open_price": open_price,
        "price_from_open_pct": price_from_open_pct,
    }


def _datetime_from_candle(raw) -> datetime | None:
    s = "".join(ch for ch in str(raw or "") if ch.isdigit())
    try:
        if len(s) >= 14:
            return datetime.strptime(s[:14], "%Y%m%d%H%M%S")
        if len(s) >= 8:
            return datetime.strptime(s[:8] + "153000", "%Y%m%d%H%M%S")
    except Exception:
        return None
    return None


def available_minute_dates(rows: List[dict]) -> list[str]:
    candles = normalize_candles(rows or [])
    return sorted({d for d in (_date_key(c.get("date")) for c in candles) if len(d) == 8})


def slice_series_for_date(series: dict, target_date: str) -> dict:
    target_date = _date_key(target_date)
    candles = list(series.get("candles", []) or [])
    idx = [i for i, c in enumerate(candles) if _date_key(c.get("date")) == target_date]
    if not idx:
        return {"candles": []}

    out = {}
    blocked = {
        "box", "acc_flags",
        "signal_pink", "signal_blue", "signal_red", "signal_black",
        "signal_sar", "signal_bb40_22",
        "core_path", "path_breakout", "path_pullback", "path_rebreakout",
        "watermelon_stage", "watermelon_score", "watermelon_reason",
        "watermelon_confirmed", "watermelon_display",
    }
    for key, value in series.items():
        if key in blocked:
            continue
        if isinstance(value, list) and len(value) == len(candles):
            out[key] = [value[i] for i in idx]
        else:
            out[key] = value
    out["candles"] = [candles[i] for i in idx]
    return out


def _kijun_series(candles: List[dict], period: int = 26) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(candles)
    if period <= 0:
        return out
    for i in range(period - 1, len(candles)):
        seg = candles[i - period + 1:i + 1]
        hi = max(c["high"] for c in seg)
        lo = min(c["low"] for c in seg)
        out[i] = (hi + lo) / 2.0
    return out


def analyze_danta(
    minute_rows: List[dict],
    daily_rows: List[dict] | None = None,
    *,
    now: datetime | None = None,
    scan_start: str = "08:50",
    scan_end: str = "10:00",
) -> tuple[DantaAnalysis, dict]:
    """PUMA 단타 분석.

    5분봉, 기준선, 장초반 거래량, EMA 정배열, 돌파/눌림을 결합한
    PUMA 해석판이다. 단타 화면에는 일봉용 화살표/공구리/수박 등
    장기 패턴 오버레이를 표시하지 않는다. 실제 자동주문은 별도의
    가보자 엔진이 사용자 기준 + PUMA 2차 선별로 판정한다.
    """
    candles = normalize_candles(minute_rows or [])
    if len(candles) < 65:
        raise ValueError("5분봉 데이터가 65봉 이상 필요합니다.")

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    vols = [c["volume"] for c in candles]

    e5 = ema(closes, 5)
    e20 = ema(closes, 20)
    e60 = ema(closes, 60)
    kijun = _kijun_series(candles, 26)

    cur = closes[-1]
    k_now = float(kijun[-1] or 0.0)
    k_prev = float(kijun[-2] or k_now or 0.0)

    avg20 = mean(vols[-21:-1]) if len(vols) >= 21 else mean(vols[:-1])
    volume_ratio_5m = vols[-1] / avg20 if avg20 else 0.0

    latest_day = _date_key(candles[-1].get("date"))
    daily = normalize_candles(daily_rows or [])

    # 장초 힘은 '현재까지 누적 vs 과거 하루 전체'가 아니라
    # 09:00부터 현재까지 동일한 경과 5분봉 수의 최근 5일 평균과 비교한다.
    morning = market_open_volume_ratio(candles, 5)
    day_volume_ratio = float(morning.get("ratio", 0.0) or 0.0)
    session_open = float(morning.get("open_price", 0.0) or 0.0)
    price_from_open_pct = float(morning.get("price_from_open_pct", 0.0) or 0.0)
    morning_volume_burst = bool(day_volume_ratio >= 3.0)

    ema_stack = bool(e5[-1] and e20[-1] and e60[-1] and cur >= e5[-1] > e20[-1] > e60[-1])
    baseline_lift = bool(k_now > 0 and cur > k_now and k_now >= k_prev)
    baseline_alive = bool(k_now > 0 and cur >= k_now)

    prior_high = max(highs[-11:-1])
    breakout = cur > prior_high
    near_ema20 = bool(e20[-1] and lows[-1] <= e20[-1] * 1.008 and cur >= e20[-1])
    near_kijun = bool(k_now and lows[-1] <= k_now * 1.008 and cur >= k_now)
    pullback_hold = near_ema20 or near_kijun

    momentum_pct = (cur / closes[-4] - 1.0) * 100 if closes[-4] else 0.0
    steep = momentum_pct >= 1.2

    now = now or datetime.now()
    hm = now.strftime("%H:%M")
    in_time = scan_start <= hm <= scan_end

    # 장 시작 기준 단타 점수. 장초 거래량 300%+가 가장 큰 비중이며
    # 실제 후보 인정에도 필수조건으로 사용한다.
    score = 0
    if day_volume_ratio >= 5.0:
        score += 35
    elif day_volume_ratio >= 3.0:
        score += 30
    elif day_volume_ratio >= 2.0:
        score += 15
    elif day_volume_ratio >= 1.3:
        score += 7

    if price_from_open_pct >= 3.0:
        score += 18
    elif price_from_open_pct >= 1.5:
        score += 14
    elif price_from_open_pct >= 0.5:
        score += 9
    elif price_from_open_pct >= 0:
        score += 4

    score += 10 if baseline_lift else (5 if baseline_alive else 0)
    score += 8 if ema_stack else 0
    score += 10 if volume_ratio_5m >= 1.8 else (5 if volume_ratio_5m >= 1.2 else 0)
    score += 14 if breakout else (10 if pullback_hold else 0)
    score += 5 if steep else 0
    score = min(100, score)

    candidate = bool(
        in_time
        and morning_volume_burst
        and session_open > 0
        and cur >= session_open
        and baseline_alive
        and score >= 70
        and (breakout or pullback_hold)
    )
    if candidate:
        stage = "실시간 타점 후보"
    elif score >= 70 and not in_time:
        stage = "패턴 강함 / 검색시간 외"
    elif score >= 55 and baseline_alive:
        stage = "관찰 강화"
    elif baseline_alive:
        stage = "기준선 위 관찰"
    else:
        stage = "대기 / 기준선 이탈"

    data_time = str(candles[-1].get("date", "") or "-")
    reasons = []
    reasons.append(f"장초 거래량 {day_volume_ratio:.2f}배" + (" · 300%↑" if morning_volume_burst else ""))
    reasons.append(f"시초 대비 {price_from_open_pct:+.2f}%")
    reasons.append("기준선 위" if baseline_alive else "기준선 이탈")
    if breakout:
        reasons.append("최근 고점 돌파")
    elif pullback_hold:
        reasons.append("눌림 지지")
    else:
        reasons.append("돌파/눌림 미확인")

    details = {
        "간단 이유": " · ".join(reasons[:4]),
        "분석 기준일": latest_day,
        "검색 시간": f"{hm} / {scan_start}~{scan_end} · {'진입허용' if in_time else '시간외'}",
        "데이터 시각": data_time,
        "5분 기준선": f"{k_now:,.0f} · {'상승/지지' if baseline_lift else ('위 유지' if baseline_alive else '이탈')}",
        "PUMA 기준선(26)": f"{k_now:,.0f} · {'상승/지지' if baseline_lift else ('위 유지' if baseline_alive else '이탈')}",
        "EMA 5·20·60": "정배열 확인" if ema_stack else "정배열 미확인",
        "현재 5분봉 거래량": f"최근20봉 평균의 {volume_ratio_5m:.2f}배",
        "장초반 누적 거래량": (
            f"09:00~현재 / 최근{int(morning.get('days', 0))}일 같은구간 평균 "
            f"{day_volume_ratio:.2f}배 · {'힘 강함(300%+)' if morning_volume_burst else '300% 미달'}"
            if morning.get("reference_volume", 0) else "같은 시간대 비교 데이터 부족"
        ),
        "시초가 기준 힘": f"{session_open:,.0f} → {cur:,.0f} · {price_from_open_pct:+.2f}%",
        "단타 PUMA 점수": f"{score}/100 · 장초 거래량 300%+ {'필수충족' if morning_volume_burst else '미충족'}",
        "최근 고점 돌파": "확인" if breakout else "미확인",
        "눌림 지지": "EMA20/기준선 지지 확인" if pullback_hold else "지지 미확인",
        "상승 각도": f"최근 3봉 {momentum_pct:+.2f}% · {'강함' if steep else '보통'}",
    }

    series = {
        "candles": candles,
        "ema5": e5,
        "ema20": e20,
        "ema60": e60,
        "kijun": kijun,
    }
    return DantaAnalysis(
        stage=stage,
        score=score,
        candidate=candidate,
        in_time=in_time,
        current_price=cur,
        kijun=k_now,
        volume_ratio_5m=volume_ratio_5m,
        day_volume_ratio=day_volume_ratio,
        momentum_pct=momentum_pct,
        breakout=breakout,
        pullback_hold=pullback_hold,
        details=details,
    ), series


def analyze_danta_for_date(
    minute_rows: List[dict],
    daily_rows: List[dict] | None = None,
    target_date: str | None = None,
    *,
    scan_start: str = "08:50",
    scan_end: str = "10:00",
) -> tuple[DantaAnalysis, dict, str]:
    """특정 거래일 기준으로 5분봉 단타를 복기한다.

    이전 날짜의 봉은 EMA/기준선 계산 컨텍스트로 유지하고,
    target_date 이후 봉은 제거하여 미래 데이터를 보지 않는다.
    target_date가 없으면 최신 거래일을 분석한다.
    """
    candles = normalize_candles(minute_rows or [])
    days = available_minute_dates(candles)
    if not days:
        raise ValueError("날짜가 있는 5분봉 데이터가 없습니다.")

    requested = _date_key(target_date) if target_date else ""
    day = requested if requested in days else days[-1]
    context = [c for c in candles if _date_key(c.get("date")) <= day]
    selected = [c for c in context if _date_key(c.get("date")) == day]
    if not selected:
        raise ValueError(f"{day} 5분봉 데이터가 없습니다.")

    historical = day != days[-1]
    now = _datetime_from_candle(selected[-1].get("date")) if historical else None
    result, series = analyze_danta(
        context,
        daily_rows,
        now=now,
        scan_start=scan_start,
        scan_end=scan_end,
    )
    result.details["분석 기준일"] = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
    return result, series, day
