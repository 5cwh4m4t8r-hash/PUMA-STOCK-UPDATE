from __future__ import annotations

from statistics import mean

from .swing import ema, normalize_candles


def build_watermelon(rows: list[dict]) -> list[int]:
    """PUMA 수박형 하단 밴드.

    반환값: 1=상승형(초록), -1=하락형(빨강), 0=표시 없음.
    차트 전체를 연속 도색하지 않고 타점 주변에 짧게 표시하도록 설계했다.
    특정 비공개/유료 지표 공식을 복제하지 않는다.
    """
    candles = normalize_candles(rows or [])
    n = len(candles)
    if n == 0:
        return []
    if n < 25:
        return [0] * n

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    vols = [c["volume"] for c in candles]
    e5 = ema(closes, 5)
    e20 = ema(closes, 20)
    e60 = ema(closes, 60)

    raw = [0] * n
    for i in range(22, n):
        if not e5[i] or not e20[i] or not e60[i]:
            continue
        avg_vol = mean(vols[i-20:i]) if i >= 20 else 0.0
        vr = vols[i] / avg_vol if avg_vol else 0.0
        mom3 = (closes[i] / closes[i-3] - 1.0) * 100 if closes[i-3] else 0.0
        prior_hi = max(highs[i-10:i])
        prior_lo = min(lows[i-10:i])

        bullish = (
            closes[i] >= e20[i]
            and e5[i] > e20[i]
            and mom3 >= 0.55
            and (vr >= 1.12 or closes[i] > prior_hi)
        )
        bearish = (
            closes[i] <= e20[i]
            and e5[i] < e20[i]
            and mom3 <= -0.55
            and (vr >= 1.12 or closes[i] < prior_lo)
        )
        raw[i] = 1 if bullish else (-1 if bearish else 0)

    # 한 방향 신호가 오래 지속돼도 바닥 전체를 칠하지 않는다.
    # 새 신호 발생 지점부터 최대 4봉만 짧은 밴드로 표시.
    out = [0] * n
    active = 0
    streak = 0
    cooldown = 0
    for i, state in enumerate(raw):
        if state == 0:
            active = 0
            streak = 0
            cooldown = max(0, cooldown - 1)
            continue
        if state != active:
            active = state
            streak = 0
        if streak < 4 and cooldown == 0:
            out[i] = state
            streak += 1
            if streak == 4:
                cooldown = 3
        elif cooldown > 0:
            cooldown -= 1
    return out
