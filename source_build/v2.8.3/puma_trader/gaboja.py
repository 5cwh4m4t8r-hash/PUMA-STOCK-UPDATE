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


def _daily_filter(daily_rows: List[dict], live_bar: dict | None = None) -> tuple[bool, dict]:
    daily = normalize_candles(daily_rows or [])
    if live_bar:
        live_day = _date_key(live_bar.get("date"))
        if daily and _date_key(daily[-1].get("date")) == live_day:
            daily[-1] = dict(live_bar)
        elif not daily or _date_key(daily[-1].get("date")) < live_day:
            daily.append(dict(live_bar))
    if len(daily) < 6:
        return False, {"reason": "일봉 6봉 미만"}

    cur = daily[-1]
    prev = daily[-2]
    prev5 = daily[-6:-1]
    prev5_high = max(float(x["high"]) for x in prev5)
    gap_ok = float(cur["open"]) > prev5_high

    prev_vol = float(prev["volume"])
    vol_ratio = float(cur["volume"]) / prev_vol if prev_vol > 0 else 0.0
    volume_ok = vol_ratio >= 3.0

    closes = [float(x["close"]) for x in daily]
    long_hits = []
    for period in (112, 224, 448):
        arr = _eavg(closes, period)
        level = float(arr[-1])
        prev_level = float(arr[-2]) if len(arr) >= 2 else level
        crossed = (
            float(cur["high"]) > level
            and float(cur["close"]) >= level
            and float(prev["close"]) <= prev_level
        )
        if crossed:
            long_hits.append(period)

    bb = _bb_upper(closes, 40, 2.2)
    bb_ok = False
    if len(bb) >= 2 and bb[-1] is not None and bb[-2] is not None:
        bb_ok = (
            float(cur["high"]) > float(bb[-1])
            and float(cur["close"]) >= float(bb[-1])
            and float(prev["close"]) <= float(bb[-2])
        )

    resistance_ok = bool(long_hits or bb_ok)
    ok = bool(gap_ok and volume_ok and resistance_ok)
    reason = (
        f"이전5봉 갭 {'확인' if gap_ok else '미확인'} · "
        f"거래량 {vol_ratio:.2f}배 · "
        f"{'장기EMA '+','.join(map(str,long_hits)) if long_hits else ('BB40/2.2 돌파' if bb_ok else '장기EMA/BB 돌파 미확인')}"
    )
    return ok, {
        "reason": reason,
        "basis_open": float(cur["open"]),
        "prev5_high": prev5_high,
        "day_volume_ratio": vol_ratio,
        "gap_ok": gap_ok,
        "volume_ok": volume_ok,
        "long_ma_hits": long_hits,
        "bb40_22_breakout": bb_ok,
        "date": _date_key(cur.get("date")),
    }


def evaluate_gaboja(
    minute_rows: List[dict],
    daily_rows: List[dict],
    *,
    now: datetime | None = None,
    scan_start: str = "08:50",
    scan_end: str = "10:00",
) -> GabojaSignal:
    """가보자 단타 자동진입.

    1) 일봉: 이전 5봉 위 갭 + 전일대비 거래량 300%+ +
       EMA112/224/448 또는 BB40/2.2 상향돌파.
    2) 5분봉: 영1 이후 거래량이 줄어든 차(눌림), 또는 그 눌림 뒤
       영1 전고를 양봉 몸통이 실제로 관통하는 재돌파에서만 진입.
    3) 손절 기준은 일봉 기준봉 시가.
    """
    candles = normalize_candles(minute_rows or [])
    if not candles:
        return GabojaSignal(False, reason="5분봉 데이터 없음")

    day = _date_key(candles[-1].get("date"))
    session = [c for c in candles if _date_key(c.get("date")) == day and (_hm(c.get("date")) == "" or _hm(c.get("date")) >= "09:00")]
    if not session:
        return GabojaSignal(False, reason="장중 5분봉 데이터 없음")

    # 일봉은 장중 매 스캔마다 다시 받을 필요가 없다.
    # 오늘 OHLCV는 최신 5분봉들로 합성해 거래량 300%와 돌파 여부를 실시간 갱신한다.
    live_bar = {
        "date": day,
        "open": float(session[0]["open"]),
        "high": max(float(x["high"]) for x in session),
        "low": min(float(x["low"]) for x in session),
        "close": float(session[-1]["close"]),
        "volume": sum(float(x["volume"]) for x in session),
    }
    daily_ok, d = _daily_filter(daily_rows, live_bar)
    basis_open = float(d.get("basis_open", 0.0) or 0.0)
    day_ratio = float(d.get("day_volume_ratio", 0.0) or 0.0)
    if not daily_ok:
        return GabojaSignal(False, reason=f"가보자 일봉 선별 대기 · {d.get('reason','-')}",
                            current_price=float(session[-1]["close"]), basis_open=basis_open,
                            day_volume_ratio=day_ratio, details=d)
    if len(session) < 4:
        return GabojaSignal(False, reason="가보자 5분봉 구조 형성 대기", current_price=float(candles[-1]["close"]),
                            basis_open=basis_open, day_volume_ratio=day_ratio, details=d)

    now = now or datetime.now()
    hm = now.strftime("%H:%M")
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
