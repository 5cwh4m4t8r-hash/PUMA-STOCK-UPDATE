from __future__ import annotations

from typing import List, Optional

from .indicators import hero_eavg


def _ema(values: List[float], period: int) -> List[Optional[float]]:
    """Use the same Hero/Kiwoom EAVG engine as every visible PUMA price EMA."""
    return hero_eavg(values, period)


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


def _latest_reclaim_index(closes, ema_line, i: int, lookback: int = 4) -> int:
    """Return the latest genuine reclaim bar, or -1.

    A watermelon marker should belong to the actual turn area. Looking too far
    back lets a stale long-MA cross keep qualifying later candles, which makes
    markers appear where they no longer belong.
    """
    lo = max(1, i - lookback + 1)
    for j in range(i, lo - 1, -1):
        cur = ema_line[j]
        prev = ema_line[j - 1]
        if cur is None or prev is None:
            continue
        if closes[j - 1] < float(prev) * 0.995 and closes[j] >= float(cur) * 0.995:
            return j
    return -1


def _crossed_or_reclaimed(closes, ema_line, i: int, lookback: int = 4) -> bool:
    return _latest_reclaim_index(closes, ema_line, i, lookback) >= 0


def build_puma_watermelon(
    candles: List[dict],
    arrow_series: dict | None = None,
    *,
    acc_flags: list[bool] | None = None,
) -> dict:
    """PUMA watermelon approximation v2.

    Important:
      The proprietary Stock Dante watermelon formula is not public.
      This is a transparent approximation built only from observable/public
      concepts: bottom-area context, 112/224 long-MA retest/reclaim,
      reversal/settling, prior volume/accumulation, and arrow confluence.

    Goal:
      Place sparse markers around the *first bottom/reversal entry zone*,
      rather than waiting until price is already far above EMA224.

    Uses only current/past bars. No future-bar confirmation is used.
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
    opens = [float(c["open"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    vols = [float(c["volume"]) for c in candles]

    e20 = _ema(closes, 20)
    e60 = _ema(closes, 60)
    e112 = _ema(closes, 112)
    e224 = _ema(closes, 224)
    e448 = _ema(closes, 448)
    v20 = _rolling_avg(vols, 20)

    arrow_series = arrow_series or {}
    arrow_keys = ("signal_pink", "signal_blue", "signal_red", "signal_black")
    arrows = [arrow_series.get(k, [False] * n) for k in arrow_keys]
    acc_flags = list(acc_flags or [False] * n)
    if len(acc_flags) < n:
        acc_flags.extend([False] * (n - len(acc_flags)))

    last_display = -10**9
    min_display_gap = 20

    for i in range(n):
        if i < 20 or e112[i] is None:
            continue

        price = closes[i]
        if price <= 0:
            continue

        # Publicly observable Dante context: falling/bottom area, not chasing highs.
        history = closes[max(0, i - 119):i + 1]
        recent_high = max(history) if history else price
        drawdown_pct = (recent_high - price) / recent_high * 100.0 if recent_high else 0.0
        bottom_context = drawdown_pct >= 10.0

        # Use whichever of EMA112 / EMA224 is actually closest to price.
        anchors = []
        if e112[i] is not None:
            anchors.append(("112", float(e112[i]), e112))
        if e224[i] is not None:
            anchors.append(("224", float(e224[i]), e224))
        if not anchors:
            continue
        anchor_name, anchor, anchor_line = min(
            anchors, key=lambda item: abs(price - item[1]) / max(price, 1e-9)
        )
        distance_pct = abs(price - anchor) / anchor * 100.0 if anchor else 999.0
        wick_touch = lows[i] <= anchor * 1.035 and price >= anchor * 0.970
        near_long = bool(distance_pct <= 6.0 or wick_touch)

        reclaim_idx = _latest_reclaim_index(closes, anchor_line, i, 4)
        reclaim = reclaim_idx >= 0
        reclaim_recent = reclaim and (i - reclaim_idx <= 2)

        valid_hold = 0
        hold_count = 0
        for j in range(max(0, i - 2), i + 1):
            line = anchor_line[j]
            if line is None:
                continue
            valid_hold += 1
            if closes[j] >= float(line) * 0.985:
                hold_count += 1
        settled = valid_hold >= 2 and hold_count >= 2

        # Avoid markers after the move is already stretched away from the long MA.
        not_overextended = bool(anchor > 0 and price <= anchor * 1.10)

        # Bottom-turn behavior: positive candle or at least close recovery.
        reversal = bool(
            (price >= opens[i] and (i == 0 or price >= closes[i - 1] * 0.995))
            or (i > 0 and price > closes[i - 1] * 1.01)
        )

        # Early turn confirmation: short EMA recovery/rising, but not a hard gate.
        ema20_recovery = False
        if e20[i] is not None and price >= float(e20[i]) * 0.995:
            if i < 3 or e20[i - 3] is None:
                ema20_recovery = True
            else:
                ema20_recovery = float(e20[i]) >= float(e20[i - 3]) * 0.995

        reverse_order = False
        if e224[i] is not None:
            reverse_order = float(e112[i]) <= float(e224[i]) * 1.015
            if e448[i] is not None:
                reverse_order = reverse_order and float(e224[i]) <= float(e448[i]) * 1.015

        impulse = False
        for j in range(max(20, i - 15), i + 1):
            if v20[j] and vols[j] >= float(v20[j]) * 1.50:
                impulse = True
                break

        acc_recent = any(bool(x) for x in acc_flags[max(0, i - 20):i + 1])
        calm = bool(v20[i] and vols[i] <= float(v20[i]) * 1.25)

        arrow_recent = False
        lo = max(0, i - 5)
        for arr in arrows:
            if isinstance(arr, list) and any(bool(x) for x in arr[lo:i + 1]):
                arrow_recent = True
                break

        score = 0
        tags = []
        if bottom_context:
            score += 20; tags.append(f"바닥권 -{drawdown_pct:.0f}%")
        if near_long:
            score += 20; tags.append(f"EMA{anchor_name} 근접 {distance_pct:.1f}%")
        if reclaim:
            score += 20; tags.append(f"EMA{anchor_name} 재돌파")
        if settled:
            score += 10; tags.append("장기선 위 2/3봉 안착")
        if reversal:
            score += 10; tags.append("반등봉/종가회복")
        if ema20_recovery:
            score += 5; tags.append("단기선 회복")
        if reverse_order:
            score += 10; tags.append("장기이평 역배열/수렴")
        if impulse or acc_recent:
            score += 10; tags.append("선행 거래량/매집")
        if calm:
            score += 5; tags.append("눌림 거래량 안정")
        if arrow_recent:
            score += 10; tags.append("화살표 동반")
        score = min(100, score)

        stage = 0
        if bottom_context and near_long:
            stage = 1
        if stage and reclaim and reversal:
            stage = 2

        # Earlier than v1: marker is allowed near the initial reclaim/turning area.
        # Still require bottom context + long-MA proximity + actual reclaim.
        # Final marker is intentionally strict. A loose arrow overlap alone is
        # not evidence for watermelon. Require a *recent* long-MA reclaim,
        # actual hold/settling, short-line recovery, and objective volume or
        # accumulation evidence. This favors missing a marginal marker over
        # painting false watermelon symbols across the chart.
        context_confirmed = bool(reverse_order or drawdown_pct >= 15.0)
        evidence_confirmed = bool(impulse or acc_recent)
        strict = bool(
            bottom_context
            and near_long
            and reclaim_recent
            and settled
            and reversal
            and ema20_recovery
            and not_overextended
            and context_confirmed
            and evidence_confirmed
            and score >= 80
        )

        if strict:
            stage = 3
            confirmed[i] = True
            if i - last_display >= min_display_gap:
                display[i] = 3
                last_display = i

        stages[i] = stage
        scores[i] = score
        reasons[i] = " · ".join(tags[:6]) if tags else "조건 미충족"

    return {
        "watermelon_stage": stages,
        "watermelon_score": scores,
        "watermelon_reason": reasons,
        "watermelon_confirmed": confirmed,
        "watermelon_display": display,
    }
