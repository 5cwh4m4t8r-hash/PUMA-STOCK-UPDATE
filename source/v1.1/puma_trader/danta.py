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
    PUMA 해석판이다. 특정 유료/비공개 검색식의 복제가 아니다.
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

    latest_day = str(candles[-1].get("date", ""))[:8]
    day_vol = sum(c["volume"] for c in candles if str(c.get("date", ""))[:8] == latest_day)
    daily = normalize_candles(daily_rows or [])
    prior_daily = [c for c in daily if str(c.get("date", ""))[:8] != latest_day]
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

    # 패턴 점수는 시간과 분리한다. 장 마감 후 복기해도 패턴 자체의 강도를 볼 수 있고,
    # 실시간 진입 가능 여부만 검색 시간으로 게이트한다.
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
    details = {
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
