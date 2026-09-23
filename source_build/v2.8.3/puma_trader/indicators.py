from __future__ import annotations

from typing import List, Optional


def hero_eavg(values: List[float], period: int) -> List[Optional[float]]:
    """Kiwoom EAVG-compatible cumulative EMA used everywhere in PUMA.

    One shared implementation is critical: chart MA lines, arrow formulas,
    Bowl-3 and market-path logic must not calculate different 112/224/448
    values from the same candles.
    """
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0 or not values:
        return out
    k = 2.0 / (float(period) + 1.0)
    prev = float(values[0])
    out[0] = prev
    for i in range(1, len(values)):
        prev = float(values[i]) * k + prev * (1.0 - k)
        out[i] = prev
    return out


def _midpoint(candles: List[dict], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(candles)
    if period <= 0:
        return out
    for i in range(period - 1, len(candles)):
        seg = candles[i - period + 1:i + 1]
        hi = max(float(c["high"]) for c in seg)
        lo = min(float(c["low"]) for c in seg)
        out[i] = (hi + lo) / 2.0
    return out


def ichimoku_cloud(
    candles: List[dict],
    *,
    tenkan_period: int = 9,
    kijun_period: int = 26,
    span_b_period: int = 52,
    shift: int = 26,
) -> dict:
    """Standard Ichimoku leading spans 1/2.

    선행스팬1 = (전환선 + 기준선) / 2, +26칸 선행
    선행스팬2 = 52기간 최고/최저 중간값, +26칸 선행

    Arrays include the future shift area so the chart can display the cloud
    beyond the latest candle, matching a trading-terminal style chart.
    """
    n = len(candles)
    if not candles:
        return {"cloud_a": [], "cloud_b": [], "future_count": 0}

    tenkan = _midpoint(candles, tenkan_period)
    kijun = _midpoint(candles, kijun_period)
    span_b_src = _midpoint(candles, span_b_period)

    total = n + max(0, int(shift))
    cloud_a: List[Optional[float]] = [None] * total
    cloud_b: List[Optional[float]] = [None] * total

    for i in range(n):
        dest = i + shift
        if dest >= total:
            continue
        if tenkan[i] is not None and kijun[i] is not None:
            cloud_a[dest] = (tenkan[i] + kijun[i]) / 2.0
        if span_b_src[i] is not None:
            cloud_b[dest] = span_b_src[i]

    return {
        "cloud_a": cloud_a,
        "cloud_b": cloud_b,
        "future_count": max(0, int(shift)),
    }
