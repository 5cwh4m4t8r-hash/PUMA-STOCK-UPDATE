from __future__ import annotations

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
    den = sum((i - xbar) ** 2 for i in range(n))
    if den <= 0 or ybar == 0:
        return 999.0
    slope = sum((i - xbar) * (float(v) - ybar) for i, v in enumerate(values)) / den
    return abs(slope) * (n - 1) / abs(ybar) * 100.0


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
    if n < 10:
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
    max_width = float(_s(settings, "box_width_pct", 30.0))
    if width_pct > max_width:
        return None

    tol = float(_s(settings, "box_touch_tolerance_pct", 2.5))/100.0
    coverage_req = float(_s(settings, "box_min_coverage", 0.68))
    touch_req = int(_s(settings, "box_min_touches", 2))
    alt_req = int(_s(settings, "box_min_alternations", 2))
    max_drift = float(_s(settings, "box_max_drift_pct", 7.5))

    coverage = sum(1 for c in closes if low*(1-tol) <= c <= high*(1+tol)) / n
    top_idx = _spaced_touch_indices(seg, high, tol, "top")
    bottom_idx = _spaced_touch_indices(seg, low, tol, "bottom")
    alts = _alternations(top_idx, bottom_idx)
    drift = _linear_drift_pct(closes)

    if coverage < coverage_req:
        return None
    if len(top_idx) < touch_req or len(bottom_idx) < touch_req:
        return None
    if alts < alt_req:
        return None
    if drift > max_drift:
        return None

    score = (
        coverage*36
        + min(18, len(top_idx)*4)
        + min(18, len(bottom_idx)*4)
        + min(16, alts*4)
        + max(0, 12-drift)
        + min(8, n/12)
    )

    return {
        "start":start, "end":end,
        "low":low, "high":high,
        "width_pct":width_pct,
        "coverage":coverage,
        "top_touches":len(top_idx),
        "bottom_touches":len(bottom_idx),
        "alternations":alts,
        "drift_pct":drift,
        "period":n,
        "score":score,
        "structure_type":"공구리",
        "breakout_idx":-1,
        "accepted":False,
    }


def find_box_before(candles: list[dict], end_idx: int, settings: Any=None) -> dict | None:
    if end_idx < 9:
        return None
    lookback = max(30, min(400, int(_s(settings, "box_search_lookback", 160))))
    earliest = max(0, end_idx-lookback+1)

    best = None
    for end_lag in range(0, 4):
        e = end_idx-end_lag
        available = e-earliest+1
        for length in range(10, available+1, 2):
            start = e-length+1
            item = _evaluate_box(candles, start, e, settings)
            if not item:
                continue
            item["recency_lag"] = end_lag
            item["score"] -= end_lag*1.5
            if best is None or item["score"] > best["score"]+2:
                best = item
            elif best and abs(item["score"]-best["score"]) <= 2 and item["period"] > best["period"]:
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


def _confirm_breakout(candles: list[dict], i: int, structure: dict, settings: Any):
    if i <= 0:
        return False, {}
    level = float(structure["high"])
    c = candles[i]
    prev = candles[i-1]
    strength, vs_prev, vs_avg = _volume_strength(candles, i)
    req = float(_s(settings, "breakout_volume_ratio", 3.0))
    buffer = float(_s(settings, "breakout_buffer_pct", 0.15))/100.0

    rng = max(float(c["high"])-float(c["low"]), 1e-9)
    body = float(c["close"])-float(c["open"])
    body_ratio = body/rng
    close_pos = (float(c["close"])-float(c["low"]))/rng

    first_cross = float(prev["close"]) <= level*(1+buffer)
    price_break = float(c["close"]) > level*(1+buffer)

    # Box breakout should be visible when the box really breaks. Do not demand
    # an oversized candle on top of the volume+price confirmation.
    body_req = 0.15 if structure.get("structure_type") == "공구리" else 0.22
    candle_ok = body > 0 and body_ratio >= body_req and close_pos >= 0.55

    info = {
        "strength":strength, "vs_prev":vs_prev, "vs_avg":vs_avg,
        "body_ratio":body_ratio, "close_pos":close_pos,
    }
    return bool(first_cross and price_break and strength >= req and candle_ok), info


def _quality_breakout(structure: dict, info: dict) -> int:
    box_q = min(30, max(10, float(structure.get("score", 0))*0.30)) if structure.get("structure_type") == "공구리" else 12
    vol_q = min(35, 20 + max(0, float(info.get("strength", 0))-3.0)*7)
    close_q = min(20, max(0, (float(info.get("close_pos", 0))-0.50)*40))
    body_q = min(15, max(0, float(info.get("body_ratio", 0))*30))
    return int(min(100, box_q+vol_q+close_q+body_q))


def analyze_market_path(candles: list[dict], settings: Any=None) -> dict:
    n = len(candles)
    breakout_flags=[False]*n
    pullback_flags=[False]*n
    rebreak_flags=[False]*n

    default={
        "active":False, "stage":"대기", "stage_key":"WAIT",
        "name":"수급→돌파→눌림→재돌파",
        "reason":"확정 구조 대기",
        "breakout_idx":-1, "pullback_idx":-1, "rebreak_idx":-1,
        "box_high":0.0, "box_low":0.0,
        "breakout_volume_ratio":0.0,
        "breakout_vs_prev":0.0,
        "breakout_vs_avg":0.0,
        "pullback_volume_ratio":1.0,
        "pullback_base_volume_ratio":1.0,
        "rebreak_volume_ratio":0.0,
        "rebreak_vs_prev":0.0,
        "rebreak_vs_avg":0.0,
        "support_hold":False,
        "structure_type":"-",
        "quality_score":0,
    }
    if n < 30:
        return {"current":default,"box":None,"path_breakout":breakout_flags,"path_pullback":pullback_flags,"path_rebreakout":rebreak_flags}

    breakout_req=float(_s(settings,"breakout_volume_ratio",3.0))
    rebreak_req=float(_s(settings,"rebreak_volume_ratio",3.0))
    pull_vs_break=float(_s(settings,"pullback_volume_max_ratio",0.60))
    pull_vs_base=float(_s(settings,"pullback_base_volume_max_ratio",1.00))
    support_tol=float(_s(settings,"pullback_support_tolerance_pct",3.0))/100.0
    buffer=float(_s(settings,"breakout_buffer_pct",0.15))/100.0
    max_after=int(_s(settings,"path_max_pullback_bars",12))
    duplicate_bars=int(_s(settings,"path_duplicate_suppress_bars",8))

    events=[]
    recent_levels=[]

    for i in range(15,n):
        structure=_structure_before(candles,i-1,settings)
        if not structure:
            continue
        ok,info=_confirm_breakout(candles,i,structure,settings)
        if not ok:
            continue

        level=float(structure["high"])
        duplicate=any(
            i-pi <= duplicate_bars and abs(level/plevel-1.0) <= 0.025
            for pi,plevel in recent_levels if plevel>0
        )
        if duplicate:
            continue

        q=_quality_breakout(structure,info)
        item=dict(structure)
        item.update({
            "breakout_idx":i,
            "breakout_volume_ratio":info["strength"],
            "breakout_vs_prev":info["vs_prev"],
            "breakout_vs_avg":info["vs_avg"],
            "breakout_volume":float(candles[i]["volume"]),
            "breakout_quality":q,
            "pullback_idx":-1,
            "rebreak_idx":-1,
            "accepted":True,
        })
        breakout_flags[i]=True
        events.append(item)
        recent_levels.append((i,level))

    for event in events:
        bi=int(event["breakout_idx"])
        level=float(event["high"])
        bvol=float(event["breakout_volume"])
        last_j=min(n-1,bi+max_after)

        pull_idx=-1
        for j in range(bi+1,last_j+1):
            seg=candles[bi+1:j+1]
            closes=[float(c["close"]) for c in seg]
            if min(closes) < level*(1-support_tol):
                break

            peak=max(float(c["high"]) for c in candles[bi:j+1])
            current=candles[j]
            current_close=float(current["close"])
            retrace=(peak-current_close)/peak*100 if peak else 0.0
            near_level=float(current["low"]) <= level*1.04
            actual_pull=near_level or retrace >= 2.0

            # One or two low-volume bars are enough to confirm the contraction.
            recent=seg[-2:]
            avg_recent=mean(float(c["volume"]) for c in recent)
            current_ratio=float(current["volume"])/bvol if bvol else 1.0
            two_ratio=avg_recent/bvol if bvol else 1.0
            base=_avg_prior_volume(candles,j,20)
            current_base=float(current["volume"])/base if base else 1.0
            two_base=avg_recent/base if base else 1.0

            volume_dead=(
                (current_ratio <= pull_vs_break and current_base <= pull_vs_base)
                or
                (len(recent)>=2 and two_ratio <= min(0.70,pull_vs_break+0.10) and two_base <= pull_vs_base)
            )

            if actual_pull and volume_dead:
                pull_idx=j
                pullback_flags[j]=True
                event["pullback_idx"]=j
                event["pullback_volume_ratio"]=min(current_ratio,two_ratio)
                event["pullback_base_volume_ratio"]=min(current_base,two_base)
                event["pullback_retrace_pct"]=retrace
                event["pullback_quality"]=int(min(
                    100,
                    45
                    + max(0, (pull_vs_break-min(current_ratio,two_ratio))*55)
                    + max(0, (pull_vs_base-min(current_base,two_base))*25)
                    + min(20, retrace*2)
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
            if (
                float(c["close"]) > prior_high*(1+buffer)
                and strength >= rebreak_req
                and body > 0
                and close_pos >= 0.55
            ):
                event["rebreak_idx"]=j
                event["rebreak_volume_ratio"]=strength
                event["rebreak_vs_prev"]=vs_prev
                event["rebreak_vs_avg"]=vs_avg
                event["rebreak_quality"]=int(min(
                    100,
                    50 + min(35,max(0,strength-3.0)*10+20) + min(15,close_pos*15)
                ))
                rebreak_flags[j]=True
                break

    if not events:
        box=find_box_before(candles,n-1,settings)
        cur=dict(default)
        if box:
            cur.update({
                "stage":"공구리 형성 / 돌파 대기",
                "reason":(
                    f"횡보 {box['period']}봉 · 지지 {box['low']:,.0f} / 저항 {box['high']:,.0f} · "
                    f"상단 {box['top_touches']}회·하단 {box['bottom_touches']}회·왕복 {box['alternations']}회"
                ),
                "box_high":box["high"],"box_low":box["low"],
                "structure_type":box["structure_type"],
                "quality_score":int(min(100,box.get("score",0))),
            })
        return {"current":cur,"box":box,"path_breakout":breakout_flags,"path_pullback":pullback_flags,"path_rebreakout":rebreak_flags}

    event=events[-1]
    bi=int(event["breakout_idx"])
    pi=int(event.get("pullback_idx",-1))
    ri=int(event.get("rebreak_idx",-1))
    level=float(event["high"])
    support_hold=(
        min(float(c["close"]) for c in candles[bi+1:]) >= level*(1-support_tol)
        if bi<n-1 else True
    )

    cur=dict(default)
    cur.update({
        "breakout_idx":bi,"pullback_idx":pi,"rebreak_idx":ri,
        "box_high":level,"box_low":float(event["low"]),
        "breakout_volume_ratio":float(event.get("breakout_volume_ratio",0)),
        "breakout_vs_prev":float(event.get("breakout_vs_prev",0)),
        "breakout_vs_avg":float(event.get("breakout_vs_avg",0)),
        "pullback_volume_ratio":float(event.get("pullback_volume_ratio",1)),
        "pullback_base_volume_ratio":float(event.get("pullback_base_volume_ratio",1)),
        "rebreak_volume_ratio":float(event.get("rebreak_volume_ratio",0)),
        "rebreak_vs_prev":float(event.get("rebreak_vs_prev",0)),
        "rebreak_vs_avg":float(event.get("rebreak_vs_avg",0)),
        "support_hold":support_hold,
        "structure_type":event["structure_type"],
    })

    if not support_hold:
        cur.update({"stage":"돌파 실패 / 박스 복귀","stage_key":"FAIL","active":False,"reason":f"저항 {level:,.0f} 돌파 후 지지 실패","quality_score":20})
    elif ri>=0 and n-1-ri<=2:
        cur.update({
            "stage":"확정 재돌파","stage_key":"REBREAKOUT","active":True,
            "reason":(
                f"돌파→저거래량 눌림→재돌파 · 거래량강도 {event.get('rebreak_volume_ratio',0):.2f}배 "
                f"(전봉 {event.get('rebreak_vs_prev',0):.2f} / 20평균 {event.get('rebreak_vs_avg',0):.2f})"
            ),
            "quality_score":int(event.get("rebreak_quality",80)),
        })
    elif pi>=0 and ri<0 and n-1-pi<=4:
        cur.update({
            "stage":"확정 눌림","stage_key":"PULLBACK","active":True,
            "reason":(
                f"돌파선 {level:,.0f} 지지 · 눌림거래량/돌파봉 {event.get('pullback_volume_ratio',1):.2f} · "
                f"20봉평균대비 {event.get('pullback_base_volume_ratio',1):.2f}"
            ),
            "quality_score":int(event.get("pullback_quality",70)),
        })
    elif n-1-bi<=2 and pi<0:
        cur.update({
            "stage":"확정 돌파","stage_key":"BREAKOUT","active":True,
            "reason":(
                f"{event['structure_type']} 저항 {level:,.0f} 돌파 · 거래량강도 {event.get('breakout_volume_ratio',0):.2f}배 "
                f"(전봉 {event.get('breakout_vs_prev',0):.2f} / 20평균 {event.get('breakout_vs_avg',0):.2f})"
            ),
            "quality_score":int(event.get("breakout_quality",70)),
        })
    elif pi<0:
        cur.update({
            "stage":"돌파 후 눌림 대기","stage_key":"WAIT","active":False,
            "reason":(
                f"돌파 확인 · 이제 거래량이 돌파봉의 {pull_vs_break*100:.0f}% 이하로 줄고 "
                f"저항 {level:,.0f} 부근을 지키는 눌림 확인"
            ),
            "quality_score":int(event.get("breakout_quality",60)),
        })
    elif ri<0:
        cur.update({
            "stage":"눌림 확인 / 재상승 대기","stage_key":"PULLBACK","active":True,
            "reason":(
                f"저거래량 눌림 확인 · 돌파선 지지 · 재상승 또는 거래량 {rebreak_req:.1f}배 재돌파 대기"
            ),
            "quality_score":int(event.get("pullback_quality",70)),
        })
    else:
        cur.update({"stage":"과거 구조","stage_key":"WAIT","active":False,"reason":"현재 신규 타점과 거리 있음","quality_score":0})

    event["accepted"]=support_hold
    return {"current":cur,"box":event,"path_breakout":breakout_flags,"path_pullback":pullback_flags,"path_rebreakout":rebreak_flags}
