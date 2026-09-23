from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CoreEntrySignal:
    active: bool
    name: str
    matched: list[str]
    missing: list[str]
    reason: str

    @property
    def status_text(self) -> str:
        if self.active:
            return f"활성 · {self.name} · " + " / ".join(self.matched)
        miss = " / ".join(self.missing) if self.missing else "조건 부족"
        return f"대기 · {self.name} · 미충족: {miss}"


def _last_valid(arr, idx=-1):
    if not isinstance(arr, list) or not arr:
        return None
    try:
        return arr[idx]
    except Exception:
        return None



def _common_market_path_signal(series: dict) -> CoreEntrySignal | None:
    path = series.get("core_path")
    if not isinstance(path, dict):
        return None

    stage = str(path.get("stage") or "대기")
    reason = str(path.get("reason") or "")
    quality = int(path.get("quality_score", 0) or 0)

    if bool(path.get("active")):
        matched = []
        if stage == "확정 돌파":
            matched = [
                "박스/전고점 저항 종가 돌파",
                f"거래량강도 {float(path.get('breakout_volume_ratio',0)):.2f}배",
                f"구조품질 {quality}/100",
            ]
        elif stage in ("확정 눌림", "눌림 확인 / 재상승 대기"):
            matched = [
                "선행 돌파 확인",
                "돌파가격 지지",
                f"눌림 거래량/돌파봉 {float(path.get('pullback_volume_ratio',1)):.2f}",
                f"구조품질 {quality}/100",
            ]
        elif stage == "확정 재돌파":
            matched = [
                "선행 돌파 확인",
                "저거래량 눌림 확인",
                f"재돌파 거래량강도 {float(path.get('rebreak_volume_ratio',0)):.2f}배",
                f"구조품질 {quality}/100",
            ]
        else:
            matched = [stage, f"구조품질 {quality}/100"]
        return CoreEntrySignal(True, f"공통 핵심경로 · {stage}", matched, [], reason)

    missing = []
    if stage == "공구리 형성 / 돌파 대기":
        missing.append("박스상단 종가돌파 + 거래량강도 300%")
    elif stage == "돌파 후 눌림 대기":
        missing.append("돌파선 지지 + 거래량이 확 죽는 눌림")
    elif stage == "돌파 실패 / 박스 복귀":
        missing.append("돌파기준선 재회복")
    else:
        missing.append("박스돌파→저거래량 눌림→재상승/재돌파 구조")
    return CoreEntrySignal(False, f"공통 핵심경로 · {stage}", [], missing, reason)


def _day_signal(analysis: Any, series: dict) -> CoreEntrySignal:
    candles = series.get("candles") or []
    e5 = series.get("ema5") or []
    e20 = series.get("ema20") or []
    if not candles:
        return CoreEntrySignal(False, "단타/오돌이 핵심", [], ["5분봉 데이터 없음"], "5분봉 데이터 없음")

    close = float(candles[-1]["close"])
    e5_now = _last_valid(e5)
    e5_prev = _last_valid(e5, -2)
    e20_now = _last_valid(e20)

    time_ok = bool(getattr(analysis, "in_time", False))
    baseline_ok = bool(getattr(analysis, "kijun", 0) and close >= float(getattr(analysis, "kijun", 0)))
    five_up = bool(e5_now is not None and e5_prev is not None and float(e5_now) > float(e5_prev) and close >= float(e5_now))
    support_ok = bool(getattr(analysis, "breakout", False) or getattr(analysis, "pullback_hold", False))
    volume_ok = float(getattr(analysis, "volume_ratio_5m", 0) or 0) >= 1.20
    e20_ok = bool(e20_now is not None and close >= float(e20_now) * 0.995)

    checks = [
        ("08:50~10:00 검색시간", time_ok),
        ("기준선26 위 유지", baseline_ok),
        ("EMA5 상승전환/상승유지", five_up),
        ("고점돌파 또는 기준선·EMA20 눌림지지", support_ok),
        ("5분 거래량 ≥ 최근20봉 1.2배", volume_ok),
        ("EMA20 위 유지", e20_ok),
    ]
    matched = [name for name, ok in checks if ok]
    missing = [name for name, ok in checks if not ok]
    active = all(ok for _, ok in checks)
    reason = " + ".join(matched) if active else " / ".join(missing)
    return CoreEntrySignal(active, "단타/오돌이 핵심", matched, missing, reason)


def _swing_signal(analysis: Any, series: dict) -> CoreEntrySignal:
    candles = series.get("candles") or []
    e112 = series.get("ema112") or []
    pullback = series.get("pullback") or {}
    if not candles:
        return CoreEntrySignal(False, "역매공파 핵심", [], ["일봉 데이터 없음"], "일봉 데이터 없음")

    # YTN 같은 기준봉-거래량감소 눌림은 역매공파와 별도 유효 셋업으로 인정.
    if bool(pullback.get("confirmed")):
        matched = [
            "강한 기준봉",
            "2~6봉 눌림",
            "기준봉 시가 위 유지",
            "거래량 피크 대비 감소",
        ]
        return CoreEntrySignal(
            True,
            "기준봉-거래량감소 눌림",
            matched,
            [],
            str(pullback.get("reason") or "기준봉 후 거래량 감소 눌림 확인"),
        )

    last = len(candles) - 1
    acc_ok = int(getattr(analysis, "accumulation_count", 0) or 0) >= 2
    reverse_ok = bool(getattr(analysis, "reverse_order", False))
    box_ok = bool(getattr(analysis, "box_found", False))
    blue_ok = bool(getattr(analysis, "blue_near", False))

    # 공개 복기에서 반복되는 '112일선 안착'을 수치화:
    # 최근 5봉 중 3봉 이상이 EMA112의 -1% 이내/위에서 종가 마감.
    accept112 = False
    if len(e112) >= 5:
        count = 0
        valid = 0
        for j in range(max(0, last - 4), last + 1):
            if j < len(e112) and e112[j] is not None:
                valid += 1
                if float(candles[j]["close"]) >= float(e112[j]) * 0.99:
                    count += 1
        accept112 = valid >= 3 and count >= 3

    checks = [
        ("장기 역배열 112<224<448", reverse_ok),
        ("매집확정 ≥2봉", acc_ok),
        ("공구리/박스 확인", box_ok),
        ("EMA112 안착", accept112),
        ("파란점선 ±설정근접", blue_ok),
    ]
    matched = [name for name, ok in checks if ok]
    missing = [name for name, ok in checks if not ok]
    active = all(ok for _, ok in checks)
    reason = " + ".join(matched) if active else " / ".join(missing)
    return CoreEntrySignal(active, "역매공파 핵심", matched, missing, reason)


def _long_signal(analysis: Any, series: dict) -> CoreEntrySignal:
    long_below = bool(getattr(analysis, "long_below", False))
    breakout = bool(getattr(analysis, "breakout", False))
    accepted = bool(getattr(analysis, "accepted", False))
    retest = bool(getattr(analysis, "retest", False))
    distance = float(getattr(analysis, "distance_pct", 999) or 999)
    distance_ok = 0.0 <= distance <= 8.0

    checks = [
        ("장기간 224EMA 아래", long_below),
        ("224EMA 상향돌파", breakout),
        ("224EMA 위 안착", accepted),
        ("224EMA 눌림/지지", retest),
        ("현재가 224EMA 위 0~8%", distance_ok),
    ]
    matched = [name for name, ok in checks if ok]
    missing = [name for name, ok in checks if not ok]
    active = all(ok for _, ok in checks)
    reason = " + ".join(matched) if active else " / ".join(missing)
    return CoreEntrySignal(active, "밥그릇3번 핵심", matched, missing, reason)


def evaluate_core_entry(analysis: Any, series: dict, strategy: str) -> CoreEntrySignal:
    # All named techniques sit underneath the same supply/breakout/pullback path.
    common = _common_market_path_signal(series)
    if common is not None and common.active:
        return common

    # Keep technique-specific context, but the displayed entry decision is the
    # common path so users can see exactly what is still missing.
    strategy = str(strategy or "").upper()
    if common is not None:
        return common
    if strategy == "DAY":
        return _day_signal(analysis, series)
    if strategy == "SWING":
        return _swing_signal(analysis, series)
    return _long_signal(analysis, series)
