from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List

from .swing import ema, normalize_candles, rolling_mean, rolling_std


def _date_key(raw) -> str:
    return "".join(ch for ch in str(raw or "") if ch.isdigit())[:8]


@dataclass
class GabojagoSignal:
    passed: bool
    reason: str
    entry_kind: str = ""
    current_price: float = 0.0
    basis_open: float = 0.0
    young1_high: float = 0.0
    daily_volume_ratio: float = 0.0
    daily_gap: bool = False
    daily_break: bool = False


def _daily_filter(daily_rows: List[dict], target_day: str, volume_ratio_min: float = 3.0):
    daily = normalize_candles(daily_rows or [])
    eligible = [c for c in daily if _date_key(c.get("date")) <= target_day]
    if len(eligible) < 7:
        return False, "일봉 데이터 부족", 0.0, 0.0, False, False

    basis = eligible[-1]
    if _date_key(basis.get("date")) != target_day:
        return False, "당일 일봉 기준봉 미확인", 0.0, 0.0, False, False

    prev = eligible[:-1]
    prev5 = prev[-5:]
    prev5_high = max(c["high"] for c in prev5)
    gap = basis["open"] > prev5_high

    prev_volume = float(prev[-1]["volume"] or 0.0)
    vol_ratio = float(basis["volume"] or 0.0) / prev_volume if prev_volume > 0 else 0.0
    volume_ok = vol_ratio >= float(volume_ratio_min)

    closes = [c["close"] for c in eligible]
    e112 = ema(closes, 112)
    e224 = ema(closes, 224)
    e448 = ema(closes, 448)
    levels = []
    for label, arr in (("EMA112", e112), ("EMA224", e224), ("EMA448", e448)):
        if arr and arr[-1] is not None:
            levels.append((label, float(arr[-1])))

    ma40 = rolling_mean(closes, 40)
    sd40 = rolling_std(closes, 40)
    if ma40 and sd40 and ma40[-1] is not None and sd40[-1] is not None:
        levels.append(("BB40/2.2", float(ma40[-1]) + 2.2 * float(sd40[-1])))

    broken = []
    prev_close = float(prev[-1]["close"])
    for label, level in levels:
        # 갭 또는 당일 몸통/종가로 장기 저항을 실제 위로 올려놓은 경우 인정.
        if basis["close"] > level and (basis["open"] <= level or prev_close <= level):
            broken.append(label)

    break_ok = bool(broken)
    ok = bool(gap and volume_ok and break_ok)
    reason = (
        f"일봉 {'갭OK' if gap else '갭X'} · 거래량 {vol_ratio:.2f}배 · "
        + (f"{'/'.join(broken)} 돌파" if broken else "장기이평/BB40·2.2 돌파X")
    )
    return ok, reason, float(basis["open"]), vol_ratio, gap, break_ok


def evaluate_gabojago(
    minute_rows: List[dict],
    daily_rows: List[dict],
    *,
    now: datetime | None = None,
    scan_start: str = "08:50",
    scan_end: str = "10:00",
    daily_volume_ratio_min: float = 3.0,
    min_stop_gap_pct: float = 0.5,
) -> GabojagoSignal:
    """사용자 전용 '가보자' 단타 진입 판정.

    1) 일봉: 이전 5봉 위 갭 + 당일 거래량 300%+ + 장기이평 또는 BB40/2.2 돌파
    2) 5분봉: 영1 이후 거래량 감소 '차' 눌림 또는
       차 이후 영1 전고를 양봉 몸통으로 재돌파할 때만 진입
    3) 손절 기준은 일봉 기준봉 시가. 차 저점은 손절선과 거리를 둬야 한다.
    """
    candles = normalize_candles(minute_rows or [])
    if len(candles) < 4:
        return GabojagoSignal(False, "5분봉 데이터 부족")

    target_day = _date_key(candles[-1].get("date"))
    today = [c for c in candles if _date_key(c.get("date")) == target_day]
    if len(today) < 3:
        return GabojagoSignal(False, "당일 5분봉 3개 미만")

    now = now or datetime.now()
    hm = now.strftime("%H:%M")
    if not (scan_start <= hm <= scan_end):
        return GabojagoSignal(False, f"검색시간 외 {hm}")

    daily_ok, daily_reason, basis_open, day_vol_ratio, gap, break_ok = _daily_filter(
        daily_rows, target_day, daily_volume_ratio_min
    )
    current = float(today[-1]["close"])
    if not daily_ok:
        return GabojagoSignal(
            False, daily_reason, current_price=current, basis_open=basis_open,
            daily_volume_ratio=day_vol_ratio, daily_gap=gap, daily_break=break_ok,
        )

    if current <= basis_open:
        return GabojagoSignal(
            False, "기준봉 시가 이탈 · 진입 금지", current_price=current, basis_open=basis_open,
            daily_volume_ratio=day_vol_ratio, daily_gap=gap, daily_break=break_ok,
        )

    peak_idx = 0
    pullback_idx = None
    for i in range(1, len(today)):
        if today[i - 1]["high"] > today[peak_idx]["high"]:
            peak_idx = i - 1
        peak = today[peak_idx]
        bar = today[i]
        retreat = (bar["close"] < today[i - 1]["close"]) or (bar["low"] < today[i - 1]["low"])
        volume_down = float(bar["volume"]) < float(peak["volume"])
        if i > peak_idx and retreat and volume_down:
            pullback_idx = i
            break

    if pullback_idx is None:
        return GabojagoSignal(
            False, f"{daily_reason} · 영1 이후 차 대기",
            current_price=current, basis_open=basis_open, daily_volume_ratio=day_vol_ratio,
            daily_gap=gap, daily_break=break_ok,
        )

    young1 = today[peak_idx]
    young1_high = float(young1["high"])
    pull = today[pullback_idx]
    stop_gap_pct = ((float(pull["low"]) / basis_open) - 1.0) * 100.0 if basis_open > 0 else -999.0
    safe_pullback = stop_gap_pct >= float(min_stop_gap_pct)

    if not safe_pullback:
        return GabojagoSignal(
            False, f"차가 기준봉 시가에 너무 근접/이탈 · 거리 {stop_gap_pct:.2f}%",
            current_price=current, basis_open=basis_open, young1_high=young1_high,
            daily_volume_ratio=day_vol_ratio, daily_gap=gap, daily_break=break_ok,
        )

    last_idx = len(today) - 1
    # 눌림 자체가 현재 봉이면 '차 진입'. 거래량 감소 + 손절선과 거리 확보가 필수.
    if last_idx == pullback_idx:
        return GabojagoSignal(
            True,
            f"가보자 차 진입 · 거래량 감소 · 기준봉 시가와 {stop_gap_pct:.2f}% 거리",
            entry_kind="PULLBACK", current_price=current, basis_open=basis_open,
            young1_high=young1_high, daily_volume_ratio=day_vol_ratio,
            daily_gap=gap, daily_break=break_ok,
        )

    last = today[-1]
    body_cross = (
        float(last["close"]) > float(last["open"])
        and float(last["open"]) <= young1_high < float(last["close"])
    )
    rebreak_volume = float(last["volume"]) > float(pull["volume"])
    if pullback_idx < last_idx and body_cross and rebreak_volume:
        return GabojagoSignal(
            True,
            f"가보자 전고 몸통돌파 · 영1 전고 {young1_high:,.0f} · 재돌파 거래량 증가",
            entry_kind="BODY_REBREAK", current_price=current, basis_open=basis_open,
            young1_high=young1_high, daily_volume_ratio=day_vol_ratio,
            daily_gap=gap, daily_break=break_ok,
        )

    return GabojagoSignal(
        False,
        f"{daily_reason} · 차 확인 · 전고 몸통돌파 대기",
        current_price=current, basis_open=basis_open, young1_high=young1_high,
        daily_volume_ratio=day_vol_ratio, daily_gap=gap, daily_break=break_ok,
    )
