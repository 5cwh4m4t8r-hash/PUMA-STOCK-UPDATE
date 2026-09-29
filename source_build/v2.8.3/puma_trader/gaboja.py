from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import sqrt
from statistics import mean
from typing import Dict, List

from .swing import normalize_candles
from .danta import market_open_volume_ratio


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


def _premarket_snapshot(
    candles_raw: List[dict],
    day: str,
    *,
    start: str = "08:00",
    end: str = "08:50",
) -> dict:
    """Summarize today's NXT premarket bars without turning them into buy signals."""
    candles = normalize_candles(candles_raw or [])
    rows = [
        x for x in candles
        if _date_key(x.get("date")) == str(day)
        and start <= _hm(x.get("date")) < end
    ]
    if not rows:
        return {
            "premarket_available": False,
            "premarket_bars": 0,
            "premarket_open": 0.0,
            "premarket_close": 0.0,
            "premarket_high": 0.0,
            "premarket_low": 0.0,
            "premarket_volume": 0.0,
            "premarket_change_pct": 0.0,
            "premarket_high_retention_pct": 0.0,
        }

    op = float(rows[0]["open"])
    cl = float(rows[-1]["close"])
    hi = max(float(x["high"]) for x in rows)
    lo = min(float(x["low"]) for x in rows)
    vol = sum(float(x["volume"]) for x in rows)
    return {
        "premarket_available": True,
        "premarket_bars": len(rows),
        "premarket_open": op,
        "premarket_close": cl,
        "premarket_high": hi,
        "premarket_low": lo,
        "premarket_volume": vol,
        "premarket_change_pct": ((cl / op - 1.0) * 100.0) if op > 0 else 0.0,
        "premarket_high_retention_pct": ((cl / hi) * 100.0) if hi > 0 else 0.0,
    }


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
    morning_volume_ratio: float = 0.0,
    min_score: int = 3,
) -> tuple[bool, dict]:
    """PUMA 2차 후보 선별.

    영웅문 검색기가 1차 후보를 공급한 뒤 PUMA가 장중 힘을 재검증한다.
    장초 누적 거래량은 최근 5일 동일 시간대 평균 대비 300% 이상이어야 한다.

    점수(4개 중 3개 이상) + 장초 거래량 300% 필수:
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
    morning_volume_ratio = float(morning_volume_ratio or 0.0)
    volume_burst_ok = morning_volume_ratio >= 3.0
    flow_ok = volume_burst_ok

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
    ok = bool(volume_burst_ok and score >= max(1, int(min_score)))

    reasons = [
        f"시가위 {'O' if price_strength else 'X'}",
        f"장초거래량 {morning_volume_ratio:.2f}x {'O' if volume_burst_ok else 'X'}",
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
        "morning_volume_ratio": morning_volume_ratio,
        "morning_volume_300_ok": volume_burst_ok,
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
    scan_start: str = "08:00",
    trade_start: str = "08:00",
    scan_end: str = "10:00",
    apply_secondary_filter: bool = True,
    secondary_min_score: int = 3,
) -> GabojaSignal:
    """가보자 단타 자동진입.

    1) NXT 프리마켓 08:00부터 후보 검색과 실제 자동매매를 함께 시작한다.
       09:00 이후에는 08시부터 이어진 NXT 흐름과 KRX 신규 후보를 같은 PUMA 기준으로 비교한다.
    2) '영'은 장대양봉 한 봉에 고정하지 않는다. 단일 임펄스 또는 여러 5분봉이 이어진 상승 언덕 전체를
       영 구간으로 인정하고, 그 뒤 거래량이 줄어든 차(눌림) 또는 영 고점 몸통 재돌파에서 진입한다.
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
    premarket = _premarket_snapshot(candles, today_key)

    # trade_start 이전에는 신규진입을 막는다. v2.9.59 기본 trade_start는
    # 08:00이므로 NXT 프리마켓도 실제 가보자 진입 세션에 포함된다.
    if hm < trade_start:
        if hm < scan_start:
            reason = f"가보자 검색 시작 전 · {scan_start} 대기"
        elif premarket.get("premarket_available"):
            reason = f"가보자 검색 중 · 실제 자동매수는 {trade_start}부터"
        else:
            reason = f"가보자 후보 탐색 중 · 실제 자동매수는 {trade_start}부터"
        return GabojaSignal(
            False,
            reason=reason,
            current_price=latest_price,
            details={**premarket, "time_ok": False, "trade_start": trade_start},
        )

    # 장 시작 직후 API가 아직 전일 마지막 봉을 반환할 수 있으므로 stale 재진입을 막는다.
    if latest_day != today_key:
        return GabojaSignal(
            False,
            reason=f"당일 5분봉 대기 · 최신 데이터 {latest_day or '없음'}",
            current_price=latest_price,
            details={**premarket, "time_ok": False, "trade_start": trade_start},
        )

    day = latest_day
    session = [
        x for x in candles
        if _date_key(x.get("date")) == day
        and (_hm(x.get("date")) == "" or _hm(x.get("date")) >= trade_start)
    ]
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
    morning = market_open_volume_ratio(candles, 5, session_start=trade_start)
    morning_ratio = float(morning.get("ratio", 0.0) or 0.0)
    candidate_ok, d = _candidate_filter(
        daily_rows,
        live_bar,
        session_bars=len(session),
        morning_volume_ratio=morning_ratio,
        min_score=secondary_min_score,
    )
    basis_open = float(d.get("basis_open", live_bar["open"]) or live_bar["open"])
    # GabojaSignal의 거래량 비율도 이제 장초 동일시간대 5일 평균 대비 비율을 사용한다.
    day_ratio = float(d.get("morning_volume_ratio", 0.0) or 0.0)
    if apply_secondary_filter and not candidate_ok:
        return GabojaSignal(
            False,
            reason=f"PUMA 2차 선별 대기 · {d.get('reason','-')}",
            current_price=float(session[-1]["close"]),
            basis_open=basis_open,
            day_volume_ratio=day_ratio,
            details={**d, **premarket, "trade_start": trade_start},
        )
    if len(session) < 4:
        return GabojaSignal(
            False,
            reason="가보자 5분봉 구조 형성 대기",
            current_price=float(candles[-1]["close"]),
            basis_open=basis_open,
            day_volume_ratio=day_ratio,
            details={**d, **premarket, "trade_start": trade_start},
        )

    entry_window_start = max(str(scan_start), str(trade_start))
    time_ok = entry_window_start <= hm <= scan_end
    current = session[-1]
    current_price = float(current["close"])

    # 기준봉 시가까지 눌리는 것은 '차'가 아니다. 영 상승폭의 15% 또는 시가의 0.2% 중
    # 큰 값을 최소 안전거리로 둔다.
    #
    # 영은 '장대양봉 한 봉'으로 고정하지 않는다.
    #  - single: 기존처럼 한 봉이 전고를 힘있게 돌파한 경우
    #  - hill: 최근 구조의 저점에서 여러 봉이 이어져 상승 언덕을 만들고 마지막 봉이 구간 고점을 만든 경우
    # 두 형태 모두 같은 차 눌림/몸통 재돌파 규칙으로 연결한다.
    pairs = []
    for i in range(1, len(session) - 1):
        bar = session[i]
        prior = session[max(0, i - 3):i]
        if not prior:
            continue

        prior_high = max(float(x["high"]) for x in prior)
        prior_vol = mean(float(x["volume"]) for x in prior)
        single_impulse = (
            float(bar["close"]) > float(bar["open"])
            and float(bar["high"]) > prior_high
            and float(bar["volume"]) >= prior_vol
        )

        # 언덕형 영: 최근 최대 7봉 안에서 가장 낮은 저점을 시작점으로 잡아
        # 상승 진행과 구간 고점 갱신을 확인한다. 특정 '몇 번째 봉'을 영으로 고정하지 않는다.
        lookback_start = max(0, i - 6)
        lookback = session[lookback_start:i + 1]
        rel_start = min(
            range(len(lookback)),
            key=lambda k: float(lookback[k]["low"]),
        )
        young_start = lookback_start + rel_start
        hill = session[young_start:i + 1]
        bullish = sum(1 for x in hill if float(x["close"]) >= float(x["open"]))
        progress = sum(
            1 for k in range(1, len(hill))
            if float(hill[k]["close"]) >= float(hill[k - 1]["close"])
        )
        hill_high = max(float(x["high"]) for x in hill)
        hill_open = float(hill[0]["open"])
        before_hill = session[max(0, young_start - 3):young_start]
        before_high = max((float(x["high"]) for x in before_hill), default=basis_open)
        hill_shape = (
            len(hill) >= 2
            and float(bar["high"]) >= hill_high
            and float(bar["close"]) > hill_open
            and hill_high > max(basis_open, before_high)
            and bullish >= max(2, (len(hill) + 1) // 2)
            and progress >= max(1, (len(hill) - 1) // 2)
        )

        if single_impulse:
            young_start = i
            young_high = float(bar["high"])
            young_volume = float(bar["volume"])
            young_kind = "single"
        elif hill_shape:
            young_high = hill_high
            young_volume = max(float(x["volume"]) for x in hill)
            young_kind = "hill"
        else:
            continue

        safety = max((young_high - basis_open) * 0.15, basis_open * 0.002)
        if young_high <= basis_open or safety <= 0:
            continue

        for j in range(i + 1, min(len(session), i + 5)):
            pb = session[j]
            pb_mid = (float(pb["high"]) + float(pb["low"])) / 2.0
            pullback = (
                float(pb["low"]) < young_high
                and float(pb["close"]) < young_high
                and float(pb["low"]) >= basis_open + safety
                and float(pb["volume"]) < young_volume
                and float(pb["close"]) >= pb_mid
            )
            if pullback:
                pairs.append((
                    young_start, i, j, young_high,
                    float(pb["low"]), safety, young_volume, young_kind,
                ))
                break

    if not pairs:
        return GabojaSignal(False, reason="영 상승구간 이후 유효한 차(저거래량 눌림) 대기",
                            current_price=current_price, basis_open=basis_open,
                            day_volume_ratio=day_ratio,
                            details={**d, **premarket, "time_ok": time_ok, "trade_start": trade_start})

    young_start, i, j, young1_high, pullback_low, safety, young_volume, young_kind = pairs[-1]
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
            **premarket,
            "time_ok": time_ok,
            "trade_start": trade_start,
            "young1_index": i,
            "young_start_index": young_start,
            "young_end_index": i,
            "young_kind": young_kind,
            "pullback_index": j,
            "young1_high": young1_high,
            "pullback_low": pullback_low,
            "stop_safety": safety,
            "pullback_volume": float(pb["volume"]),
            "young1_volume": young_volume,
            "body_rebreak": body_rebreak,
        },
    )
