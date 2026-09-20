from __future__ import annotations

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
    total = 0.0
    for i, v in enumerate(values):
        total += float(v)
        if i >= period:
            total -= float(values[i-period])
        if i >= period - 1:
            out[i] = total / period
    return out


def build_puma_watermelon(candles: List[dict], arrow_series: dict | None = None) -> dict:
    """Strict PUMA watermelon approximation.

    The proprietary original formula is not public. This proxy deliberately
    shows ONLY high-confluence zones. Stage 1/2 are kept internally for
    diagnostics; the chart receives only sparse confirmed events.

    Confirmed zone requires:
      - EMA112/224/448 convergence <= 7.5%
      - recent EMA224 reclaim
      - 4 of last 5 closes holding EMA224
      - current price retesting/near EMA224
      - prior volume expansion >= 1.8x 20-bar average
      - current pullback volume <= 1.0x 20-bar average
      - either a recent user-supplied arrow or especially tight convergence
      - composite score >= 85
    A 20-bar cooldown suppresses repeated markers in the same setup.
    """
    n = len(candles)
    stages = [0] * n
    scores = [0] * n
    reasons = [""] * n
    confirmed = [False] * n
    display = [0] * n
    if n == 0:
        return {
            "watermelon_stage": stages,
            "watermelon_score": scores,
            "watermelon_reason": reasons,
            "watermelon_confirmed": confirmed,
            "watermelon_display": display,
        }

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

    last_display = -10**9
    for i in range(n):
        if e224[i] is None:
            continue

        price = closes[i]
        ema224 = float(e224[i])
        longs = [x for x in (e112[i], e224[i], e448[i]) if isinstance(x, (int, float))]
        spread_pct = ((max(longs) - min(longs)) / price * 100.0) if len(longs) >= 2 and price else 999.0

        convergence = spread_pct <= 7.5
        very_tight = spread_pct <= 5.0
        near224 = ema224 > 0 and lows[i] <= ema224 * 1.025 and price >= ema224 * 0.995

        recent_cross = False
        for j in range(max(1, i - 20), i + 1):
            if e224[j] is None or e224[j-1] is None:
                continue
            if closes[j-1] <= float(e224[j-1]) and closes[j] > float(e224[j]):
                recent_cross = True
                break

        hold_count = 0
        valid_hold = 0
        for j in range(max(0, i - 4), i + 1):
            if e224[j] is not None:
                valid_hold += 1
                if closes[j] >= float(e224[j]) * 0.995:
                    hold_count += 1
        held = valid_hold >= 4 and hold_count >= 4

        impulse = False
        for j in range(max(20, i - 20), i + 1):
            if v20[j] and vols[j] >= float(v20[j]) * 1.80:
                impulse = True
                break

        pullback_calm = bool(v20[i] and vols[i] <= float(v20[i]) * 1.00)

        arrow_recent = False
        for arr in (pink, blue, red):
            lo = max(0, i - 5)
            if isinstance(arr, list) and any(bool(x) for x in arr[lo:i+1]):
                arrow_recent = True
                break

        score = 0
        tags = []
        if convergence:
            score += 25; tags.append(f"장기이평 수렴 {spread_pct:.1f}%")
        if near224:
            score += 20; tags.append("224EMA 근접/지지")
        if recent_cross:
            score += 20; tags.append("최근 224EMA 돌파")
        if held:
            score += 15; tags.append("224EMA 위 4/5봉 안착")
        if impulse:
            score += 10; tags.append("선행 거래량 1.8배+")
        if pullback_calm:
            score += 5; tags.append("눌림 거래량 안정")
        if arrow_recent:
            score += 10; tags.append("사용자 화살표 동반")
        score = min(100, score)

        stage = 0
        if convergence and near224:
            stage = 1
        if stage and recent_cross and held:
            stage = 2

        strict = bool(
            convergence and near224 and recent_cross and held and impulse
            and pullback_calm and (arrow_recent or very_tight) and score >= 85
        )
        if strict:
            stage = 3
            confirmed[i] = True
            if i - last_display >= 20:
                display[i] = 3
                last_display = i

        stages[i] = stage
        scores[i] = score
        reasons[i] = " · ".join(tags[:5]) if tags else "조건 미충족"

    return {
        "watermelon_stage": stages,
        "watermelon_score": scores,
        "watermelon_reason": reasons,
        "watermelon_confirmed": confirmed,
        "watermelon_display": display,
    }
