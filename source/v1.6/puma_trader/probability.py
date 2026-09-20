from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import List


@dataclass
class ProbabilityEstimate:
    probability: float | None
    samples: int
    wins: int
    losses: int
    unresolved: int
    lower95: float | None
    upper95: float | None
    horizon_bars: int
    tp_pct: float
    sl_pct: float
    verdict: str
    reason: str

    def summary(self) -> str:
        if self.probability is None:
            return f"통계부족({self.samples}건) · {self.verdict}"
        return (
            f"{self.probability*100:.0f}%"
            f" ({self.wins}/{self.samples}건, 95% {self.lower95*100:.0f}~{self.upper95*100:.0f}%)"
            f" · {self.verdict}"
        )


def _wilson(wins: int, total: int) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 1.0)
    z = 1.96
    p = wins / total
    den = 1 + z*z/total
    center = (p + z*z/(2*total)) / den
    margin = z * sqrt((p*(1-p)/total) + z*z/(4*total*total)) / den
    return max(0.0, center-margin), min(1.0, center+margin)


def estimate_from_flags(
    candles: List[dict],
    flags: List[bool],
    *,
    horizon_bars: int,
    tp_pct: float,
    sl_pct: float,
    min_samples: int = 8,
    current_score: int = 0,
    current_active: bool = False,
) -> ProbabilityEstimate:
    """Empirical TP-before-SL rate on past matching signals.

    A same-bar TP/SL collision is treated conservatively as a loss because
    intrabar sequence is unknown. Unresolved cases are reported separately.
    """
    n = min(len(candles), len(flags))
    horizon = max(1, int(horizon_bars))
    tp = max(0.1, float(tp_pct))
    sl = max(0.1, abs(float(sl_pct)))

    wins = losses = unresolved = 0
    last_used = -10**9

    for i in range(n):
        if not flags[i]:
            continue
        if i - last_used < max(1, horizon // 3):
            continue
        if i + horizon >= n:
            continue

        entry = float(candles[i]["close"])
        if entry <= 0:
            continue
        target = entry * (1 + tp/100.0)
        stop = entry * (1 - sl/100.0)
        outcome = None
        for j in range(i + 1, min(n, i + horizon + 1)):
            hi = float(candles[j]["high"])
            lo = float(candles[j]["low"])
            hit_tp = hi >= target
            hit_sl = lo <= stop
            if hit_tp and hit_sl:
                outcome = "loss"  # conservative when sequence is unknowable
                break
            if hit_sl:
                outcome = "loss"
                break
            if hit_tp:
                outcome = "win"
                break
        if outcome == "win":
            wins += 1
        elif outcome == "loss":
            losses += 1
        else:
            unresolved += 1
        last_used = i

    resolved = wins + losses
    if resolved <= 0:
        return ProbabilityEstimate(
            probability=None, samples=0, wins=0, losses=0, unresolved=unresolved,
            lower95=None, upper95=None, horizon_bars=horizon, tp_pct=tp, sl_pct=sl,
            verdict="판단 유보",
            reason="동일 조건의 과거 완료 사례가 없습니다.",
        )

    p = wins / resolved
    lo, hi = _wilson(wins, resolved)

    if resolved < min_samples:
        verdict = "판단 유보"
        reason = f"표본 {resolved}건으로 너무 적습니다."
    elif not current_active:
        verdict = "현재 진입 신호 아님"
        reason = "과거 통계가 있어도 현재 핵심 신호가 활성화되지 않았습니다."
    elif current_score >= 75 and p >= 0.65 and lo >= 0.45:
        verdict = "진입 적합도 높음"
        reason = "현재 점수와 과거 적중률이 함께 높은 구간입니다."
    elif current_score >= 60 and p >= 0.55:
        verdict = "조건부 진입 검토"
        reason = "우위는 있으나 신호 강도/통계 신뢰도가 충분히 높지는 않습니다."
    else:
        verdict = "관망 우세"
        reason = "현재 점수 또는 과거 적중률이 진입 기준에 못 미칩니다."

    return ProbabilityEstimate(
        probability=p, samples=resolved, wins=wins, losses=losses, unresolved=unresolved,
        lower95=lo, upper95=hi, horizon_bars=horizon, tp_pct=tp, sl_pct=sl,
        verdict=verdict, reason=reason,
    )


def strategy_flags(series: dict, strategy: str) -> List[bool]:
    candles = series.get("candles") or []
    n = len(candles)
    pink = series.get("signal_pink", [False]*n)
    blue = series.get("signal_blue", [False]*n)
    red = series.get("signal_red", [False]*n)
    wm = series.get("watermelon_stage", [0]*n)

    out = [False] * n
    for i in range(n):
        any_arrow = any(
            i < len(arr) and bool(arr[i])
            for arr in (pink, blue, red)
            if isinstance(arr, list)
        )
        stage = int(wm[i]) if isinstance(wm, list) and i < len(wm) else 0
        if strategy == "DAY":
            out[i] = any_arrow or stage >= 2
        elif strategy == "SWING":
            out[i] = stage >= 2 or (i < len(pink) and pink[i]) or (i < len(red) and red[i])
        else:
            out[i] = stage >= 3
    return out
