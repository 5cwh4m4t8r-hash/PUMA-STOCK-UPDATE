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
    day_vol = sum(c["volume"] for c in candles if _date_key(c.get("date")) == latest_day)
    daily = normalize_candles(daily_rows or [])
    # 과거 날짜 복기 시 미래 일봉을 참조하지 않도록 선택일 이전 거래일만 비교에 사용.
    prior_daily = [c for c in daily if _date_key(c.get("date")) < latest_day]
    prior_vols = [c["volume"] for c in prior_daily[-5:] if c["volume"] > 0]
    ref_day_vol = mean(prior_vols) if prior_vols else 0.0
    day_volume_ratio = day_vol / ref_day_vol if ref_day_vol else 0.0

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

    score = 0
    score += 25 if baseline_lift else (12 if baseline_alive else 0)
    score += 15 if ema_stack else 0
    score += 20 if volume_ratio_5m >= 1.8 else (10 if volume_ratio_5m >= 1.2 else 0)
    score += 15 if day_volume_ratio >= 1.0 else (8 if day_volume_ratio >= 0.6 else 0)
    score += 15 if breakout else (10 if pullback_hold else 0)
    score += 10 if steep else 0
    score = min(100, score)

    candidate = bool(in_time and baseline_alive and score >= 70 and (breakout or pullback_hold))
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
    reasons.append("기준선 위" if baseline_alive else "기준선 이탈")
    reasons.append("EMA 정배열" if ema_stack else "EMA 정배열 미확인")
    reasons.append(f"5분 거래량 {volume_ratio_5m:.2f}배")
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
        "장초반 누적 거래량": f"최근5일 일평균의 {day_volume_ratio:.2f}배" if ref_day_vol else "일봉 비교 데이터 부족",
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
