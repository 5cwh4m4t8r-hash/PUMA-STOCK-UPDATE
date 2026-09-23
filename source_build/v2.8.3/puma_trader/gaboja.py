from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import sqrt
from statistics import mean
from typing import Dict, List

from .swing import normalize_candles


@dataclass
class GabojaSignal:
    passed: bool
    entry_kind: str = ""
    reason: str = ""
    current_price: float = 0.0
    basis_open: float = 0.0
    young1_high: float = 0.0
    pullback_low: float = 0.0
    day_volume_ratio: float = 0.0
    details: Dict[str, object] = field(default_factory=dict)


def _date_key(raw) -> str:
    return "".join(ch for ch in str(raw or "") if ch.isdigit())[:8]


def _hm(raw) -> str:
    s = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(s) >= 12:
        return s[8:10] + ":" + s[10:12]
    return ""


def _eavg(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    alpha = 2.0 / (float(period) + 1.0)
    out = [float(values[0])]
    for value in values[1:]:
        out.append(float(value) * alpha + out[-1] * (1.0 - alpha))
    return out


def _bb_upper(values: List[float], period: int = 40, dev: float = 2.2) -> List[float | None]:
    out: List[float | None] = [None] * len(values)
    if period <= 1:
        return out
    for i in range(period - 1, len(values)):
        xs = [float(x) for x in values[i - period + 1:i + 1]]
        m = sum(xs) / period
        sd = sqrt(sum((x - m) ** 2 for x in xs) / period)
        out[i] = m + float(dev) * sd
    return out


def _candidate_filter(
    daily_rows: List[dict],
    live_bar: dict | None = None,
    *,
    session_bars: int = 1,
    min_score: int = 3,
) -> tuple[bool, dict]:
    """PUMA 2차 후보 선별.

    영웅문 검색기가 1차 후보를 공급한 뒤 PUMA가 장중 힘을 재검증한다.
    갭과 전일 하루 거래량 300%는 더 이상 필수조건이 아니다.

    점수(4개 중 3개 이상):
      1) 현재가가 시가 이상
      2) 장중 거래량/거래대금 진행속도가 전일 평균 진행속도 대비 강함
      3) 전일고 또는 최근 5일 고점을 공격 중
      4) EMA112/224/448 또는 BB40/2.2 저항을 당일 공격/돌파
    """
    daily = normalize_candles(daily_rows or [])
    if live_bar:
        live_day = _date_key(live_bar.get("date"))
        if daily and _date_key(daily[-1].get("date")) == live_day:
            daily[-1] = dict(live_bar)
        elif not daily or _date_key(daily[-1].get("date")) < live_day:
            daily.append(dict(live_bar))
    if len(daily) < 6:
        return False, {"reason": "일봉 6봉 미만", "puma_score": 0}

    cur = daily[-1]
    prev = daily[-2]
    prev5 = daily[-6:-1]
    cur_open = float(cur["open"])
    cur_high = float(cur["high"])
    cur_close = float(cur["close"])
    cur_volume = float(cur["volume"])

    prev_high = float(prev["high"])
    prev5_high = max(float(x["high"]) for x in prev5)
    gap_ok = cur_open > prev5_high

    prev_vol = float(prev["volume"])
    day_volume_ratio = cur_volume / prev_vol if prev_vol > 0 else 0.0

    # 장중 누적 거래량을 '전일 하루 전체'와 직접 비교하지 않고,
    # 현재까지 경과한 5분봉 비율로 환산하여 진행속도를 비교한다.
    bars = max(1, int(session_bars or 1))
    elapsed_fraction = min(1.0, max(5.0 / 390.0, (bars * 5.0) / 390.0))
    expected_vol = prev_vol * elapsed_fraction
    volume_pace = cur_volume / expected_vol if expected_vol > 0 else 0.0

    prev_turnover = max(0.0, float(prev["close"]) * prev_vol)
    cur_turnover = max(0.0, cur_close * cur_volume)
    expected_turnover = prev_turnover * elapsed_fraction
    turnover_pace = cur_turnover / expected_turnover if expected_turnover > 0 else 0.0
    flow_pace = max(volume_pace, turnover_pace)
    flow_ok = flow_pace >= 1.30

    price_strength = cur_close >= cur_open

    # '돌파 완료'만 보지 않고 실제로 최근 고점을 공격하는 종목까지 후보로 인정한다.
    prev_high_attack = cur_high >= prev_high * 0.995 if prev_high > 0 else False
    prev5_attack = cur_high >= prev5_high * 0.99 if prev5_high > 0 else False
    high_attack = bool(prev_high_attack or prev5_attack)

    closes = [float(x["close"]) for x in daily]
    long_hits = []
    long_levels = {}
    for period in (112, 224, 448):
        arr = _eavg(closes, period)
        level = float(arr[-1])
        prev_level = float(arr[-2]) if len(arr) >= 2 else level
        long_levels[period] = level
        attacked = (
            cur_high >= level
            and cur_close >= level * 0.995
            and (cur_open <= level or float(prev["close"]) <= prev_level)
        )
        if attacked:
            long_hits.append(period)

    bb = _bb_upper(closes, 40, 2.2)
    bb_ok = False
    bb_level = None
    if len(bb) >= 2 and bb[-1] is not None:
        bb_level = float(bb[-1])
        prev_bb = float(bb[-2]) if bb[-2] is not None else bb_level
        bb_ok = (
            cur_high >= bb_level
            and cur_close >= bb_level * 0.995
            and (cur_open <= bb_level or float(prev["close"]) <= prev_bb)
        )

    resistance_ok = bool(long_hits or bb_ok)

    score = sum((
        1 if price_strength else 0,
        1 if flow_ok else 0,
        1 if high_attack else 0,
        1 if resistance_ok else 0,
    ))
    ok = score >= max(1, int(min_score))

    reasons = [
        f"시가위 {'O' if price_strength else 'X'}",
        f"거래속도 {flow_pace:.2f}x {'O' if flow_ok else 'X'}",
        f"고점공격 {'O' if high_attack else 'X'}",
        (
            "장기저항 " + (
                "EMA" + ",".join(map(str, long_hits))
                if long_hits else ("BB40/2.2" if bb_ok else "X")
            )
        ),
    ]
    return ok, {
        "reason": " · ".join(reasons) + f" · PUMA {score}/4",
        "basis_open": cur_open,
        "prev_high": prev_high,
        "prev5_high": prev5_high,
        "day_volume_ratio": day_volume_ratio,
        "volume_pace": volume_pace,
        "turnover_pace": turnover_pace,
        "flow_pace": flow_pace,
        "gap_ok": gap_ok,  # 정보만 기록. 필수조건 아님.
        "price_strength": price_strength,
        "flow_ok": flow_ok,
        "high_attack": high_attack,
        "prev_high_attack": prev_high_attack,
        "prev5_attack": prev5_attack,
        "long_ma_hits": long_hits,
        "long_ma_levels": long_levels,
        "bb40_22_breakout": bb_ok,
        "bb40_22_level": bb_level,
        "resistance_ok": resistance_ok,
        "puma_score": score,
        "date": _date_key(cur.get("date")),
    }

def evaluate_gaboja(
    minute_rows: List[dict],
    daily_rows: List[dict],
    *,
    now: datetime | None = None,
    scan_start: str = "08:50",
    scan_end: str = "10:00",
    apply_secondary_filter: bool = True,
    secondary_min_score: int = 3,
) -> GabojaSignal:
    """가보자 단타 자동진입.

    1) 영웅문 검색기 후보를 PUMA가 장중 힘으로 2차 선별한다.
       갭/전일 하루 거래량 300%는 필수가 아니다.
    2) 5분봉: 영1 이후 거래량이 줄어든 차(눌림), 또는 그 눌림 뒤
       영1 전고를 양봉 몸통이 실제로 관통하는 재돌파에서만 진입.
    3) 차 눌림 진입은 당일 기준봉 시가 손절.
       전고 몸통돌파 진입은 직전 차 눌림 저점 손절.
    """
    candles = normalize_candles(minute_rows or [])
    if not candles:
        return GabojaSignal(False, reason="5분봉 데이터 없음")

    now = now or datetime.now()
    hm = now.strftime("%H:%M")
    latest_day = _date_key(candles[-1].get("date"))
    today_key = now.strftime("%Y%m%d")
    latest_price = float(candles[-1]["close"])

    # 08:50부터 후보 감시는 가능하지만 실제 주문은 정규장 시작 뒤에만 허용한다.
    # 장 시작 전 API가 전일 마지막 5분봉을 반환할 수 있으므로 stale 재진입을 막는다.
    if hm < "09:00":
        return GabojaSignal(False, reason=f"장 시작 전 · 자동매수 대기 {hm}", current_price=latest_price)
    if latest_day != today_key:
        return GabojaSignal(False, reason=f"당일 5분봉 대기 · 최신 데이터 {latest_day or '없음'}", current_price=latest_price)

    day = latest_day
    session = [c for c in candles if _date_key(c.get("date")) == day and (_hm(c.get("date")) == "" or _hm(c.get("date")) >= "09:00")]
    if not session:
        return GabojaSignal(False, reason="장중 5분봉 데이터 없음", current_price=latest_price)

    # 일봉 과거값은 캐시하고, 오늘 OHLCV는 최신 5분봉들로 합성한다.
    # PUMA는 갭 여부가 아니라 장중 가격 힘/거래속도/고점공격/저항공격을 재검증한다.
    live_bar = {
        "date": day,
        "open": float(session[0]["open"]),
        "high": max(float(x["high"]) for x in session),
        "low": min(float(x["low"]) for x in session),
        "close": float(session[-1]["close"]),
        "volume": sum(float(x["volume"]) for x in session),
    }
    candidate_ok, d = _candidate_filter(
        daily_rows,
        live_bar,
        session_bars=len(session),
        min_score=secondary_min_score,
    )
    basis_open = float(d.get("basis_open", live_bar["open"]) or live_bar["open"])
    day_ratio = float(d.get("day_volume_ratio", 0.0) or 0.0)
    if apply_secondary_filter and not candidate_ok:
        return GabojaSignal(
            False,
            reason=f"PUMA 2차 선별 대기 · {d.get('reason','-')}",
            current_price=float(session[-1]["close"]),
            basis_open=basis_open,
            day_volume_ratio=day_ratio,
            details=d,
        )
    if len(session) < 4:
        return GabojaSignal(False, reason="가보자 5분봉 구조 형성 대기", current_price=float(candles[-1]["close"]),
                            basis_open=basis_open, day_volume_ratio=day_ratio, details=d)

    time_ok = scan_start <= hm <= scan_end
    current = session[-1]
    current_price = float(current["close"])

    # 기준봉 시가까지 눌리는 것은 '차'가 아니다. 영1 상승폭의 15% 또는 시가의 0.2% 중
    # 큰 값을 최소 안전거리로 두며 이후 설정값으로 조정 가능하게 설계한다.
    pairs = []
    for i in range(1, len(session) - 1):
        bar = session[i]
        prior = session[max(0, i - 3):i]
        if not prior:
            continue
        prior_high = max(float(x["high"]) for x in prior)
        prior_vol = mean(float(x["volume"]) for x in prior)
        impulse = (
            float(bar["close"]) > float(bar["open"])
            and float(bar["high"]) > prior_high
            and float(bar["volume"]) >= prior_vol
        )
        if not impulse:
            continue

        young1_high = float(bar["high"])
        safety = max((young1_high - basis_open) * 0.15, basis_open * 0.002)
        if young1_high <= basis_open or safety <= 0:
            continue

        for j in range(i + 1, min(len(session), i + 5)):
            pb = session[j]
            pb_mid = (float(pb["high"]) + float(pb["low"])) / 2.0
            pullback = (
                float(pb["low"]) < young1_high
                and float(pb["close"]) < young1_high
                and float(pb["low"]) >= basis_open + safety
                and float(pb["volume"]) < float(bar["volume"])
                and float(pb["close"]) >= pb_mid
            )
            if pullback:
                pairs.append((i, j, young1_high, float(pb["low"]), safety))
                break

    if not pairs:
        return GabojaSignal(False, reason="영1 이후 유효한 차(저거래량 눌림) 대기",
                            current_price=current_price, basis_open=basis_open,
                            day_volume_ratio=day_ratio, details={**d, "time_ok": time_ok})

    i, j, young1_high, pullback_low, safety = pairs[-1]
    latest = len(session) - 1
    pb = session[j]

    # 눌림 진입: 바로 현재 봉이 '차'이고, 거래량 감소 + 시가 손절선과 거리 유지 + 상단부 마감.
    pullback_entry = latest == j

    # 전고돌파 진입: 꼬리만 찌르는 것은 제외.
    # 양봉 몸통의 아래쪽 <= 영1 전고 < 몸통 위쪽이어야 실제 몸통 관통으로 인정.
    body_low = min(float(current["open"]), float(current["close"]))
    body_high = max(float(current["open"]), float(current["close"]))
    body_rebreak = (
        latest > j
        and float(current["close"]) > float(current["open"])
        and body_low <= young1_high < body_high
        and float(current["low"]) > basis_open
    )

    passed = bool(time_ok and (pullback_entry or body_rebreak))
    kind = "PULLBACK" if pullback_entry else ("BODY_REBREAK" if body_rebreak else "")
    if passed:
        label = "차 눌림" if kind == "PULLBACK" else "전고 몸통돌파"
        if kind == "BODY_REBREAK":
            reason = f"가보자 {label} 진입 · 직전 차 저점 {pullback_low:,.0f} 이탈 손절"
        else:
            reason = f"가보자 {label} 진입 · 기준봉 시가 {basis_open:,.0f} 이탈 손절"
    elif not time_ok:
        reason = f"가보자 패턴 확인 · 검색시간 외({scan_start}~{scan_end})"
    else:
        reason = "차 확인 완료 · 전고 몸통돌파 대기"

    return GabojaSignal(
        passed=passed,
        entry_kind=kind,
        reason=reason,
        current_price=current_price,
        basis_open=basis_open,
        young1_high=young1_high,
        pullback_low=pullback_low,
        day_volume_ratio=day_ratio,
        details={
            **d,
            "time_ok": time_ok,
            "young1_index": i,
            "pullback_index": j,
            "young1_high": young1_high,
            "pullback_low": pullback_low,
            "stop_safety": safety,
            "pullback_volume": float(pb["volume"]),
            "young1_volume": float(session[i]["volume"]),
            "body_rebreak": body_rebreak,
        },
    )
