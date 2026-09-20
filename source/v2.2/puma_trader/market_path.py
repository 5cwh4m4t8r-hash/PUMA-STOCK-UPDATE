from __future__ import annotations

from math import sqrt
from statistics import mean
from typing import Any


def _s(settings: Any, name: str, default):
    try:
        return getattr(settings, name)
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


def _linear_drift_pct(values: list[float]) -> float:
    n = len(values)
    if n < 3:
        return 999.0
    xbar = (n - 1) / 2.0
    ybar = mean(values)
    den = sum((i - xbar) ** 2 for i in range(n))
    if den <= 0 or ybar == 0:
        return 999.0
    slope = sum((i - xbar) * (float(v) - ybar) for i, v in enumerate(values)) / den
    return abs(slope) * (n - 1) / abs(ybar) * 100.0


def _spaced_touch_indices(seg: list[dict], level: float, tol: float, side: str) -> list[int]:
    raw = []
    for i, c in enumerate(seg):
        if side == "top":
            hit = float(c["high"]) >= level * (1 - tol)
        else:
            hit = float(c["low"]) <= level * (1 + tol)
        if hit:
            raw.append(i)

    # 여러 인접 봉이 같은 저항/지지를 만진 것은 한 번의 테스트로 본다.
    out = []
    for i in raw:
        if not out or i - out[-1] >= 3:
            out.append(i)
    return out


def _alternations(top_idx: list[int], bottom_idx: list[int]) -> int:
    events = [(i, "T") for i in top_idx] + [(i, "B") for i in bottom_idx]
    events.sort()
    if not events:
        return 0
    compressed = []
    for item in events:
        if not compressed or compressed[-1][1] != item[1]:
            compressed.append(item)
    return max(0, len(compressed) - 1)


def _evaluate_box(candles: list[dict], start: int, end: int, settings: Any) -> dict | None:
    seg = candles[start:end + 1]
    n = len(seg)
    # 기간 자체를 고정하지 않는다. 다만 지지/저항을 논할 최소 표본은 필요하다.
    if n < 12:
        return None

    highs = [float(c["high"]) for c in seg]
    lows = [float(c["low"]) for c in seg]
    closes = [float(c["close"]) for c in seg]

    # 한두 개 긴 꼬리가 박스 상하단을 왜곡하지 않도록 반복 가격대를 사용한다.
    low = _quantile(lows, 0.18)
    high = _quantile(highs, 0.82)
    if low <= 0 or high <= low:
        return None

    mid = (high + low) / 2.0
    width_pct = (high - low) / mid * 100.0 if mid else 999.0
    max_width = float(_s(settings, "box_width_pct", 30.0))
    if width_pct > max_width:
        return None

    tol = float(_s(settings, "box_touch_tolerance_pct", 2.5)) / 100.0
    coverage_req = float(_s(settings, "box_min_coverage", 0.72))
    touches_req = int(_s(settings, "box_min_touches", 3))
    alt_req = int(_s(settings, "box_min_alternations", 2))
    max_drift = float(_s(settings, "box_max_drift_pct", 6.0))

    inside = sum(1 for c in closes if low * (1 - tol) <= c <= high * (1 + tol))
    coverage = inside / n

    top_idx = _spaced_touch_indices(seg, high, tol, "top")
    bottom_idx = _spaced_touch_indices(seg, low, tol, "bottom")
    alternations = _alternations(top_idx, bottom_idx)
    drift_pct = _linear_drift_pct(closes)

    if coverage < coverage_req:
        return None
    if len(top_idx) < touches_req or len(bottom_idx) < touches_req:
        return None
    if alternations < alt_req:
        return None
    if drift_pct > max_drift:
        return None

    # 짧더라도 명확한 횡보면 인정하고, 길더라도 추세면 탈락한다.
    # 기간은 보조점수만 주고 지지/저항 반복과 평탄성을 우선한다.
    score = (
        coverage * 38.0
        + min(18.0, len(top_idx) * 3.0)
        + min(18.0, len(bottom_idx) * 3.0)
        + min(16.0, alternations * 4.0)
        + max(0.0, 10.0 - drift_pct)
        + min(6.0, n / 20.0)
        - max(0.0, width_pct - max_width * 0.70) * 0.35
    )

    return {
        "start": start,
        "end": end,
        "low": low,
        "high": high,
        "width_pct": width_pct,
        "coverage": coverage,
        "top_touches": len(top_idx),
        "bottom_touches": len(bottom_idx),
        "alternations": alternations,
        "drift_pct": drift_pct,
        "period": n,
        "score": score,
        "structure_type": "공구리",
        "breakout_idx": -1,
        "accepted": False,
    }


def find_box_before(candles: list[dict], end_idx: int, settings: Any = None) -> dict | None:
    """Find the actual horizontal support/resistance segment.

    box_search_lookback is only a search range. It is NOT the box duration.
    Candidate duration is determined by the chart itself.
    """
    if end_idx < 11:
        return None

    lookback = int(_s(settings, "box_search_lookback", 160))
    lookback = max(30, min(400, lookback))
    earliest = max(0, end_idx - lookback + 1)

    best = None
    # Box may finish 0~3 bars before the evaluation point.
    for end_lag in range(0, 4):
        e = end_idx - end_lag
        if e < 11:
            continue
        available = e - earliest + 1
        for length in range(12, available + 1, 2):
            start = e - length + 1
            item = _evaluate_box(candles, start, e, settings)
            if not item:
                continue
            item["recency_lag"] = end_lag
            item["score"] -= end_lag * 2.0
            if best is None:
                best = item
                continue
            # If quality is essentially tied, prefer the longer support/resistance history.
            if item["score"] > best["score"] + 2.5:
                best = item
            elif abs(item["score"] - best["score"]) <= 2.5 and item["period"] > best["period"]:
                best = item
    return best


def _fallback_hill(candles: list[dict], end_idx: int, settings: Any = None) -> dict | None:
    lookback = int(_s(settings, "box_search_lookback", 160))
    start = max(0, end_idx - lookback + 1)
    seg = candles[start:end_idx + 1]
    if len(seg) < 20:
        return None

    highs = [float(c["high"]) for c in seg]
    lows = [float(c["low"]) for c in seg]
    high = _quantile(highs, 0.90)
    low = _quantile(lows, 0.20)
    if high <= low or low <= 0:
        return None

    tol = float(_s(settings, "box_touch_tolerance_pct", 2.5)) / 100.0
    top_idx = _spaced_touch_indices(seg, high, tol, "top")
    if len(top_idx) < 2:
        return None

    return {
        "start": start,
        "end": end_idx,
        "low": low,
        "high": high,
        "width_pct": (high - low) / ((high + low) / 2.0) * 100.0,
        "coverage": 0.0,
        "top_touches": len(top_idx),
        "bottom_touches": 0,
        "alternations": 0,
        "drift_pct": _linear_drift_pct([float(c["close"]) for c in seg]),
        "period": len(seg),
        "score": 0.0,
        "structure_type": "전고점언덕",
        "breakout_idx": -1,
        "accepted": False,
    }


def _structure_before(candles: list[dict], end_idx: int, settings: Any = None) -> dict | None:
    return find_box_before(candles, end_idx, settings) or _fallback_hill(candles, end_idx, settings)


def _confirm_breakout(candles: list[dict], i: int, structure: dict, settings: Any) -> tuple[bool, float]:
    if i <= 0:
        return False, 0.0
    level = float(structure["high"])
    c = candles[i]
    prev = candles[i - 1]
    avg_vol = _avg_prior_volume(candles, i, 20)
    if avg_vol <= 0:
        return False, 0.0

    vr = float(c["volume"]) / avg_vol
    req = float(_s(settings, "breakout_volume_ratio", 3.0))
    buffer = float(_s(settings, "breakout_buffer_pct", 0.3)) / 100.0

    rng = max(float(c["high"]) - float(c["low"]), 1e-9)
    body = float(c["close"]) - float(c["open"])
    body_ratio = body / rng
    close_pos = (float(c["close"]) - float(c["low"])) / rng

    first_cross = float(prev["close"]) <= level * (1 + buffer)
    price_break = float(c["close"]) > level * (1 + buffer)
    candle_quality = body > 0 and body_ratio >= 0.35 and close_pos >= 0.70

    return bool(first_cross and price_break and vr >= req and candle_quality), vr


def analyze_market_path(candles: list[dict], settings: Any = None) -> dict:
    """Strict unified path.

    supply/volume expansion -> confirmed resistance breakout
    -> confirmed low-volume pullback holding breakout level
    -> confirmed high-volume re-breakout

    Flags are event markers, not continuous labels, so the chart stays sparse.
    """
    n = len(candles)
    breakout_flags = [False] * n
    pullback_flags = [False] * n
    rebreak_flags = [False] * n

    default_current = {
        "active": False,
        "stage": "대기",
        "stage_key": "WAIT",
        "name": "수급→돌파→눌림→재돌파",
        "reason": "확정 구조 대기",
        "breakout_idx": -1,
        "pullback_idx": -1,
        "rebreak_idx": -1,
        "box_high": 0.0,
        "box_low": 0.0,
        "breakout_volume_ratio": 0.0,
        "pullback_volume_ratio": 1.0,
        "pullback_base_volume_ratio": 1.0,
        "rebreak_volume_ratio": 0.0,
        "support_hold": False,
        "structure_type": "-",
    }
    if n < 35:
        return {
            "current": default_current,
            "box": None,
            "path_breakout": breakout_flags,
            "path_pullback": pullback_flags,
            "path_rebreakout": rebreak_flags,
        }

    breakout_req = float(_s(settings, "breakout_volume_ratio", 3.0))
    rebreak_req = float(_s(settings, "rebreak_volume_ratio", 3.0))
    pullback_vs_breakout_max = float(_s(settings, "pullback_volume_max_ratio", 0.45))
    pullback_vs_base_max = float(_s(settings, "pullback_base_volume_max_ratio", 0.85))
    support_tol = float(_s(settings, "pullback_support_tolerance_pct", 2.5)) / 100.0
    buffer = float(_s(settings, "breakout_buffer_pct", 0.3)) / 100.0
    max_after = int(_s(settings, "path_max_pullback_bars", 12))
    confirm_bars = max(2, int(_s(settings, "pullback_confirm_bars", 2)))

    events = []
    recent_levels: list[tuple[int, float]] = []

    # Confirm only the first real breakout of a given resistance zone.
    for i in range(20, n):
        avg_vol = _avg_prior_volume(candles, i, 20)
        if avg_vol <= 0 or float(candles[i]["volume"]) / avg_vol < breakout_req:
            continue

        structure = _structure_before(candles, i - 1, settings)
        if not structure:
            continue

        ok, vr = _confirm_breakout(candles, i, structure, settings)
        if not ok:
            continue

        level = float(structure["high"])
        duplicate = any(i - pi <= 20 and abs(level / plevel - 1.0) <= 0.03 for pi, plevel in recent_levels if plevel > 0)
        if duplicate:
            continue

        item = dict(structure)
        item.update({
            "breakout_idx": i,
            "breakout_volume_ratio": vr,
            "breakout_volume": float(candles[i]["volume"]),
            "pullback_idx": -1,
            "rebreak_idx": -1,
            "accepted": True,
        })
        breakout_flags[i] = True
        events.append(item)
        recent_levels.append((i, level))

    # Confirm exactly one pullback and one re-breakout per breakout event.
    for event in events:
        bi = int(event["breakout_idx"])
        level = float(event["high"])
        breakout_vol = float(event["breakout_volume"])
        last_j = min(n - 1, bi + max_after)

        pull_idx = -1
        for j in range(bi + confirm_bars, last_j + 1):
            seg = candles[bi + 1:j + 1]
            closes = [float(c["close"]) for c in seg]
            support_hold = min(closes) >= level * (1 - support_tol)
            if not support_hold:
                break

            peak = max(float(c["high"]) for c in candles[bi:j + 1])
            recent = seg[-confirm_bars:]
            recent_low = min(float(c["low"]) for c in recent)
            current_close = float(candles[j]["close"])
            retrace_pct = (peak - current_close) / peak * 100.0 if peak else 0.0
            touch_or_retrace = recent_low <= level * (1 + support_tol) or retrace_pct >= 4.0

            avg_recent = mean(float(c["volume"]) for c in recent)
            calm_vs_breakout = avg_recent / breakout_vol if breakout_vol else 1.0
            base_vol = _avg_prior_volume(candles, j, 20)
            calm_vs_base = avg_recent / base_vol if base_vol else 1.0

            volume_dead = (
                calm_vs_breakout <= pullback_vs_breakout_max
                and calm_vs_base <= pullback_vs_base_max
            )

            if touch_or_retrace and volume_dead:
                pull_idx = j
                pullback_flags[j] = True
                event["pullback_idx"] = j
                event["pullback_volume_ratio"] = calm_vs_breakout
                event["pullback_base_volume_ratio"] = calm_vs_base
                break

        if pull_idx < 0:
            continue

        # Re-breakout must happen AFTER a confirmed pullback, with renewed >=300% volume.
        for j in range(pull_idx + 1, last_j + 1):
            prior_high = max(float(c["high"]) for c in candles[bi:j])
            c = candles[j]
            avg_vol = _avg_prior_volume(candles, j, 20)
            vr = float(c["volume"]) / avg_vol if avg_vol else 0.0
            rng = max(float(c["high"]) - float(c["low"]), 1e-9)
            body = float(c["close"]) - float(c["open"])
            close_pos = (float(c["close"]) - float(c["low"])) / rng
            if (
                float(c["close"]) > prior_high * (1 + buffer)
                and vr >= rebreak_req
                and body > 0
                and close_pos >= 0.65
            ):
                event["rebreak_idx"] = j
                event["rebreak_volume_ratio"] = vr
                rebreak_flags[j] = True
                break

    # If no event exists, keep only the strongest current support/resistance box on screen.
    if not events:
        current_box = find_box_before(candles, n - 1, settings)
        current = dict(default_current)
        if current_box:
            current.update({
                "stage": "공구리 형성 / 돌파 대기",
                "stage_key": "WAIT",
                "reason": (
                    f"횡보 {current_box['period']}봉 · "
                    f"지지 {current_box['low']:,.0f} / 저항 {current_box['high']:,.0f} · "
                    f"상단 {current_box['top_touches']}회·하단 {current_box['bottom_touches']}회"
                ),
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

    event = events[-1]
    bi = int(event["breakout_idx"])
    pi = int(event.get("pullback_idx", -1))
    ri = int(event.get("rebreak_idx", -1))
    level = float(event["high"])
    support_hold = min(float(c["close"]) for c in candles[bi + 1:]) >= level * (1 - support_tol) if bi < n - 1 else True

    current = dict(default_current)
    current.update({
        "breakout_idx": bi,
        "pullback_idx": pi,
        "rebreak_idx": ri,
        "box_high": level,
        "box_low": float(event["low"]),
        "breakout_volume_ratio": float(event.get("breakout_volume_ratio", 0.0)),
        "pullback_volume_ratio": float(event.get("pullback_volume_ratio", 1.0)),
        "pullback_base_volume_ratio": float(event.get("pullback_base_volume_ratio", 1.0)),
        "rebreak_volume_ratio": float(event.get("rebreak_volume_ratio", 0.0)),
        "support_hold": support_hold,
        "structure_type": event["structure_type"],
    })

    if not support_hold:
        current.update({
            "stage": "돌파 실패 / 박스 복귀",
            "stage_key": "FAIL",
            "active": False,
            "reason": f"저항 {level:,.0f} 돌파 후 지지 실패",
        })
    elif ri >= 0 and n - 1 - ri <= 1:
        current.update({
            "stage": "확정 재돌파",
            "stage_key": "REBREAKOUT",
            "active": True,
            "reason": (
                f"돌파→저거래량 눌림 완료 · 재돌파 거래량 "
                f"{float(event.get('rebreak_volume_ratio',0)):.2f}배"
            ),
        })
    elif pi >= 0 and ri < 0 and n - 1 - pi <= 3:
        current.update({
            "stage": "확정 눌림",
            "stage_key": "PULLBACK",
            "active": True,
            "reason": (
                f"저항 {level:,.0f} 지지 · 눌림거래량/돌파봉 "
                f"{float(event.get('pullback_volume_ratio',1)):.2f} · "
                f"평균거래량대비 {float(event.get('pullback_base_volume_ratio',1)):.2f}"
            ),
        })
    elif bi == n - 1:
        current.update({
            "stage": "확정 돌파",
            "stage_key": "BREAKOUT",
            "active": True,
            "reason": (
                f"{event['structure_type']} 저항 {level:,.0f} 상향돌파 · "
                f"거래량 {float(event.get('breakout_volume_ratio',0)):.2f}배"
            ),
        })
    elif pi < 0:
        current.update({
            "stage": "돌파 후 눌림 확인 대기",
            "stage_key": "WAIT",
            "active": False,
            "reason": (
                f"돌파는 확정 · 눌림은 미확정 · "
                f"거래량이 돌파봉의 {pullback_vs_breakout_max*100:.0f}% 이하로 죽고 "
                f"저항 {level:,.0f}을 지켜야 함"
            ),
        })
    elif ri < 0:
        current.update({
            "stage": "확정 눌림 이후 재돌파 대기",
            "stage_key": "WAIT",
            "active": False,
            "reason": f"눌림 완료 · 재돌파 시 거래량 {rebreak_req:.1f}배 이상 필요",
        })
    else:
        current.update({
            "stage": "구조 진행",
            "stage_key": "WAIT",
            "active": False,
            "reason": "과거 확정 구조 · 현재 신규 타점 아님",
        })

    event["accepted"] = support_hold
    return {
        "current": current,
        "box": event,
        "path_breakout": breakout_flags,
        "path_pullback": pullback_flags,
        "path_rebreakout": rebreak_flags,
    }
