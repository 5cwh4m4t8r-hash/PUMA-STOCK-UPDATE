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
    confidence: str = "낮음"

    def summary(self) -> str:
        if self.probability is None:
            return f"통계부족({self.samples}건) · 신뢰도 {self.confidence} · {self.verdict}"
        return (
            f"{self.probability*100:.0f}%"
            f" ({self.wins}/{self.samples}건, 95% {self.lower95*100:.0f}~{self.upper95*100:.0f}%)"
            f" · 신뢰도 {self.confidence} · {self.verdict}"
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


def _confidence(samples: int, lo: float | None, hi: float | None) -> str:
    if samples < 10 or lo is None or hi is None:
        return "낮음"
    width = hi - lo
    if samples >= 30 and width <= 0.30:
        return "높음"
    if samples >= 15 and width <= 0.42:
        return "보통"
    return "낮음"


def estimate_from_flags(
    candles: List[dict],
    flags: List[bool],
    *,
    horizon_bars: int,
    tp_pct: float,
    sl_pct: float,
    min_samples: int = 10,
    current_score: int = 0,
    current_active: bool = False,
    core_signal_name: str = "핵심 진입 신호",
    core_signal_reason: str = "",
) -> ProbabilityEstimate:
    n = min(len(candles), len(flags))
    horizon = max(1, int(horizon_bars))
    tp = max(0.1, float(tp_pct))
    sl = max(0.1, abs(float(sl_pct)))

    wins = losses = unresolved = 0
    last_used = -10**9
    for i in range(n):
        if not flags[i]:
            continue
        if i - last_used < max(2, horizon // 4):
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
            verdict="판단 유보", reason="완료된 동일단계 과거 사례가 없습니다.", confidence="낮음",
        )

    p = wins / resolved
    lo, hi = _wilson(wins, resolved)
    conf = _confidence(resolved, lo, hi)

    if not current_active:
        verdict = "진입 대기"
        reason = f"{core_signal_name} 미충족"
        if core_signal_reason:
            reason += f" · {core_signal_reason}"
    elif resolved < min_samples:
        verdict = "신호 활성 / 통계 부족"
        reason = f"현재 신호는 확정됐지만 동일단계 완료 표본이 {resolved}건뿐입니다."
    elif p >= 0.65 and lo >= 0.50 and current_score >= 60:
        verdict = "진입 우위 높음"
        reason = f"{core_signal_name} 확정 + 동일단계 과거 통계가 기준을 통과했습니다."
    elif p >= 0.58 and lo >= 0.40 and current_score >= 55:
        verdict = "진입 우위 있음"
        reason = f"{core_signal_name} 확정 + 동일단계 통계가 우위이나 신뢰구간은 더 넓습니다."
    else:
        verdict = "진입 보류"
        reason = f"{core_signal_name}은 확정됐지만 동일단계 과거 통계 우위가 충분하지 않습니다."

    return ProbabilityEstimate(
        probability=p, samples=resolved, wins=wins, losses=losses, unresolved=unresolved,
        lower95=lo, upper95=hi, horizon_bars=horizon, tp_pct=tp, sl_pct=sl,
        verdict=verdict, reason=reason, confidence=conf,
    )


def strategy_flags(series: dict, strategy: str) -> List[bool]:
    """Use the SAME stage as the current confirmed setup for probability."""
    candles = series.get("candles") or []
    n = len(candles)
    path = series.get("core_path") or {}
    stage_key = str(path.get("stage_key") or "")

    path_breakout = series.get("path_breakout", [False]*n)
    path_pullback = series.get("path_pullback", [False]*n)
    path_rebreakout = series.get("path_rebreakout", [False]*n)

    if stage_key == "BREAKOUT":
        return list(path_breakout)[:n]
    if stage_key == "PULLBACK":
        return list(path_pullback)[:n]
    if stage_key == "REBREAKOUT":
        return list(path_rebreakout)[:n]

    # No confirmed current stage: do not mix unrelated technique events to create a misleading probability.
    return [False] * n
