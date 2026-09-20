from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .swing import ema, normalize_candles


@dataclass
class BowlSettings:
    ema_period: int = 224
    below_lookback: int = 100
    min_below_closes: int = 70
    breakout_buffer_pct: float = 0.3
    acceptance_window: int = 12
    acceptance_min_closes: int = 6
    acceptance_tolerance_pct: float = 1.5
    retest_tolerance_pct: float = 2.5
    max_entry_distance_pct: float = 8.0


@dataclass
class BowlAnalysis:
    stage: str
    score: int
    long_below: bool
    below_count: int
    breakout: bool
    breakout_index: int
    accepted: bool
    retest: bool
    ema_value: float
    distance_pct: float
    details: Dict[str, str]


def analyze_bowl(candles_raw: List[dict], settings: BowlSettings | None = None) -> tuple[BowlAnalysis, dict]:
    """PUMA 밥그릇 3번 베타.

    원본 비공개 수식을 복제하지 않고 사용자가 설명한 장기 자리 개념을 수치화한다.
    핵심은 장기간 224EMA 아래 -> 224EMA 돌파 -> 위에서 안착 -> 눌림/지지 확인이다.
    """
    settings = settings or BowlSettings()
    candles = normalize_candles(candles_raw)
    if len(candles) < settings.ema_period + 20:
        raise ValueError(f'밥그릇3번 분석에는 최소 {settings.ema_period + 20}개 이상의 일봉이 필요합니다.')

    closes = [c['close'] for c in candles]
    e = ema(closes, settings.ema_period)
    n = len(candles)
    last = n - 1
    last_ema = e[last] or 0.0
    current = closes[last]
    distance = ((current / last_ema - 1) * 100.0) if last_ema else 999.0

    # 최근 구간에서 '장기간 아래에 있다가 위로 올라온 첫 돌파'를 찾는다.
    search_start = max(settings.ema_period, n - 180)
    breakout_idx = -1
    below_count_at_break = 0
    for i in range(search_start, n):
        if e[i] is None or e[i - 1] is None:
            continue
        prior_start = max(settings.ema_period - 1, i - settings.below_lookback)
        prior = [j for j in range(prior_start, i) if e[j] is not None]
        below_count = sum(1 for j in prior if closes[j] < e[j])
        enough_history = len(prior) >= min(settings.min_below_closes, settings.below_lookback)
        crossed = closes[i - 1] <= e[i - 1] and closes[i] > e[i] * (1 + settings.breakout_buffer_pct / 100.0)
        if enough_history and below_count >= settings.min_below_closes and crossed:
            breakout_idx = i
            below_count_at_break = below_count

    long_below = breakout_idx >= 0
    accepted = False
    retest = False
    if breakout_idx >= 0:
        after = range(breakout_idx, min(n, breakout_idx + settings.acceptance_window))
        accepted_count = sum(
            1 for j in after
            if e[j] is not None and closes[j] >= e[j] * (1 - settings.acceptance_tolerance_pct / 100.0)
        )
        accepted = accepted_count >= settings.acceptance_min_closes

        # 돌파 뒤 224EMA 부근으로 눌렸다가 종가가 다시 위에서 끝나는지 확인.
        tail_start = max(breakout_idx, n - 30)
        for j in range(tail_start, n):
            if e[j] is None:
                continue
            touched = candles[j]['low'] <= e[j] * (1 + settings.retest_tolerance_pct / 100.0)
            held = closes[j] >= e[j] * (1 - settings.acceptance_tolerance_pct / 100.0)
            if touched and held:
                retest = True

    score = 0
    stage = '장기 224EMA 아래 구간 확인'
    if long_below:
        score += 35
        stage = '224EMA 돌파 후 안착 확인'
    if accepted:
        score += 35
        stage = '3번 자리 눌림/지지 확인'
    if retest:
        score += 20
        stage = '최종 신호(수박/화살표) 수식 대기'
    if last_ema and 0 <= distance <= settings.max_entry_distance_pct:
        score += 10

    reasons = [
        (f'224EMA 아래 {below_count_at_break}봉' if long_below else '장기 아래구간 미확인'),
        ('224EMA 돌파 확인' if breakout_idx >= 0 else '224EMA 돌파 대기'),
        ('위 안착 확인' if accepted else '위 안착 대기'),
        ('눌림 지지 확인' if retest else '눌림 지지 대기'),
    ]

    details = {
        '간단 이유': ' · '.join(reasons),
        '장기 224EMA 아래': f'{below_count_at_break}봉 확인' if long_below else '미확인',
        '224EMA 돌파': '확인' if breakout_idx >= 0 else '대기',
        '224EMA 위 안착': '확인' if accepted else '대기',
        '눌림/지지': '확인' if retest else '대기',
        '224EMA 거리': f'{last_ema:,.0f} / {distance:+.2f}%' if last_ema else '데이터 부족',
        '수박/화살표': '사용자 수식 입력 대기',
    }

    result = BowlAnalysis(
        stage=stage,
        score=min(score, 100),
        long_below=long_below,
        below_count=below_count_at_break,
        breakout=breakout_idx >= 0,
        breakout_index=breakout_idx,
        accepted=accepted,
        retest=retest,
        ema_value=last_ema,
        distance_pct=distance,
        details=details,
    )
    return result, {'candles': candles, 'ema224': e}
