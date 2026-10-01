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


def _bar_elapsed_seconds(raw, now: datetime, timeframe_min: int = 5) -> float:
    """Elapsed seconds inside the live candle bucket.

    Historical/completed bars return a full timeframe. The active bar uses only
    elapsed wall-clock time so raw cumulative volume is never compared directly
    with a completed Young bar.
    """
    full = float(max(1, int(timeframe_min or 5)) * 60)
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) < 12:
        return full
    try:
        stamp = datetime.strptime(digits[:12], "%Y%m%d%H%M")
    except Exception:
        return full
    if stamp.date() != now.date():
        return full
    delta = (now - stamp).total_seconds()
    if delta < 0 or delta >= full:
        return full
    return max(0.0, float(delta))


def _volume_pace(volume: float, elapsed_seconds: float) -> float:
    sec = max(1.0, float(elapsed_seconds or 0.0))
    return max(0.0, float(volume or 0.0)) / sec


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
    cha_max_ratio: float = 0.35,
    cha_volume_pace_ratio: float = 1.00,
    cha_min_live_seconds: int = 20,
) -> GabojaSignal:
    """가보자 단타 자동진입.

    1) NXT 프리마켓 08:00부터 후보 검색과 실제 자동매매를 함께 시작한다.
       09:00 이후에는 08시부터 이어진 NXT 흐름과 KRX 신규 후보를 같은 PUMA 기준으로 비교한다.
    2) 1영은 장대양봉 한 봉에 고정하지 않는다. 특히 장 시작 첫 5분봉은 음봉이어도
       거래량/변동폭이 살아 있으면 1영 구조의 시작봉으로 인정한다.
    3) 차는 기존 65% 깊은 되돌림 + 거래량 진행속도 둔화 규칙을 그대로 쓴다.
       진행 중인 차가 조건을 충족하는 순간 바로 매수한다.
    4) 두 번째 경로는 '고거래량 하락 후 회복'이다. 65% 이상 깊게 밀렸는데
       거래량 진행속도가 줄지 않는 동안에는 절대 차 매수를 하지 않고 관찰만 한다.
       이후 힘이 실제로 회복되어 전고를 양봉 몸통으로 돌파하는 봉에서만 진입한다.
       차 진입의 최초 손절은 기준봉 시가, 전고돌파 진입은 확인된 눌림 저점이다.
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
    if len(session) < 2:
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

    # 실시간 1차 차 영역:
    #   B = 기준봉 시가, H = 영 고점, R = H-B
    #   B < 현재가 <= B + R*0.35  (영 고점에서 65% 이상 되돌림)
    # 즉 고점 근처의 얕은 눌림은 차로 보지 않고, 영 상승폭의 절반 아래까지 깊게 눌린
    # 현재 봉만 1차 차 후보로 본다. 현재 봉을 그대로 사용하므로 미래 봉 확인이 필요 없다.
    cha_ratio = min(0.95, max(0.05, float(cha_max_ratio or 0.35)))
    cha_pace_ratio = min(2.0, max(0.10, float(cha_volume_pace_ratio or 1.00)))
    cha_live_min_sec = max(0, min(120, int(cha_min_live_seconds or 0)))
    latest_index = len(session) - 1

    # 1영은 첫 5분봉부터 볼 수 있다. 첫 봉은 음봉이어도 후보가 이미
    # 장초 거래량/PUMA 힘 필터를 통과했다면 구조의 시작봉으로 인정한다.
    pairs = []
    recovery_setups = []
    for i in range(0, len(session) - 1):
        bar = session[i]
        opening_young = (
            i == 0
            and float(bar["volume"]) > 0
            and float(bar["high"]) > float(bar["low"])
        )

        if opening_young:
            young_start = 0
            young_high = float(bar["high"])
            young_volume = float(bar["volume"])
            young_volume_total = float(bar["volume"])
            young_bar_count = 1
            young_kind = "opening_bearish" if float(bar["close"]) < float(bar["open"]) else "opening"
            # 첫 봉 음봉은 당일 시가 아래에서 끝날 수 있으므로 구조 바닥은 첫 봉 저가로 둔다.
            # 이후 65% 깊은 차가 확인되면 그 차에서 바로 매수한다.
            structural_floor = min(basis_open, float(bar["low"]))
        else:
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

            # 언덕형 1영: 최근 최대 7봉 안에서 저점부터 이어진 상승 언덕 전체를 인정한다.
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
                young_volume_total = float(bar["volume"])
                young_bar_count = 1
                young_kind = "single"
            elif hill_shape:
                young_high = hill_high
                young_volume = max(float(x["volume"]) for x in hill)
                young_volume_total = sum(float(x["volume"]) for x in hill)
                young_bar_count = max(1, len(hill))
                young_kind = "hill"
            else:
                continue
            structural_floor = basis_open

        rise = young_high - structural_floor
        if rise <= 0:
            continue
        cha_ceiling = structural_floor + rise * cha_ratio
        young_pace = _volume_pace(
            young_volume_total,
            float(young_bar_count * 5 * 60),
        )

        # 1영 이후 첫 65% 깊은 차를 찾는다.
        # 거래량 진행속도가 줄면 기존 차 매수 경로, 줄지 않으면 '고거래량 하락'
        # 회복 감시 경로로 전환한다. 고거래량 하락 중에는 절대 매수하지 않는다.
        hot_pullback_idx = -1
        hot_pullback_low = 0.0
        hot_pullback_pace = 0.0
        hot_pullback_depth = 0.0

        for j in range(i + 1, len(session)):
            pb = session[j]
            pb_low = float(pb["low"])
            pb_close = float(pb["close"])
            if pb_low <= structural_floor or pb_close <= structural_floor:
                break

            deep_zone = structural_floor < pb_close <= cha_ceiling
            is_live_bar = j == latest_index
            if is_live_bar:
                elapsed = _bar_elapsed_seconds(pb.get("date"), now, 5)
                live_ready = elapsed >= float(cha_live_min_sec)
            else:
                elapsed = 5.0 * 60.0
                live_ready = True

            pb_pace = _volume_pace(float(pb["volume"]), elapsed if elapsed > 0 else 1.0)
            lower_volume_pace = young_pace > 0 and pb_pace <= young_pace * cha_pace_ratio

            if deep_zone and live_ready and lower_volume_pace:
                depth_pct = ((young_high - pb_close) / rise) * 100.0
                pairs.append((
                    young_start, i, j, young_high, pb_low,
                    cha_ceiling, young_volume, young_kind, depth_pct,
                    young_pace, pb_pace, elapsed, lower_volume_pace,
                    structural_floor,
                ))
                break

            if deep_zone and live_ready and not lower_volume_pace:
                # 거래량이 안 죽은 채 깊게 밀리면 차 매수 금지.
                # 이후 전고 몸통돌파가 확인될 때까지 회복 후보로만 유지한다.
                if hot_pullback_idx < 0:
                    hot_pullback_idx = j
                    hot_pullback_low = pb_low
                    hot_pullback_pace = pb_pace
                    hot_pullback_depth = ((young_high - pb_close) / rise) * 100.0
                else:
                    hot_pullback_low = min(hot_pullback_low, pb_low)
                    hot_pullback_pace = max(hot_pullback_pace, pb_pace)
                    hot_pullback_depth = max(
                        hot_pullback_depth,
                        ((young_high - pb_close) / rise) * 100.0,
                    )

        # 고거래량 하락형은 차에서 사지 않는다. 눌림이 끝난 뒤 현재봉이
        # 양봉 몸통으로 1영 전고를 실제 돌파할 때만 별도 회복 진입 신호를 만든다.
        if hot_pullback_idx >= 0 and latest_index > hot_pullback_idx:
            current_bar = session[latest_index]
            current_body_low = min(float(current_bar["open"]), float(current_bar["close"]))
            current_body_high = max(float(current_bar["open"]), float(current_bar["close"]))
            recovery_body_break = bool(
                float(current_bar["close"]) > float(current_bar["open"])
                and current_body_low <= young_high < current_body_high
                and float(current_bar["low"]) > structural_floor
            )
            if recovery_body_break:
                recovery_setups.append((
                    young_start, i, hot_pullback_idx, young_high, hot_pullback_low,
                    cha_ceiling, young_volume, young_kind, hot_pullback_depth,
                    young_pace, hot_pullback_pace, structural_floor,
                ))

    if not pairs:
        if recovery_setups:
            (
                recovery_young_start, recovery_i, recovery_j, recovery_high, recovery_low,
                recovery_cha_ceiling, recovery_young_volume, recovery_young_kind,
                recovery_depth_pct, recovery_young_pace, recovery_pullback_pace,
                recovery_floor,
            ) = recovery_setups[-1]
            recovery_passed = bool(time_ok)
            opening_note = " · 첫봉 음봉 1영 인정" if recovery_young_kind == "opening_bearish" else ""
            reason = (
                f"가보자 고거래량 하락→전고 몸통돌파 회복진입{opening_note} · "
                f"차에서는 매수 보류 · 전고 {recovery_high:,.0f} 몸통돌파 확인 · "
                f"직전 눌림저점 {recovery_low:,.0f} 이탈 손절"
                if recovery_passed else
                f"고거래량 하락 후 전고 몸통돌파 확인 · 검색시간 외({scan_start}~{scan_end})"
            )
            return GabojaSignal(
                passed=recovery_passed,
                entry_kind="RECOVERY_BREAKOUT" if recovery_passed else "",
                reason=reason,
                current_price=current_price,
                basis_open=basis_open,
                young1_high=recovery_high,
                pullback_low=recovery_low,
                day_volume_ratio=day_ratio,
                details={
                    **d, **premarket,
                    "time_ok": time_ok,
                    "trade_start": trade_start,
                    "cha_max_ratio": cha_ratio,
                    "cha_volume_pace_ratio": cha_pace_ratio,
                    "cha_min_live_seconds": cha_live_min_sec,
                    "recovery_breakout": True,
                    "recovery_pullback_index": recovery_j,
                    "recovery_pullback_low": recovery_low,
                    "recovery_depth_pct": recovery_depth_pct,
                    "recovery_pullback_volume_pace": recovery_pullback_pace,
                    "young_volume_pace": recovery_young_pace,
                    "young1_index": recovery_i,
                    "young1_start_index": recovery_young_start,
                },
            )

        return GabojaSignal(
            False,
            reason="1영 이후 65% 이상 되돌린 차 또는 고거래량 회복형 대기",
            current_price=current_price,
            basis_open=basis_open,
            day_volume_ratio=day_ratio,
            details={
                **d, **premarket, "time_ok": time_ok, "trade_start": trade_start,
                "cha_max_ratio": cha_ratio,
                "cha_volume_pace_ratio": cha_pace_ratio,
                "cha_min_live_seconds": cha_live_min_sec,
                "recovery_breakout": False,
            },
        )

    (
        young_start, i, j, young1_high, pullback_low, cha_ceiling,
        young_volume, young_kind, cha_depth_pct, young_pace,
        pullback_pace, pullback_elapsed_sec, lower_volume_pace,
        structural_floor,
    ) = pairs[-1]
    latest = len(session) - 1
    pb = session[j]

    # 차 매수: 현재 진행 중인 5분봉이 65% 깊은 차 영역에 들어왔고
    # 거래량 진행속도까지 둔화됐으면 다음 2영을 기다리지 않고 즉시 진입한다.
    pullback_entry = latest == j

    # 차 타점을 놓친 경우의 보조 진입: 전고를 꼬리가 아니라 양봉 몸통으로 돌파할 때만 허용.
    body_low = min(float(current["open"]), float(current["close"]))
    body_high = max(float(current["open"]), float(current["close"]))
    body_rebreak = (
        latest > j
        and float(current["close"]) > float(current["open"])
        and body_low <= young1_high < body_high
        and float(current["low"]) > structural_floor
    )

    passed = bool(time_ok and (pullback_entry or body_rebreak))
    kind = "PULLBACK" if pullback_entry else ("YOUNG2" if body_rebreak else "")
    if passed:
        opening_note = " · 첫봉 음봉 1영 인정" if young_kind == "opening_bearish" else ""
        if kind == "PULLBACK":
            reason = (
                f"가보자 1영→차 매수{opening_note} · 65% 깊은 눌림 "
                f"({current_price:,.0f} ≤ {cha_ceiling:,.0f}) · "
                f"거래량속도 {pullback_pace:.2f}/s ≤ 영 {young_pace:.2f}/s · "
                f"기준봉 시가 {basis_open:,.0f} 이탈 손절"
            )
        else:
            reason = (
                f"가보자 전고 몸통돌파 보조진입{opening_note} · "
                f"직전 차 저점 {pullback_low:,.0f} 이탈 손절"
            )
    elif not time_ok:
        reason = f"가보자 패턴 확인 · 검색시간 외({scan_start}~{scan_end})"
    elif latest == j:
        reason = "65% 차 확인 · 차 매수 조건 대기"
    else:
        reason = "차 타점 경과 · 전고 몸통돌파 보조진입 대기"

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
            "opening_bearish_young": young_kind == "opening_bearish",
            "structural_floor": structural_floor,
            "pullback_index": j,
            "young2_index": -1,
            "young2_price": 0.0,
            "young1_high": young1_high,
            "pullback_low": pullback_low,
            "cha_ceiling": cha_ceiling,
            "cha_max_ratio": cha_ratio,
            "cha_depth_pct": cha_depth_pct,
            "early_cha": pullback_entry,
            "cha_ready": True,
            "cha_volume_pace_ratio": cha_pace_ratio,
            "cha_min_live_seconds": cha_live_min_sec,
            "pullback_elapsed_sec": pullback_elapsed_sec,
            "pullback_volume_pace": pullback_pace,
            "young_volume_pace": young_pace,
            "lower_volume_pace": lower_volume_pace,
            "pullback_volume": float(pb["volume"]),
            "young1_volume": young_volume,
            "body_rebreak": body_rebreak,
        },
    )
