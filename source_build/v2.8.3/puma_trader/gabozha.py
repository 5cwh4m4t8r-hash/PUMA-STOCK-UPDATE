from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean
from typing import List

from .swing import ema, normalize_candles


@dataclass
class GabozhaSignal:
    passed: bool
    reason: str
    current_price: float = 0.0
    basis_open: float = 0.0
    entry_kind: str = ""
    daily_ok: bool = False
    young1_high: float = 0.0
    pullback_low: float = 0.0
    volume_ratio: float = 0.0


def _date_key(raw) -> str:
    return "".join(ch for ch in str(raw or "") if ch.isdigit())[:8]


def _bb_upper(closes: List[float], period: int, dev: float) -> float | None:
    if period <= 1 or len(closes) < period:
        return None
    xs = closes[-period:]
    m = sum(xs) / period
    sd = sqrt(sum((x - m) ** 2 for x in xs) / period)
    return m + float(dev) * sd


def _crossed_up(candle: dict, level: float | None) -> bool:
    if not level or level <= 0:
        return False
    return bool(candle["close"] > level and candle["low"] <= level)


def _daily_filter(daily_rows: List[dict], settings):
    daily = normalize_candles(daily_rows or [])
    if len(daily) < 6:
        return False, "일봉 데이터 부족", 0.0, 0.0, {}

    basis = daily[-1]
    prev5 = daily[-6:-1]
    basis_open = float(basis["open"])
    prev5_high = max(float(x["high"]) for x in prev5)
    gap_ok = basis_open > prev5_high

    prev_vol = float(daily[-2]["volume"])
    day_vol_ratio = (float(basis["volume"]) / prev_vol) if prev_vol > 0 else 0.0
    volume_ok = day_vol_ratio >= float(settings.gabozha_daily_volume_ratio)
    bull_ok = float(basis["close"]) > basis_open

    closes = [float(x["close"]) for x in daily]
    crossed = {}
    for period in (112, 224, 448):
        arr = ema(closes, period)
        level = arr[-1] if arr else None
        ok = _crossed_up(basis, level)
        crossed[f"EMA{period}"] = bool(ok)

    bb = _bb_upper(
        closes,
        int(settings.gabozha_bb_period),
        float(settings.gabozha_bb_dev),
    )
    crossed["BB40/2.2"] = _crossed_up(basis, bb)

    resistance_ok = any(crossed.values())
    daily_ok = bool(gap_ok and volume_ok and bull_ok and resistance_ok)

    if not gap_ok:
        reason = "일봉 이전 5봉 고점 갭돌파 미충족"
    elif not volume_ok:
        reason = f"일봉 거래량 {day_vol_ratio:.2f}배 · 3배 미만"
    elif not bull_ok:
        reason = "일봉 기준봉 양봉 미확인"
    elif not resistance_ok:
        reason = "장기이평 또는 BB40/2.2 상향돌파 미확인"
    else:
        hit = "/".join(k for k, v in crossed.items() if v)
        reason = f"일봉 가보자 기준봉 확인 · 거래량 {day_vol_ratio:.2f}배 · {hit}"

    return daily_ok, reason, basis_open, day_vol_ratio, crossed


def analyze_gabozha(minute_rows: List[dict], daily_rows: List[dict], settings) -> GabozhaSignal:
    """사용자 정의 '가보자' 단타 진입 판정.

    1) 일봉: 이전 5봉 고점을 갭으로 넘고, 전일 대비 거래량 300% 이상,
       장기 EMA(112/224/448) 또는 BB(40, 2.2)를 상향 돌파한 기준봉.
    2) 5분봉: 장초반 영1 형성 후 거래량이 줄어드는 얕은 '차' 눌림에서 반등 확인,
       또는 그 눌림 뒤 영1 전고를 양봉 몸통으로 상향 돌파할 때만 진입.
    3) 손절가는 일봉 기준봉 시가로 전달한다.
    """
    daily_ok, daily_reason, basis_open, day_vol_ratio, _ = _daily_filter(daily_rows, settings)

    candles = normalize_candles(minute_rows or [])
    if not candles:
        return GabozhaSignal(False, "5분봉 데이터 없음", basis_open=basis_open, daily_ok=daily_ok)

    current = float(candles[-1]["close"])
    if not daily_ok:
        return GabozhaSignal(
            False, daily_reason, current_price=current, basis_open=basis_open,
            daily_ok=False, volume_ratio=day_vol_ratio
        )

    latest_day = _date_key(candles[-1].get("date"))
    today = [c for c in candles if _date_key(c.get("date")) == latest_day]
    if len(today) < 3:
        return GabozhaSignal(
            False, "장초반 5분봉 누적 대기", current_price=current,
            basis_open=basis_open, daily_ok=True, volume_ratio=day_vol_ratio
        )

    session_open = float(today[0]["open"])
    min_gain = float(settings.gabozha_young1_min_gain_pct) / 100.0
    young1_vol_ratio = float(settings.gabozha_young1_volume_ratio)

    young1_idx = None
    for i in range(1, len(today) - 1):
        c = today[i]
        gain = (float(c["high"]) / session_open - 1.0) if session_open > 0 else 0.0
        prev_vols = [float(x["volume"]) for x in today[max(0, i - 4):i]]
        ref_vol = mean(prev_vols) if prev_vols else 0.0
        vr = (float(c["volume"]) / ref_vol) if ref_vol > 0 else 0.0
        local_peak = (
            float(c["high"]) >= float(today[i - 1]["high"])
            and float(c["high"]) >= float(today[i + 1]["high"])
        )
        bullish = float(c["close"]) > float(c["open"])
        if gain >= min_gain and vr >= young1_vol_ratio and local_peak and bullish:
            young1_idx = i
            break

    if young1_idx is None:
        return GabozhaSignal(
            False, "영1 형성 대기", current_price=current,
            basis_open=basis_open, daily_ok=True, volume_ratio=day_vol_ratio
        )

    y1 = today[young1_idx]
    young1_high = float(y1["high"])
    young1_vol = max(1.0, float(y1["volume"]))

    rebreak_idx = None
    for j in range(young1_idx + 1, len(today)):
        c = today[j]
        op = float(c["open"])
        cl = float(c["close"])
        # 꼬리만 넘긴 것은 불인정. 양봉 몸통이 전고를 아래→위로 관통해야 함.
        if cl > op and op <= young1_high < cl:
            rebreak_idx = j
            break

    pb_end = rebreak_idx if rebreak_idx is not None else len(today)
    pb = today[young1_idx + 1:pb_end]
    if not pb:
        return GabozhaSignal(
            False, "영1 이후 차 눌림 대기", current_price=current,
            basis_open=basis_open, daily_ok=True,
            young1_high=young1_high, volume_ratio=day_vol_ratio
        )

    pullback_low = min(float(x["low"]) for x in pb)
    depth_pct = (young1_high / pullback_low - 1.0) * 100.0 if pullback_low > 0 else 999.0
    pb_vol = mean(float(x["volume"]) for x in pb)
    volume_contract = pb_vol <= young1_vol * float(settings.gabozha_pullback_volume_max_ratio)
    depth_ok = (
        float(settings.gabozha_pullback_min_pct)
        <= depth_pct
        <= float(settings.gabozha_pullback_max_pct)
    )
    stop_distance_ok = pullback_low >= basis_open * (1.0 + float(settings.gabozha_stop_buffer_pct) / 100.0)
    pullback_valid = bool(volume_contract and depth_ok and stop_distance_ok)

    if rebreak_idx is not None and rebreak_idx == len(today) - 1 and pullback_valid:
        rb = today[rebreak_idx]
        rb_vol = float(rb["volume"])
        rebreak_volume_ok = rb_vol >= max(1.0, pb_vol) * float(settings.gabozha_rebreak_volume_ratio)
        if rebreak_volume_ok:
            return GabozhaSignal(
                True,
                f"가보자 전고 몸통돌파 진입 · 차 {depth_pct:.2f}% · 거래량 재증가",
                current_price=current,
                basis_open=basis_open,
                entry_kind="REBREAK",
                daily_ok=True,
                young1_high=young1_high,
                pullback_low=pullback_low,
                volume_ratio=day_vol_ratio,
            )
        return GabozhaSignal(
            False,
            "전고 몸통돌파 확인 · 거래량 재증가 대기",
            current_price=current,
            basis_open=basis_open,
            daily_ok=True,
            young1_high=young1_high,
            pullback_low=pullback_low,
            volume_ratio=day_vol_ratio,
        )

    if rebreak_idx is None and pullback_valid:
        latest = today[-1]
        prev = today[-2]
        bullish_turn = (
            float(latest["close"]) > float(latest["open"])
            and float(latest["close"]) >= float(prev["close"])
            and float(latest["close"]) < young1_high
        )
        if bullish_turn:
            return GabozhaSignal(
                True,
                f"가보자 차 눌림 진입 · 눌림 {depth_pct:.2f}% · 거래량 감소",
                current_price=current,
                basis_open=basis_open,
                entry_kind="PULLBACK",
                daily_ok=True,
                young1_high=young1_high,
                pullback_low=pullback_low,
                volume_ratio=day_vol_ratio,
            )

    if not depth_ok:
        reason = f"차 깊이 {depth_pct:.2f}% · 허용범위 이탈"
    elif not volume_contract:
        reason = "차 눌림 거래량 감소 미확인"
    elif not stop_distance_ok:
        reason = "차 저점이 기준봉 시가 손절선에 너무 가까움"
    else:
        reason = "차 반등 또는 전고 몸통돌파 대기"

    return GabozhaSignal(
        False, reason, current_price=current, basis_open=basis_open,
        daily_ok=True, young1_high=young1_high, pullback_low=pullback_low,
        volume_ratio=day_vol_ratio
    )
