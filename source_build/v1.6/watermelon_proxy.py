from __future__ import annotations

from statistics import mean
from typing import List, Optional

def _ema(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    k = 2.0 / (period + 1.0)
    prev = seed
    for i in range(period, len(values)):
        prev = float(values[i]) * k + prev * (1.0 - k)
        out[i] = prev
    return out


def _rolling_avg(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0:
        return out
    total = 0.0
    for i, v in enumerate(values):
        total += float(v)
        if i >= period:
            total -= float(values[i-period])
        if i >= period - 1:
            out[i] = total / period
    return out


def build_puma_watermelon(candles: List[dict], arrow_series: dict | None = None) -> dict:
    """Public-observation-based PUMA approximation of the 'watermelon' idea.

    This is intentionally NOT presented as the proprietary indicator formula.
    It encodes public/common observations around:
      - long MA convergence around EMA112/224/448,
      - price reclaiming/holding EMA224,
      - pullback toward long support after breakout,
      - prior volume expansion followed by calmer pullback,
      - confirmation from the user's known arrow signals.

    Stage:
      0 = none
      1 = approach/convergence
      2 = reclaim + hold/pullback
      3 = reinforced setup
    """
    n = len(candles)
    stages = [0] * n
    scores = [0] * n
    reasons = [""] * n
    if n == 0:
        return {"watermelon_stage": stages, "watermelon_score": scores, "watermelon_reason": reasons}

    closes = [float(c["close"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    vols = [float(c["volume"]) for c in candles]
    e112 = _ema(closes, 112)
    e224 = _ema(closes, 224)
    e448 = _ema(closes, 448)
    v20 = _rolling_avg(vols, 20)

    arrow_series = arrow_series or {}
    pink = arrow_series.get("signal_pink", [False] * n)
    blue = arrow_series.get("signal_blue", [False] * n)
    red = arrow_series.get("signal_red", [False] * n)

    for i in range(n):
        if e224[i] is None:
            continue
        price = closes[i]
        ema224 = float(e224[i])

        longs = [x for x in (e112[i], e224[i], e448[i]) if isinstance(x, (int, float))]
        spread_pct = ((max(longs) - min(longs)) / price * 100.0) if len(longs) >= 2 and price else 999.0
        convergence = spread_pct <= 10.0

        near224 = ema224 > 0 and lows[i] <= ema224 * 1.035 and price >= ema224 * 0.985
        above224 = price >= ema224

        start = max(1, i - 35)
        recent_cross = False
        for j in range(start, i + 1):
            if e224[j] is None or e224[j-1] is None:
                continue
            if closes[j-1] <= float(e224[j-1]) and closes[j] > float(e224[j]):
                recent_cross = True
                break

        hold_start = max(0, i - 4)
        hold_count = sum(
            1 for j in range(hold_start, i + 1)
            if e224[j] is not None and closes[j] >= float(e224[j]) * 0.99
        )
        held = hold_count >= 3

        slope_ok = True
        if i >= 10 and e224[i-10] is not None:
            slope_ok = ema224 >= float(e224[i-10]) * 0.99

        impulse = False
        imp_start = max(20, i - 25)
        for j in range(imp_start, i + 1):
            if v20[j] and vols[j] >= float(v20[j]) * 1.45:
                impulse = True
                break
        pullback_calm = bool(v20[i] and vols[i] <= float(v20[i]) * 1.25)

        arrow_recent = False
        for arr in (pink, blue, red):
            lo = max(0, i - 8)
            if isinstance(arr, list) and any(bool(x) for x in arr[lo:i+1]):
                arrow_recent = True
                break

        score = 0
        tags = []
        if convergence:
            score += 20
            tags.append(f"장기이평 수렴 {spread_pct:.1f}%")
        if near224:
            score += 20
            tags.append("224EMA 근접/지지")
        if recent_cross:
            score += 20
            tags.append("최근 224EMA 돌파")
        if above224 and held:
            score += 15
            tags.append("224EMA 위 안착")
        if slope_ok:
            score += 5
        if impulse:
            score += 10
            tags.append("선행 거래량 확장")
        if pullback_calm:
            score += 5
            tags.append("눌림 거래량 안정")
        if arrow_recent:
            score += 10
            tags.append("사용자 화살표 동반")
        score = min(100, score)

        stage = 0
        if convergence and near224:
            stage = 1
        if stage >= 1 and recent_cross and above224 and held:
            stage = 2
        if stage >= 2 and (impulse or arrow_recent) and pullback_calm:
            stage = 3

        stages[i] = stage
        scores[i] = score
        reasons[i] = " · ".join(tags[:4]) if tags else "조건 미충족"

    return {
        "watermelon_stage": stages,
        "watermelon_score": scores,
        "watermelon_reason": reasons,
    }
