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
    core_signal_name: str = "핵심 진입 신호",
    core_signal_reason: str = "",
) -> ProbabilityEstimate:
    """Empirical TP-before-SL rate on past matching signals.

    The probability is historical frequency only. It is not a guarantee.
    A same-bar TP/SL collision is conservatively counted as a loss because
    intrabar sequence is unknown.
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
                outcome = "loss"
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
            verdict="통계 판단 유보",
            reason="완료된 과거 유사 사례가 없습니다.",
        )

    p = wins / resolved
    lo, hi = _wilson(wins, resolved)

    if not current_active:
        verdict = "진입 대기"
        reason = f"{core_signal_name} 미충족"
        if core_signal_reason:
            reason += f" · {core_signal_reason}"
    elif resolved < min_samples:
        verdict = "핵심신호 활성 / 통계 부족"
        reason = f"{core_signal_name}은 활성이나 과거 완료 표본이 {resolved}건뿐입니다."
    elif current_score >= 75 and p >= 0.65 and lo >= 0.45:
        verdict = "진입 적합도 높음"
        reason = f"{core_signal_name} 활성 + 현재 점수와 과거 적중률이 함께 높은 구간입니다."
    elif current_score >= 60 and p >= 0.55:
        verdict = "조건부 진입 검토"
        reason = f"{core_signal_name}은 활성이나 통계 우위 또는 신호 강도가 중간 수준입니다."
    else:
        verdict = "신호 활성 / 보수적 관찰"
        reason = f"{core_signal_name}은 활성이나 현재 점수 또는 과거 통계 우위가 충분하지 않습니다."

    return ProbabilityEstimate(
        probability=p, samples=resolved, wins=wins, losses=losses, unresolved=unresolved,
        lower95=lo, upper95=hi, horizon_bars=horizon, tp_pct=tp, sl_pct=sl,
        verdict=verdict, reason=reason,
    )


def strategy_flags(series: dict, strategy: str) -> List[bool]:
    """Sparse historical proxy flags used only for empirical statistics.

    These are not the current-entry decision. Current entry uses entry_signal.py.
    """
    candles = series.get("candles") or []
    n = len(candles)
    pink = series.get("signal_pink", [False]*n)
    blue = series.get("signal_blue", [False]*n)
    red = series.get("signal_red", [False]*n)
    wm_confirmed = series.get("watermelon_confirmed", [False]*n)

    out = [False] * n
    for i in range(n):
        any_arrow = any(
            i < len(arr) and bool(arr[i])
            for arr in (pink, blue, red)
            if isinstance(arr, list)
        )
        wm = bool(i < len(wm_confirmed) and wm_confirmed[i])
        if strategy == "DAY":
            out[i] = any_arrow
        elif strategy == "SWING":
            out[i] = wm or (i < len(pink) and bool(pink[i])) or (i < len(red) and bool(red[i]))
        else:
            out[i] = wm
    return out
