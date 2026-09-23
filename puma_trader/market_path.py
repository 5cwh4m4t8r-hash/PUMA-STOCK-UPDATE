from __future__ import annotations

from statistics import fmean as mean
from .performance import check_cancelled
from typing import Any


def _s(settings: Any, name: str, default):
    try:
        return getattr(settings, name)
    except Exception:
        return default


# Heavy box detection is shared by SWING/LONG/UI enrichment.
# Cache exact candle/settings signatures so the same chart is not analyzed
# three or four times during one screen refresh.
_PATH_CACHE: dict[tuple, dict] = {}
_PATH_CACHE_ORDER: list[tuple] = []
_PATH_CACHE_MAX = 32


def clear_market_path_cache():
    _PATH_CACHE.clear()
    _PATH_CACHE_ORDER.clear()


def _settings_key(settings: Any) -> tuple:
    names = (
        "box_search_lookback", "box_width_pct", "box_min_coverage",
        "box_min_touches", "box_min_alternations", "box_touch_tolerance_pct",
        "box_max_drift_pct", "box_max_directionality",
        "breakout_volume_ratio", "pullback_volume_max_ratio",
        "pullback_base_volume_max_ratio", "pullback_support_tolerance_pct",
        "pullback_ma_touch_tolerance_pct", "long_ma_break_buffer_pct",
        "bottom_drawdown_pct", "bottom_lookback", "bottom_exclude_recent",
        "bowl_below_lookback", "bowl_min_below_closes",
        "rebreak_volume_ratio", "path_max_pullback_bars",
        "path_duplicate_suppress_bars", "breakout_buffer_pct",
    )
    return tuple((name, _s(settings, name, None)) for name in names)


def _candles_key(candles: list[dict]) -> tuple:
    # O(n) cheap fingerprint. The old algorithm was far more expensive because
    # it sorted/scanned hundreds of candidate boxes for every candle.
    h = 1469598103934665603
    mask = (1 << 64) - 1
    for c in candles:
        item = (
            str(c.get("date", "")),
            round(float(c.get("open", 0) or 0), 4),
            round(float(c.get("high", 0) or 0), 4),
            round(float(c.get("low", 0) or 0), 4),
            round(float(c.get("close", 0) or 0), 4),
            int(float(c.get("volume", 0) or 0)),
        )
        h ^= hash(item) & mask
        h = (h * 1099511628211) & mask
    return (len(candles), h)


def _path_cache_get(key: tuple):
    return _PATH_CACHE.get(key)


def _path_cache_put(key: tuple, value: dict):
    if key in _PATH_CACHE:
        return
    _PATH_CACHE[key] = value
    _PATH_CACHE_ORDER.append(key)
    while len(_PATH_CACHE_ORDER) > _PATH_CACHE_MAX:
        old = _PATH_CACHE_ORDER.pop(0)
        _PATH_CACHE.pop(old, None)



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
    vals = [
        float(c["volume"]) for c in candles[max(0, idx-period):idx]
        if float(c["volume"]) > 0
    ]
    return mean(vals) if vals else 0.0


def _volume_strength(candles: list[dict], idx: int) -> tuple[float, float, float]:
    """Return (strength, vs_prev, vs_20avg).

    Public Danta material repeatedly explains breakout volume around 300% vs
    the previous day, while PUMA also keeps the 20-bar average reference.
    Strength is the stronger of the two references, but both are shown.
    """
    if idx <= 0:
        return 0.0, 0.0, 0.0
    vol = float(candles[idx]["volume"])
    prev = float(candles[idx-1]["volume"])
    avg = _avg_prior_volume(candles, idx, 20)
    vs_prev = vol / prev if prev > 0 else 0.0
    vs_avg = vol / avg if avg > 0 else 0.0
    return max(vs_prev, vs_avg), vs_prev, vs_avg


def _linear_drift_pct(values: list[float]) -> float:
    n = len(values)
    if n < 3:
        return 999.0
    xbar = (n - 1) / 2.0
    ybar = mean(values)
    den = n * (n * n - 1) / 12.0
    if den <= 0 or ybar == 0:
        return 999.0
    slope = sum((i - xbar) * (float(v) - ybar) for i, v in enumerate(values)) / den
    return abs(slope) * (n - 1) / abs(ybar) * 100.0


def _directionality(values: list[float]) -> float:
    """1.0 is near one-way trend; low values mean back-and-forth sideways travel."""
    if len(values) < 3:
        return 1.0
    travel = sum(abs(float(values[i]) - float(values[i-1])) for i in range(1, len(values)))
    if travel <= 0:
        return 0.0
    return abs(float(values[-1]) - float(values[0])) / travel


def _ema_series(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    seed = sum(float(x) for x in values[:period]) / period
    out[period - 1] = seed
    k = 2.0 / (period + 1.0)
    prev = seed
    for i in range(period, len(values)):
        prev = float(values[i]) * k + prev * (1.0 - k)
        out[i] = prev
    return out


def _crossed_long_mas(candles: list[dict], i: int, e112, e224, settings: Any) -> list[int]:
    if i <= 0:
        return []
    close = float(candles[i]["close"])
    prev_close = float(candles[i - 1]["close"])
    buf = float(_s(settings, "long_ma_break_buffer_pct", 0.15)) / 100.0
    crossed = []
    for period, line in ((112, e112), (224, e224)):
        if i >= len(line) or line[i] is None or line[i - 1] is None:
            continue
        if prev_close <= float(line[i - 1]) and close > float(line[i]) * (1.0 + buf):
            crossed.append(period)
    return crossed


def _bottom_context(candles: list[dict], i: int, e112, e224, settings: Any) -> tuple[bool, dict]:
    close = float(candles[i]["close"])
    lookback = max(80, int(_s(settings, "bottom_lookback", 240)))
    exclude_recent = max(10, int(_s(settings, "bottom_exclude_recent", 20)))
    hist_start = max(0, i - lookback)
    hist_end = max(hist_start + 1, i - exclude_recent)
    older = candles[hist_start:hist_end]
    anchor_high = max((float(c["high"]) for c in older), default=close)
    drawdown = (anchor_high - close) / anchor_high * 100.0 if anchor_high > 0 else 0.0
    drawdown_req = float(_s(settings, "bottom_drawdown_pct", 10.0))

    dists = []
    for line in (e112, e224):
        if i < len(line) and line[i] is not None and float(line[i]) > 0:
            dists.append(abs(close / float(line[i]) - 1.0) * 100.0)
    near_long = bool(dists and min(dists) <= 10.0)

    reverse_long = bool(
        i < len(e112) and i < len(e224)
        and e112[i] is not None and e224[i] is not None
        and float(e112[i]) <= float(e224[i]) * 1.02
    )
    active = bool(near_long and (drawdown >= drawdown_req or reverse_long))
    return active, {
        "drawdown_pct": drawdown,
        "near_long": near_long,
        "reverse_long": reverse_long,
    }


def _bowl3_context(candles: list[dict], i: int, e224, settings: Any) -> tuple[bool, dict]:
    lookback = max(40, int(_s(settings, "bowl_below_lookback", 100)))
    min_below = max(20, int(_s(settings, "bowl_min_below_closes", 70)))
    start = max(0, i - lookback)
    valid = [j for j in range(start, i) if j < len(e224) and e224[j] is not None]
    below = sum(1 for j in valid if float(candles[j]["close"]) < float(e224[j]))
    active = bool(len(valid) >= min_below and below >= min_below)
    return active, {"below_count": below, "valid_count": len(valid)}


def _spaced_touch_indices(seg: list[dict], level: float, tol: float, side: str) -> list[int]:
    raw = []
    for i, c in enumerate(seg):
        hit = (
            float(c["high"]) >= level * (1 - tol)
            if side == "top"
            else float(c["low"]) <= level * (1 + tol)
        )
        if hit:
            raw.append(i)

    out = []
    for i in raw:
        if not out or i - out[-1] >= 3:
            out.append(i)
    return out


def _alternations(top_idx: list[int], bottom_idx: list[int]) -> int:
    events = sorted([(i, "T") for i in top_idx] + [(i, "B") for i in bottom_idx])
    compressed = []
    for item in events:
        if not compressed or compressed[-1][1] != item[1]:
            compressed.append(item)
    return max(0, len(compressed) - 1)


def _evaluate_box(candles: list[dict], start: int, end: int, settings: Any) -> dict | None:
    seg = candles[start:end+1]
    n = len(seg)
    if n < 12:
        return None

    highs = [float(c["high"]) for c in seg]
    lows = [float(c["low"]) for c in seg]
    closes = [float(c["close"]) for c in seg]

    low = _quantile(lows, 0.18)
    high = _quantile(highs, 0.82)
    if low <= 0 or high <= low:
        return None

    mid = (high + low) / 2.0
    width_pct = (high-low)/mid*100.0 if mid else 999.0
    if width_pct > float(_s(settings, "box_width_pct", 30.0)):
        return None

    tol = float(_s(settings, "box_touch_tolerance_pct", 2.0))/100.0
    coverage_req = float(_s(settings, "box_min_coverage", 0.68))
    touch_req = int(_s(settings, "box_min_touches", 3))
    alt_req = int(_s(settings, "box_min_alternations", 3))
    max_drift = float(_s(settings, "box_max_drift_pct", 5.0))
    max_directionality = float(_s(settings, "box_max_directionality", 0.50))

    coverage = sum(1 for c in closes if low*(1-tol) <= c <= high*(1+tol)) / n
    top_idx = _spaced_touch_indices(seg, high, tol, "top")
    bottom_idx = _spaced_touch_indices(seg, low, tol, "bottom")
    alts = _alternations(top_idx, bottom_idx)
    if coverage < coverage_req or len(top_idx) < touch_req or len(bottom_idx) < touch_req or alts < alt_req:
        return None

    boundary = sorted(top_idx + bottom_idx)
    first_touch = boundary[0]
    last_touch = boundary[-1]
    if last_touch - first_touch + 1 < 12:
        return None

    trimmed_closes = closes[first_touch:last_touch+1]
    trimmed_coverage = sum(
        1 for c in trimmed_closes
        if low*(1-tol) <= c <= high*(1+tol)
    ) / len(trimmed_closes)
    drift = _linear_drift_pct(trimmed_closes)
    directionality = _directionality(trimmed_closes)
    if trimmed_coverage < coverage_req or drift > max_drift or directionality > max_directionality:
        return None

    period = last_touch-first_touch+1
    score = (
        trimmed_coverage*36
        + min(18, len(top_idx)*4)
        + min(18, len(bottom_idx)*4)
        + min(16, alts*4)
        + max(0, 14-drift*1.5)
        + min(8, period/12)
        + max(0, (0.55-directionality)*18)
    )

    return {
        "start":start+first_touch, "end":start+last_touch,
        "low":low, "high":high,
        "width_pct":width_pct,
        "coverage":trimmed_coverage,
        "top_touches":len(top_idx),
        "bottom_touches":len(bottom_idx),
        "alternations":alts,
        "drift_pct":drift,
        "directionality":directionality,
        "period":period,
        "score":score,
        "structure_type":"공구리",
        "breakout_idx":-1,
        "accepted":False,
    }

def find_box_before(candles: list[dict], end_idx: int, settings: Any=None) -> dict | None:
    """Fast adaptive box finder.

    v2.4 evaluated virtually every even length for four end lags.
    v2.6 does a coarse scan, then refines around the best few candidates.
    The horizontal support/resistance tests themselves are unchanged.
    """
    if end_idx < 9:
        return None
    lookback = max(30, min(400, int(_s(settings, "box_search_lookback", 160))))
    earliest = max(0, end_idx-lookback+1)

    evaluated = {}

    def evaluate(start, end, lag):
        check_cancelled()
        key = (start, end)
        if key not in evaluated:
            item = _evaluate_box(candles, start, end, settings)
            if item:
                item["recency_lag"] = lag
                item["score"] -= lag * 1.5
            evaluated[key] = item
        return evaluated[key]

    coarse_valid = []
    for end_lag in range(0, 3):
        e = end_idx-end_lag
        available = e-earliest+1
        if available < 10:
            continue

        # About 15-25 candidates instead of ~75 per end-lag.
        step = 8 if available >= 80 else 6 if available >= 50 else 4
        lengths = list(range(12, available+1, step))
        if available not in lengths:
            lengths.append(available)

        for length in lengths:
            start = e-length+1
            item = evaluate(start, e, end_lag)
            if not item:
                continue
            coarse_valid.append(item)

    if not coarse_valid:
        return None

    coarse_valid.sort(key=lambda x: (float(x.get("score", 0)), int(x.get("period", 0))), reverse=True)
    seeds = coarse_valid[:3]
    best = seeds[0]

    # Refine only near the strongest coarse periods.
    seen = set()
    for seed in seeds:
        seed_len = int(seed["period"])
        for end_lag in range(max(0, int(seed.get("recency_lag", 0))-1), min(2, int(seed.get("recency_lag", 0))+1)+1):
            e = end_idx-end_lag
            available = e-earliest+1
            lo = max(12, seed_len-8)
            hi = min(available, seed_len+8)
            for length in range(lo, hi+1, 2):
                key = (end_lag, length)
                if key in seen:
                    continue
                seen.add(key)
                start = e-length+1
                item = evaluate(start, e, end_lag)
                if not item:
                    continue
                if item["score"] > best["score"]+2:
                    best = item
                elif abs(item["score"]-best["score"]) <= 2 and item["period"] > best["period"]:
                    best = item
    return best


def _fallback_hill(candles: list[dict], end_idx: int, settings: Any=None) -> dict | None:
    lookback = max(30, min(400, int(_s(settings, "box_search_lookback", 160))))
    start = max(0, end_idx-lookback+1)
    seg = candles[start:end_idx+1]
    if len(seg) < 18:
        return None

    high = _quantile([float(c["high"]) for c in seg], 0.90)
    low = _quantile([float(c["low"]) for c in seg], 0.20)
    if low <= 0 or high <= low:
        return None

    tol = float(_s(settings, "box_touch_tolerance_pct", 2.5))/100.0
    top_idx = _spaced_touch_indices(seg, high, tol, "top")
    if len(top_idx) < 2:
        return None

    return {
        "start":start, "end":end_idx,
        "low":low, "high":high,
        "width_pct":(high-low)/((high+low)/2)*100.0,
        "coverage":0.0,
        "top_touches":len(top_idx),
        "bottom_touches":0,
        "alternations":0,
        "drift_pct":_linear_drift_pct([float(c["close"]) for c in seg]),
        "period":len(seg),
        "score":0.0,
        "structure_type":"전고점언덕",
        "breakout_idx":-1,
        "accepted":False,
    }


def _structure_before(candles: list[dict], end_idx: int, settings: Any=None) -> dict | None:
    return find_box_before(candles, end_idx, settings) or _fallback_hill(candles, end_idx, settings)


def _confirm_breakout(candles: list[dict], i: int, structure: dict, settings: Any, e112, e224):
    if i <= 0:
        return False, {}

    crossed = _crossed_long_mas(candles, i, e112, e224, settings)
    if not crossed:
        return False, {}

    bottom_ok, bottom_info = _bottom_context(candles, i, e112, e224, settings)
    bowl_ok, bowl_info = _bowl3_context(candles, i, e224, settings)
    if not (bottom_ok or bowl_ok):
        return False, {}

    level = float(structure["high"])
    c = candles[i]
    prev = candles[i-1]
    buffer = float(_s(settings, "breakout_buffer_pct", 0.15))/100.0
    first_cross = float(prev["close"]) <= level*(1+buffer)
    structure_break = float(c["close"]) > level*(1+buffer)

    rng = max(float(c["high"])-float(c["low"]), 1e-9)
    body = float(c["close"])-float(c["open"])
    body_ratio = body/rng
    close_pos = (float(c["close"])-float(c["low"]))/rng
    candle_ok = body > 0 and body_ratio >= 0.15 and close_pos >= 0.55

    strength, vs_prev, vs_avg = _volume_strength(candles, i)
    ma_period = 224 if 224 in crossed else 112
    ma_line = e224 if ma_period == 224 else e112
    ma_value = float(ma_line[i]) if ma_line[i] is not None else 0.0

    context_name = "밥그릇3" if bowl_ok else "바닥권"
    info = {
        "strength":strength, "vs_prev":vs_prev, "vs_avg":vs_avg,
        "body_ratio":body_ratio, "close_pos":close_pos,
        "crossed_mas":crossed, "breakout_ma_period":ma_period,
        "breakout_ma_value":ma_value,
        "bottom_context":bottom_ok, "bowl3_context":bowl_ok,
        "context_name":context_name,
        "bottom_drawdown_pct":float(bottom_info.get("drawdown_pct",0)),
        "bowl_below_count":int(bowl_info.get("below_count",0)),
    }
    return bool(first_cross and structure_break and candle_ok), info


def _quality_breakout(structure: dict, info: dict) -> int:
    structure_q = min(30, max(12, float(structure.get("score", 0))*0.30)) if structure.get("structure_type") == "공구리" else 15
    context_q = 25 if info.get("bowl3_context") else 20
    ma_q = 25
    candle_q = min(15, max(0, float(info.get("close_pos", 0))*15))
    vol_strength = float(info.get("strength", 0))
    volume_q = min(15, max(0, vol_strength-1.0)*6)
    return int(min(100, structure_q+context_q+ma_q+candle_q+volume_q))

def _analyze_market_path_uncached(candles: list[dict], settings: Any=None) -> dict:
    n = len(candles)
    breakout_flags=[False]*n
    pullback_flags=[False]*n
    rebreak_flags=[False]*n
    breakout_ma=[0]*n
    pullback_ma=[0]*n

    default={
        "active":False, "stage":"대기", "stage_key":"WAIT",
        "name":"바닥/밥그릇3→112·224+구조돌파→저거래량 눌림→재돌파",
        "reason":"확정 공구리/전고점과 장기이평 돌파 대기",
        "breakout_idx":-1, "pullback_idx":-1, "rebreak_idx":-1,
        "breakout_ma_period":0, "pullback_ma_period":0,
        "box_high":0.0, "box_low":0.0,
        "breakout_volume_ratio":0.0, "breakout_vs_prev":0.0, "breakout_vs_avg":0.0,
        "pullback_volume_ratio":1.0, "pullback_base_volume_ratio":1.0,
        "rebreak_volume_ratio":0.0, "rebreak_vs_prev":0.0, "rebreak_vs_avg":0.0,
        "support_hold":False, "structure_type":"-", "context_name":"-", "quality_score":0,
    }
    if n < 30:
        return {"current":default,"box":None,"path_breakout":breakout_flags,"path_pullback":pullback_flags,
                "path_rebreakout":rebreak_flags,"path_breakout_ma":breakout_ma,"path_pullback_ma":pullback_ma}

    closes=[float(c["close"]) for c in candles]
    e112=_ema_series(closes,112)
    e224=_ema_series(closes,224)

    rebreak_req=float(_s(settings,"rebreak_volume_ratio",3.0))
    pull_vs_break=float(_s(settings,"pullback_volume_max_ratio",0.60))
    pull_vs_base=float(_s(settings,"pullback_base_volume_max_ratio",1.00))
    touch_tol=float(_s(settings,"pullback_ma_touch_tolerance_pct",2.0))/100.0
    hold_tol=float(_s(settings,"pullback_support_tolerance_pct",3.0))/100.0
    buffer=float(_s(settings,"breakout_buffer_pct",0.15))/100.0
    max_after=int(_s(settings,"path_max_pullback_bars",12))
    duplicate_bars=int(_s(settings,"path_duplicate_suppress_bars",8))

    events=[]
    recent_levels=[]
    structure_cache: dict[int, dict | None] = {}

    def structure_at(end_idx: int):
        if end_idx not in structure_cache:
            structure_cache[end_idx] = _structure_before(candles, end_idx, settings)
        return structure_cache[end_idx]

    for i in range(1,n):
        if i % 32 == 0:
            check_cancelled()
        crossed=_crossed_long_mas(candles,i,e112,e224,settings)
        if not crossed:
            continue
        bottom_ok,_=_bottom_context(candles,i,e112,e224,settings)
        bowl_ok,_=_bowl3_context(candles,i,e224,settings)
        if not (bottom_ok or bowl_ok):
            continue

        structure=structure_at(i-1)
        if not structure:
            continue
        ok,info=_confirm_breakout(candles,i,structure,settings,e112,e224)
        if not ok:
            continue

        level=float(structure["high"])
        duplicate=any(
            (i-pi <= max_after) or (i-pi <= duplicate_bars and abs(level/plevel-1.0) <= 0.025)
            for pi,plevel in recent_levels if plevel>0
        )
        if duplicate:
            continue

        q=_quality_breakout(structure,info)
        item=dict(structure)
        item.update({
            "breakout_idx":i,
            "breakout_ma_period":int(info["breakout_ma_period"]),
            "breakout_ma_value":float(info["breakout_ma_value"]),
            "context_name":str(info["context_name"]),
            "bottom_context":bool(info["bottom_context"]),
            "bowl3_context":bool(info["bowl3_context"]),
            "breakout_volume_ratio":info["strength"],
            "breakout_vs_prev":info["vs_prev"], "breakout_vs_avg":info["vs_avg"],
            "breakout_volume":float(candles[i]["volume"]),
            "breakout_quality":q, "pullback_idx":-1, "pullback_ma_period":0,
            "rebreak_idx":-1, "accepted":True,
        })
        breakout_flags[i]=True
        breakout_ma[i]=int(info["breakout_ma_period"])
        events.append(item)
        recent_levels.append((i,level))

    for event in events:
        bi=int(event["breakout_idx"])
        bvol=float(event["breakout_volume"])
        last_j=min(n-1,bi+max_after)
        preferred=int(event.get("breakout_ma_period",0))
        periods=[preferred]+[p for p in (224,112) if p!=preferred]

        pull_idx=-1
        for j in range(bi+1,last_j+1):
            current=candles[j]
            if float(current["close"]) >= float(current["open"]):
                continue

            chosen_period=0
            chosen_level=0.0
            for period in periods:
                line=e224 if period==224 else e112
                if j>=len(line) or line[j] is None:
                    continue
                ma=float(line[j])
                low=float(current["low"])
                close=float(current["close"])
                touched=low <= ma*(1+touch_tol)
                held=close >= ma*(1-hold_tol)
                close_near=close <= ma*(1+max(touch_tol,0.035))
                if touched and held and close_near:
                    chosen_period=period
                    chosen_level=ma
                    break
            if not chosen_period:
                continue

            base=_avg_prior_volume(candles,j,20)
            current_vol=float(current["volume"])
            current_ratio=current_vol/bvol if bvol else 1.0
            current_base=current_vol/base if base else 1.0
            volume_dead=bool(current_ratio <= pull_vs_break and current_base <= pull_vs_base)
            if not volume_dead:
                continue

            pull_idx=j
            pullback_flags[j]=True
            pullback_ma[j]=chosen_period
            event["pullback_idx"]=j
            event["pullback_ma_period"]=chosen_period
            event["pullback_ma_value"]=chosen_level
            event["pullback_volume_ratio"]=current_ratio
            event["pullback_base_volume_ratio"]=current_base
            event["pullback_quality"]=int(min(
                100, 55 + max(0,(pull_vs_break-current_ratio))*55 + max(0,(pull_vs_base-current_base))*25
            ))
            break

        if pull_idx < 0:
            continue

        for j in range(pull_idx+1,last_j+1):
            prior_high=max(float(c["high"]) for c in candles[bi:j])
            c=candles[j]
            strength,vs_prev,vs_avg=_volume_strength(candles,j)
            rng=max(float(c["high"])-float(c["low"]),1e-9)
            body=float(c["close"])-float(c["open"])
            close_pos=(float(c["close"])-float(c["low"]))/rng
            if float(c["close"]) > prior_high*(1+buffer) and strength >= rebreak_req and body > 0 and close_pos >= 0.55:
                event["rebreak_idx"]=j
                event["rebreak_volume_ratio"]=strength
                event["rebreak_vs_prev"]=vs_prev
                event["rebreak_vs_avg"]=vs_avg
                event["rebreak_quality"]=int(min(100,50+min(35,max(0,strength-3.0)*10+20)+min(15,close_pos*15)))
                rebreak_flags[j]=True
                break

    if not events:
        box=find_box_before(candles,n-1,settings)
        cur=dict(default)
        if box:
            cur.update({
                "stage":"공구리 형성 / 112·224 동반 돌파 대기",
                "reason":f"횡보 {box['period']}봉 · 지지 {box['low']:,.0f} / 저항 {box['high']:,.0f} · 상단 {box['top_touches']}회·하단 {box['bottom_touches']}회·왕복 {box['alternations']}회",
                "box_high":box["high"],"box_low":box["low"],"structure_type":box["structure_type"],
                "quality_score":int(min(100,box.get("score",0))),
            })
        return {"current":cur,"box":box,"path_breakout":breakout_flags,"path_pullback":pullback_flags,
                "path_rebreakout":rebreak_flags,"path_breakout_ma":breakout_ma,"path_pullback_ma":pullback_ma}

    event=events[-1]
    bi=int(event["breakout_idx"]); pi=int(event.get("pullback_idx",-1)); ri=int(event.get("rebreak_idx",-1))
    level=float(event["high"])
    support_period=int(event.get("pullback_ma_period") or event.get("breakout_ma_period") or 0)
    support_line=e224 if support_period==224 else e112
    support_hold=bool(support_period and support_line[-1] is not None and float(candles[-1]["close"]) >= float(support_line[-1])*(1-hold_tol))

    cur=dict(default)
    cur.update({
        "breakout_idx":bi,"pullback_idx":pi,"rebreak_idx":ri,
        "breakout_ma_period":int(event.get("breakout_ma_period",0)),
        "pullback_ma_period":int(event.get("pullback_ma_period",0)),
        "box_high":level,"box_low":float(event["low"]),
        "breakout_volume_ratio":float(event.get("breakout_volume_ratio",0)),
        "breakout_vs_prev":float(event.get("breakout_vs_prev",0)),
        "breakout_vs_avg":float(event.get("breakout_vs_avg",0)),
        "pullback_volume_ratio":float(event.get("pullback_volume_ratio",1)),
        "pullback_base_volume_ratio":float(event.get("pullback_base_volume_ratio",1)),
        "rebreak_volume_ratio":float(event.get("rebreak_volume_ratio",0)),
        "rebreak_vs_prev":float(event.get("rebreak_vs_prev",0)),
        "rebreak_vs_avg":float(event.get("rebreak_vs_avg",0)),
        "support_hold":support_hold,"structure_type":event["structure_type"],
        "context_name":str(event.get("context_name","-")),
    })

    ma=int(event.get("breakout_ma_period",0))
    structure_name="공구리 상단" if event.get("structure_type")=="공구리" else "전고점"
    if pi>=0 and not support_hold:
        cur.update({"stage":f"{ma}EMA 눌림 지지 실패","stage_key":"FAIL","active":False,
                    "reason":f"돌파 후 {support_period}EMA 눌림에서 종가 지지 실패","quality_score":20})
    elif ri>=0 and n-1-ri<=2:
        cur.update({"stage":"확정 재돌파","stage_key":"REBREAKOUT","active":True,
                    "reason":f"{event.get('context_name')} · {ma}EMA+{structure_name} 돌파 → {event.get('pullback_ma_period')}EMA 저거래량 음봉 눌림 → 재돌파",
                    "quality_score":int(event.get("rebreak_quality",80))})
    elif pi>=0 and ri<0 and n-1-pi<=4:
        cur.update({"stage":"확정 눌림","stage_key":"PULLBACK","active":True,
                    "reason":f"{event.get('context_name')} 돌파 후 음봉이 {event.get('pullback_ma_period')}EMA까지 눌림 · 거래량/돌파봉 {event.get('pullback_volume_ratio',1):.2f} · 20봉평균대비 {event.get('pullback_base_volume_ratio',1):.2f}",
                    "quality_score":int(event.get("pullback_quality",75))})
    elif n-1-bi<=2 and pi<0:
        cur.update({"stage":"확정 돌파","stage_key":"BREAKOUT","active":True,
                    "reason":f"{event.get('context_name')} · {ma}EMA 상향돌파와 동시에 {structure_name} {level:,.0f} 돌파",
                    "quality_score":int(event.get("breakout_quality",75))})
    elif pi<0:
        cur.update({"stage":"돌파 후 112·224 눌림 대기","stage_key":"WAIT","active":False,
                    "reason":f"{event.get('context_name')} · {ma}EMA+{structure_name} 돌파 확인 · 이후 음봉이 112/224EMA까지 내려오며 거래량이 죽는지 대기",
                    "quality_score":int(event.get("breakout_quality",65))})
    elif ri<0:
        cur.update({"stage":"확정 눌림 / 재상승 대기","stage_key":"PULLBACK","active":True,
                    "reason":f"{event.get('pullback_ma_period')}EMA 저거래량 음봉 눌림 확인 · 재상승 대기",
                    "quality_score":int(event.get("pullback_quality",75))})
    else:
        cur.update({"stage":"과거 구조","stage_key":"WAIT","active":False,"reason":"현재 신규 타점과 거리 있음","quality_score":0})

    event["accepted"]=support_hold
    return {"current":cur,"box":event,"path_breakout":breakout_flags,"path_pullback":pullback_flags,
            "path_rebreakout":rebreak_flags,"path_breakout_ma":breakout_ma,"path_pullback_ma":pullback_ma}

def analyze_market_path(candles: list[dict], settings: Any=None) -> dict:
    if not candles:
        return _analyze_market_path_uncached(candles, settings)

    key = (_candles_key(candles), _settings_key(settings))
    cached = _path_cache_get(key)
    if cached is not None:
        return cached

    result = _analyze_market_path_uncached(candles, settings)
    _path_cache_put(key, result)
    return result
