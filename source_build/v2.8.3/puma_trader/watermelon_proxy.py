from __future__ import annotations

from typing import List, Optional

from .indicators import hero_eavg, ichimoku_cloud


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


def _percentile(values: List[float], q: float) -> float:
    xs = sorted(float(x) for x in values if float(x) > 0)
    if not xs:
        return 0.0
    idx = min(len(xs) - 1, max(0, int(round((len(xs) - 1) * float(q)))))
    return float(xs[idx])


def _volume_footprint(candles: List[dict], vols: List[float], v20, i: int) -> dict:
    """Observable large-money footprint proxy; never identifies the actual actor."""
    avg = float(v20[i - 1]) if i > 0 and i - 1 < len(v20) and v20[i - 1] else 0.0
    ratio = float(vols[i]) / avg if avg > 0 else 0.0
    prev_vol = float(vols[i - 1]) if i > 0 else float(vols[i])
    volume_up_vs_prev = bool(i > 0 and float(vols[i]) > prev_vol)
    recent = vols[max(0, i - 60):i]
    p85 = _percentile(recent, 0.85)
    p95 = _percentile(recent, 0.95)
    abnormal = bool(
        volume_up_vs_prev
        and (
            ratio >= 1.80
            or (p85 > 0 and vols[i] >= p85 and ratio >= 1.35)
            or (p95 > 0 and vols[i] >= p95 and ratio >= 1.25)
        )
    )

    c = candles[i]
    op = float(c["open"])
    close = float(c["close"])
    high = float(c["high"])
    low = float(c["low"])
    prev_close = float(candles[i - 1]["close"]) if i > 0 else op
    rng = max(high - low, 1e-9)
    body = abs(close - op)
    upper = max(0.0, high - max(op, close))
    close_change = (close / prev_close - 1.0) * 100.0 if prev_close > 0 else 0.0
    body_ratio = body / rng
    upper_ratio = upper / rng

    big_bear = bool(close < op and body_ratio >= 0.55 and (close - low) / rng <= 0.42)
    long_upper = bool(upper_ratio >= 0.40 and upper >= max(body * 1.35, 1e-9))
    muted = bool(abs(close_change) <= 3.0 and ratio >= 1.50)
    absorption = bool(abnormal and (big_bear or long_upper or muted))

    if not abnormal:
        pattern = "-"
    elif big_bear:
        pattern = "대량 장대음봉"
    elif long_upper:
        pattern = "대량 긴윗꼬리"
    elif muted:
        pattern = "가격대비 대량흡수"
    else:
        pattern = "이상거래량"

    return {
        "abnormal": abnormal,
        "absorption": absorption,
        "ratio": ratio,
        "previous_volume": prev_vol,
        "volume_up_vs_prev": volume_up_vs_prev,
        "p85": p85,
        "p95": p95,
        "big_bear": big_bear,
        "long_upper": long_upper,
        "muted": muted,
        "pattern": pattern,
        "close_change_pct": close_change,
    }


def _record112_recent(vols: List[float], i: int, recent_window: int = 20) -> bool:
    """True when one of the last 20 bars is a 112-bar record-volume bar.

    The record bar must also have higher volume than its immediately previous
    bar, matching the user's volume-color rule.
    """
    start = max(111, i - recent_window + 1)
    for j in range(start, i + 1):
        if j <= 0 or float(vols[j]) <= float(vols[j - 1]):
            continue
        base = vols[j - 111:j + 1]
        if base and float(vols[j]) >= max(float(x) for x in base):
            return True
    return False


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
    """PUMA watermelon approximation v4.

    Important:
      The proprietary Stock Dante watermelon formula is not public.
      This is a transparent approximation built only from observable/public
      concepts: bottom-area context, abnormal volume/absorption, interaction
      with EMA112/224 and Ichimoku cloud, prior accumulation, and arrow confluence.

    Goal:
      Mark only the sparse preparation zone immediately before a Bowl-3 style
      EMA224 breakout setup, using concentrated-capital footprints as evidence.

    Uses only current/past bars. No future-bar confirmation is used.
    """
    n = len(candles)
    stages = [0] * n
    scores = [0] * n
    reasons = [""] * n
    confirmed = [False] * n
    display = [0] * n
    footprint_scores = [0] * n
    footprint_reasons = [""] * n
    pre_bowl3_flags = [False] * n
    if n == 0:
        return {
            "watermelon_stage": stages,
            "watermelon_score": scores,
            "watermelon_reason": reasons,
            "watermelon_confirmed": confirmed,
            "watermelon_display": display,
            "watermelon_footprint_score": footprint_scores,
            "watermelon_footprint_reason": footprint_reasons,
            "watermelon_pre_bowl3": pre_bowl3_flags,
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
    cloud = ichimoku_cloud(candles)
    cloud_a = list(cloud.get("cloud_a") or [])
    cloud_b = list(cloud.get("cloud_b") or [])

    arrow_series = arrow_series or {}
    arrow_keys = ("signal_pink", "signal_blue", "signal_red", "signal_black")
    arrows = [arrow_series.get(k, [False] * n) for k in arrow_keys]
    acc_flags = list(acc_flags or [False] * n)
    if len(acc_flags) < n:
        acc_flags.extend([False] * (n - len(acc_flags)))

    last_display = -10**9
    # 수박은 밥3 직전 준비구간에만 드물게 표시한다.
    min_display_gap = 35

    pre_bowl_prev = False

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

        # Large-money footprint proxy: abnormal volume/absorption plus interaction
        # with structural levels that individual traders cannot directly command
        # as a group. This is evidence of concentrated capital, not actor identity.
        vf = _volume_footprint(candles, vols, v20, i)

        impulse = False
        for j in range(max(20, i - 15), i + 1):
            if (
                j > 0
                and v20[j]
                and vols[j] > vols[j - 1]
                and vols[j] >= float(v20[j]) * 1.50
            ):
                impulse = True
                break

        acc_recent = any(bool(x) for x in acc_flags[max(0, i - 20):i + 1])
        calm = bool(v20[i] and vols[i] <= float(v20[i]) * 1.25)

        # Direct interaction with EMA112/224 and the visible Ichimoku cloud.
        long_touch = False
        long_reclaim = False
        for line in (e112, e224):
            if i < len(line) and line[i] is not None:
                lv = float(line[i])
                if lows[i] <= lv * 1.025 and highs[i] >= lv * 0.975:
                    long_touch = True
                if i > 0 and line[i - 1] is not None:
                    long_reclaim = long_reclaim or bool(
                        closes[i - 1] < float(line[i - 1]) * 0.995
                        and closes[i] >= lv * 0.995
                    )

        ca = cloud_a[i] if i < len(cloud_a) else None
        cb = cloud_b[i] if i < len(cloud_b) else None
        cloud_touch = False
        cloud_reclaim = False
        if isinstance(ca, (int, float)) and isinstance(cb, (int, float)):
            cloud_lo = min(float(ca), float(cb))
            cloud_hi = max(float(ca), float(cb))
            cloud_touch = bool(lows[i] <= cloud_hi * 1.02 and highs[i] >= cloud_lo * 0.98)
            if i > 0:
                pca = cloud_a[i - 1] if i - 1 < len(cloud_a) else None
                pcb = cloud_b[i - 1] if i - 1 < len(cloud_b) else None
                if isinstance(pca, (int, float)) and isinstance(pcb, (int, float)):
                    prev_top = max(float(pca), float(pcb))
                    cloud_reclaim = bool(
                        closes[i - 1] <= prev_top * 1.005
                        and closes[i] > cloud_hi * 1.005
                    )

        structural_touch = bool(long_touch or long_reclaim or cloud_touch or cloud_reclaim)
        big_money_footprint = bool(
            (vf["abnormal"] and structural_touch)
            or (vf["absorption"] and (long_touch or cloud_touch))
            or (acc_recent and structural_touch)
        )

        footprint_score = 0
        footprint_tags = []
        if vf["abnormal"]:
            footprint_score += 30
            footprint_tags.append(f"이상거래량 {vf['ratio']:.2f}배")
        if vf["absorption"]:
            footprint_score += 20
            footprint_tags.append(str(vf["pattern"]))
        if long_touch or long_reclaim:
            footprint_score += 20
            footprint_tags.append("112/224 개입")
        if cloud_touch or cloud_reclaim:
            footprint_score += 20
            footprint_tags.append("구름대 개입")
        if acc_recent:
            footprint_score += 10
            footprint_tags.append("매집반복")
        footprint_score = min(100, footprint_score)
        footprint_scores[i] = footprint_score
        footprint_reasons[i] = " · ".join(footprint_tags) if footprint_tags else "-"

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
        if big_money_footprint:
            score += 20; tags.append(f"대형자금흔적 {footprint_score}")
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
        evidence_confirmed = bool(big_money_footprint or impulse or acc_recent)

        # 밥3 분석기의 '3번 직전' 기준과 맞춘다:
        # 1) EMA224 아래 장기 체류(최근 100봉 중 70봉 이상)
        # 2) 현재가 EMA224 ±2%
        # 3) 최근20봉 안 112봉 신고거래량
        # 4) 60 < 112 < 224 역배열 또는 최근 112EMA 회복
        # 5) 최근 대형자금/매집 흔적
        near_224_prebreak = False
        if e224[i] is not None and float(e224[i]) > 0:
            near_224_prebreak = abs(price / float(e224[i]) - 1.0) <= 0.020

        reverse_60_112_224 = False
        if e60[i] is not None and e112[i] is not None and e224[i] is not None:
            reverse_60_112_224 = bool(
                float(e60[i]) < float(e112[i]) < float(e224[i])
            )

        reclaimed_112_recent = _latest_reclaim_index(closes, e112, i, 60) >= 0
        record112_recent = _record112_recent(vols, i, 20)

        prior_start = max(223, i - 99)
        prior_idx = [
            j for j in range(prior_start, i + 1)
            if 0 <= j < len(e224) and e224[j] is not None
        ]
        below224_count = sum(
            1 for j in prior_idx
            if closes[j] < float(e224[j])
        )
        long_below_224 = bool(len(prior_idx) >= 70 and below224_count >= 70)

        recent_large_money = bool(
            big_money_footprint
            or acc_recent
            or any(int(x) >= 50 for x in footprint_scores[max(0, i - 9):i])
        )

        # 현재 봉이 이미 224를 강한 양봉 몸통으로 돌파했다면 '직전 수박'이 아니다.
        bullish_224_body_break = False
        if i > 0 and e224[i] is not None:
            bullish_224_body_break = bool(
                closes[i] > opens[i]
                and opens[i] <= float(e224[i])
                and closes[i] > float(e224[i]) * 1.003
            )

        pre_bowl3 = bool(
            bottom_context
            and long_below_224
            and near_224_prebreak
            and record112_recent
            and (reverse_60_112_224 or reclaimed_112_recent)
            and recent_large_money
            and not bullish_224_body_break
        )

        pre_bowl3_flags[i] = pre_bowl3

        # 점수는 보조값이고, 실제 표시는 밥3 직전 구조를 통과해야만 허용한다.
        strict = bool(
            pre_bowl3
            and evidence_confirmed
            and score >= 80
        )

        if strict:
            stage = 3
            confirmed[i] = True
            # 같은 준비구간에 여러 개 난사하지 않고, 구간에 처음 진입한 자리만 우선 표시.
            entered_pre_bowl = not pre_bowl_prev
            if entered_pre_bowl and i - last_display >= min_display_gap:
                display[i] = 3
                last_display = i

        pre_bowl_prev = pre_bowl3

        stages[i] = stage
        scores[i] = score
        reasons[i] = " · ".join(tags[:6]) if tags else "조건 미충족"

    return {
        "watermelon_stage": stages,
        "watermelon_score": scores,
        "watermelon_reason": reasons,
        "watermelon_confirmed": confirmed,
        "watermelon_display": display,
        "watermelon_footprint_score": footprint_scores,
        "watermelon_footprint_reason": footprint_reasons,
        "watermelon_pre_bowl3": pre_bowl3_flags,
    }
