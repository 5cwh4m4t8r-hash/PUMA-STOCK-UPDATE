from __future__ import annotations

from statistics import mean
from typing import Any


def _s(settings: Any, name: str, default):
    try:
        value = getattr(settings, name)
        return value
    except Exception:
        return default


def _quantile(values: list[float], q: float) -> float:
    xs = sorted(float(v) for v in values)
    if not xs:
        return 0.0
    if len(xs) == 1:
        return xs[0]
    pos = max(0.0, min(1.0, float(q))) * (len(xs) - 1)
    lo = int(pos)
    hi = min(len(xs) - 1, lo + 1)
    frac = pos - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


def _avg_prior_volume(candles: list[dict], idx: int, period: int = 20) -> float:
    start = max(0, idx - period)
    vals = [float(c["volume"]) for c in candles[start:idx] if float(c["volume"]) > 0]
    return mean(vals) if vals else 0.0


def _evaluate_box(candles: list[dict], start: int, end: int, settings: Any) -> dict | None:
    if end < start:
        return None
    seg = candles[start:end + 1]
    if len(seg) < 10:
        return None

    highs = [float(c["high"]) for c in seg]
    lows = [float(c["low"]) for c in seg]
    closes = [float(c["close"]) for c in seg]

    # Outlier wicks should not define the whole box. Use robust price ridges.
    low = _quantile(lows, 0.15)
    high = _quantile(highs, 0.85)
    if low <= 0 or high <= low:
        return None

    mid = (high + low) / 2.0
    width_pct = (high - low) / mid * 100.0 if mid else 999.0
    max_width = float(_s(settings, "box_width_pct", 25.0))
    if width_pct > max_width:
        return None

    tolerance = float(_s(settings, "box_touch_tolerance_pct", 2.5)) / 100.0
    coverage_min = float(_s(settings, "box_min_coverage", 0.70))
    min_touches = int(_s(settings, "box_min_touches", 3))

    inside = sum(1 for c in closes if low * (1 - tolerance) <= c <= high * (1 + tolerance))
    coverage = inside / len(seg)

    top_touches = sum(
        1 for c in seg
        if float(c["high"]) >= high * (1 - tolerance)
        and float(c["close"]) <= high * (1 + tolerance)
    )
    bottom_touches = sum(
        1 for c in seg
        if float(c["low"]) <= low * (1 + tolerance)
        and float(c["close"]) >= low * (1 - tolerance)
    )

    # A box should be broadly flat, not merely a long directional trend.
    edge_n = min(10, max(3, len(seg) // 8))
    first_mean = mean(closes[:edge_n])
    last_mean = mean(closes[-edge_n:])
    drift_pct = abs(last_mean / first_mean - 1.0) * 100.0 if first_mean else 999.0
    drift_limit = max(5.0, max_width * 0.55)

    if coverage < coverage_min or top_touches < min_touches or bottom_touches < min_touches:
        return None
    if drift_pct > drift_limit:
        return None

    # Prefer high coverage, repeated support/resistance touches and longer boxes.
    score = (
        coverage * 55.0
        + min(15.0, top_touches * 2.5)
        + min(15.0, bottom_touches * 2.5)
        + min(15.0, len(seg) / 112.0 * 15.0)
        - max(0.0, width_pct - max_width * 0.65) * 0.5
    )
    return {
        "start": start,
        "end": end,
        "low": low,
        "high": high,
        "width_pct": width_pct,
        "coverage": coverage,
        "top_touches": top_touches,
        "bottom_touches": bottom_touches,
        "period": len(seg),
        "score": score,
        "structure_type": "공구리",
        "breakout_idx": -1,
        "accepted": False,
    }


def find_box_before(candles: list[dict], end_idx: int, settings: Any = None) -> dict | None:
    min_period = int(_s(settings, "box_period_min", 60))
    max_period = int(_s(settings, "box_period_max", 112))
    min_period = max(20, min(min_period, max_period))
    max_period = max(min_period, max_period)
    if end_idx + 1 < min_period:
        return None

    best = None
    lengths = list(range(min_period, max_period + 1, 4))
    if max_period not in lengths:
        lengths.append(max_period)
    for period in lengths:
        start = end_idx - period + 1
        if start < 0:
            continue
        item = _evaluate_box(candles, start, end_idx, settings)
        if not item:
            continue
        if best is None or item["score"] > best["score"]:
            best = item
    return best


def _fallback_resistance(candles: list[dict], end_idx: int, settings: Any = None) -> dict | None:
    period = min(int(_s(settings, "box_period_max", 112)), end_idx + 1)
    period = max(min(int(_s(settings, "box_period_min", 60)), end_idx + 1), period)
    if period < 20:
        return None
    start = end_idx - period + 1
    seg = candles[start:end_idx + 1]
    highs = [float(c["high"]) for c in seg]
    lows = [float(c["low"]) for c in seg]
    # 90th percentile represents a repeated '전고점 언덕' better than one isolated wick.
    high = _quantile(highs, 0.90)
    low = _quantile(lows, 0.20)
    if high <= low or low <= 0:
        return None
    tolerance = float(_s(settings, "box_touch_tolerance_pct", 2.5)) / 100.0
    touches = sum(1 for c in seg if float(c["high"]) >= high * (1 - tolerance))
    if touches < 2:
        return None
    return {
        "start": start,
        "end": end_idx,
        "low": low,
        "high": high,
        "width_pct": (high-low)/((high+low)/2.0)*100.0,
        "coverage": 0.0,
        "top_touches": touches,
        "bottom_touches": 0,
        "period": period,
        "score": 0.0,
        "structure_type": "전고점언덕",
        "breakout_idx": -1,
        "accepted": False,
    }


def _structure_before(candles: list[dict], end_idx: int, settings: Any = None) -> dict | None:
    return find_box_before(candles, end_idx, settings) or _fallback_resistance(candles, end_idx, settings)


def analyze_market_path(candles: list[dict], settings: Any = None) -> dict:
    """One-path model shared by day/swing/long analysis.

    Core sequence:
      volume expansion >= 300%
      -> prior-high / hill / box-top breakout
      -> pullback with dead volume while breakout level holds
      -> re-breakout with renewed volume.

    The same logic is timeframe-agnostic; named techniques are context tags.
    """
    n = len(candles)
    breakout_flags = [False] * n
    pullback_flags = [False] * n
    rebreak_flags = [False] * n

    default_current = {
        "active": False,
        "stage": "대기",
        "name": "수급→돌파→눌림→재돌파",
        "reason": "유효 돌파 구조 미확인",
        "breakout_idx": -1,
        "box_high": 0.0,
        "box_low": 0.0,
        "breakout_volume_ratio": 0.0,
        "pullback_volume_ratio": 1.0,
        "rebreak_volume_ratio": 0.0,
        "support_hold": False,
        "structure_type": "-",
    }
    if n < max(25, int(_s(settings, "box_period_min", 60)) + 1):
        return {
            "current": default_current,
            "box": None,
            "path_breakout": breakout_flags,
            "path_pullback": pullback_flags,
            "path_rebreakout": rebreak_flags,
        }

    breakout_ratio_req = float(_s(settings, "breakout_volume_ratio", 3.0))
    rebreak_ratio_req = float(_s(settings, "rebreak_volume_ratio", 3.0))
    breakout_buffer = float(_s(settings, "breakout_buffer_pct", 0.2)) / 100.0
    pullback_vol_max = float(_s(settings, "pullback_volume_max_ratio", 0.55))
    support_tol = float(_s(settings, "pullback_support_tolerance_pct", 3.0)) / 100.0
    max_after = int(_s(settings, "path_max_pullback_bars", 12))

    events: list[dict] = []
    min_period = int(_s(settings, "box_period_min", 60))

    for i in range(min_period, n):
        avg_vol = _avg_prior_volume(candles, i, 20)
        if avg_vol <= 0:
            continue
        vol_ratio = float(candles[i]["volume"]) / avg_vol
        if vol_ratio < breakout_ratio_req:
            continue

        structure = _structure_before(candles, i - 1, settings)
        if not structure:
            continue
        level = float(structure["high"])
        c = candles[i]
        close = float(c["close"])
        rng = max(float(c["high"]) - float(c["low"]), 1e-9)
        close_pos = (close - float(c["low"])) / rng

        if close <= level * (1.0 + breakout_buffer):
            continue
        if close_pos < 0.60:
            continue

        breakout_flags[i] = True
        item = dict(structure)
        item.update({
            "breakout_idx": i,
            "breakout_volume_ratio": vol_ratio,
            "breakout_volume": float(c["volume"]),
            "accepted": True,
        })
        events.append(item)

    if not events:
        # A valid box may have ended several bars ago while price is testing
        # or drifting above it without the required 300% volume. Keep the most
        # recent valid 60~112-bar box visible instead of losing the structure.
        current_box = None
        latest_box_end = n - 1
        scan_back = min(50, max(0, n - min_period))
        for back in range(scan_back + 1):
            end_idx = n - 1 - back
            candidate = find_box_before(candles, end_idx, settings)
            if candidate:
                current_box = candidate
                latest_box_end = end_idx
                break

        current = dict(default_current)
        if current_box:
            level = float(current_box["high"])
            avg_now = _avg_prior_volume(candles, n - 1, 20)
            now_vr = float(candles[-1]["volume"]) / avg_now if avg_now else 0.0
            price_above = float(candles[-1]["close"]) > level * (1.0 + breakout_buffer)
            stage = "가격 돌파 / 거래량 미달" if price_above else "박스 상단 돌파 대기"
            reason = (
                f"공구리 {current_box['period']}봉 · "
                f"{current_box['low']:,.0f}~{current_box['high']:,.0f} · "
                f"현재 거래량 {now_vr:.2f}배 / 필요 {breakout_ratio_req:.2f}배"
            )
            current.update({
                "stage": stage,
                "reason": reason,
                "box_high": current_box["high"],
                "box_low": current_box["low"],
                "structure_type": current_box["structure_type"],
            })
        return {
            "current": current,
            "box": current_box,
            "path_breakout": breakout_flags,
            "path_pullback": pullback_flags,
            "path_rebreakout": rebreak_flags,
        }

    # Derive pullback/re-breakout flags from every breakout event.
    for event in events:
        bi = int(event["breakout_idx"])
        level = float(event["high"])
        breakout_vol = float(event["breakout_volume"])
        last_j = min(n - 1, bi + max_after)
        for j in range(bi + 1, last_j + 1):
            segment = candles[bi + 1:j + 1]
            prior_segment = candles[bi + 1:j]
            current = candles[j]
            closes = [float(c["close"]) for c in segment]
            lows = [float(c["low"]) for c in segment]

            support_hold = min(closes) >= level * (1.0 - support_tol)
            pullback_seen = (
                min(lows) <= level * (1.0 + support_tol)
                or (
                    prior_segment
                    and (max(float(c["high"]) for c in candles[bi:j]) - float(current["close"]))
                    / max(float(c["high"]) for c in candles[bi:j]) >= 0.03
                )
            )
            recent_vols = [float(c["volume"]) for c in segment[-3:]]
            calm_ratio = (mean(recent_vols) / breakout_vol) if breakout_vol else 1.0
            volume_calm = calm_ratio <= pullback_vol_max

            if support_hold and pullback_seen and volume_calm:
                pullback_flags[j] = True

            if j >= bi + 2 and pullback_seen and support_hold:
                prior_high = max(float(c["high"]) for c in candles[bi:j])
                avg_vol = _avg_prior_volume(candles, j, 20)
                vr = float(current["volume"]) / avg_vol if avg_vol else 0.0
                if float(current["close"]) > prior_high * (1.0 + breakout_buffer) and vr >= rebreak_ratio_req:
                    rebreak_flags[j] = True

    event = events[-1]
    bi = int(event["breakout_idx"])
    bars_after = n - 1 - bi
    level = float(event["high"])
    breakout_vol = float(event["breakout_volume"])
    current_c = candles[-1]
    current_close = float(current_c["close"])
    avg_now = _avg_prior_volume(candles, n - 1, 20)
    current_vr = float(current_c["volume"]) / avg_now if avg_now else 0.0

    support_hold = True
    calm_ratio = 1.0
    if bars_after > 0:
        seg = candles[bi + 1:]
        closes = [float(c["close"]) for c in seg]
        support_hold = min(closes) >= level * (1.0 - support_tol)
        recent_vols = [float(c["volume"]) for c in seg[-3:]]
        calm_ratio = mean(recent_vols) / breakout_vol if breakout_vol else 1.0

    stage = "돌파 후 관찰"
    active = False
    reason = (
        f"{event['structure_type']} 상단 {level:,.0f} 돌파 · "
        f"거래량 {event['breakout_volume_ratio']:.2f}배"
    )

    if rebreak_flags[-1]:
        stage = "거래량 동반 재돌파"
        active = True
        reason += f" · 눌림 후 재돌파 거래량 {current_vr:.2f}배"
    elif pullback_flags[-1]:
        stage = "돌파 후 거래량 감소 눌림"
        active = True
        reason += f" · 눌림 거래량/돌파봉 {calm_ratio:.2f} · 상단 지지"
    elif breakout_flags[-1]:
        stage = "거래량 동반 상향돌파"
        active = True
    elif not support_hold:
        stage = "돌파 실패/박스 복귀"
        active = False
        reason += " · 박스 상단 지지 이탈"
    elif bars_after <= 2 and current_close >= level:
        stage = "돌파 상단 유지"
        active = False
        reason += " · 눌림/재돌파 확인 대기"

    current = {
        "active": active,
        "stage": stage,
        "name": "수급→돌파→눌림→재돌파",
        "reason": reason,
        "breakout_idx": bi,
        "box_high": level,
        "box_low": float(event["low"]),
        "breakout_volume_ratio": float(event["breakout_volume_ratio"]),
        "pullback_volume_ratio": calm_ratio,
        "rebreak_volume_ratio": current_vr if rebreak_flags[-1] else 0.0,
        "support_hold": support_hold,
        "structure_type": event["structure_type"],
    }

    event["accepted"] = support_hold
    return {
        "current": current,
        "box": event,
        "path_breakout": breakout_flags,
        "path_pullback": pullback_flags,
        "path_rebreakout": rebreak_flags,
    }
