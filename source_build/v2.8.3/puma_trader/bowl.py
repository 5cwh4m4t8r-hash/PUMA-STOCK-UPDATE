from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .swing import ema, normalize_candles
from .signals import build_arrow_signals, latest_signal_reason
from .watermelon_proxy import build_puma_watermelon
from .swing_reference import evaluate_swing_reference_profiles


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

    # v2.9.13: photo-A / public bowl-stage context.
    prebreak_near_224_pct: float = 2.0
    base_window: int = 60
    base_max_range_pct: float = 35.0
    base_max_directionality: float = 0.55
    reclaim_112_lookback: int = 60


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


def _crossed_above_recent(closes: list[float], line, lookback: int) -> bool:
    start = max(1, len(closes) - max(1, int(lookback)))
    for i in range(start, len(closes)):
        if i >= len(line) or line[i] is None or line[i - 1] is None:
            continue
        if closes[i - 1] <= float(line[i - 1]) and closes[i] > float(line[i]):
            return True
    return False


def is_bowl3_overextended(distance_pct: float, settings: BowlSettings | None = None) -> bool:
    settings = settings or BowlSettings()
    return bool(float(distance_pct) > float(settings.max_entry_distance_pct))


def is_bowl3_confirmed_state(
    breakout_index: int,
    retest: bool,
    support_alive: bool,
    extended_above_224: bool,
) -> bool:
    return bool(
        int(breakout_index) >= 0
        and bool(retest)
        and bool(support_alive)
        and not bool(extended_above_224)
    )


def _historical_bowl3_markers(
    candles: list[dict],
    e112,
    e224,
    settings: BowlSettings,
) -> list[dict]:
    """Display-only historical Bowl-3-like pullback locations.

    This never changes the current Bowl score/classification.  It scans every
    loaded daily bar for the same structural sequence used by the live marker:
    long stay below EMA224 -> body close breakout -> later pullback holding
    EMA224 or, at minimum, EMA112.  One marker is kept per structural cycle so
    adding newer candles does not make older confirmed-looking locations vanish.
    """
    n = len(candles)
    if n <= int(settings.ema_period):
        return []

    closes = [float(c["close"]) for c in candles]
    markers: list[dict] = []
    cooldown_until = -1

    for i in range(max(1, int(settings.ema_period)), n):
        if i <= cooldown_until:
            continue
        if i >= len(e224) or e224[i] is None or e224[i - 1] is None:
            continue

        prior_start = max(int(settings.ema_period) - 1, i - int(settings.below_lookback))
        prior = [j for j in range(prior_start, i) if e224[j] is not None]
        enough = len(prior) >= min(int(settings.min_below_closes), int(settings.below_lookback))
        below_count = sum(1 for j in prior if closes[j] < float(e224[j]))
        crossed = (
            closes[i - 1] <= float(e224[i - 1])
            and closes[i] > float(e224[i]) * (1 + float(settings.breakout_buffer_pct) / 100.0)
        )
        if not (enough and below_count >= int(settings.min_below_closes) and crossed):
            continue

        # A past Bowl-3-like position is the first real pullback after the
        # breakout that holds EMA224, or at minimum EMA112.
        retest_limit = min(n, i + 36)
        found_idx = -1
        found_line = 0
        for j in range(i + 1, retest_limit):
            low = float(candles[j]["low"])
            close = closes[j]

            held224 = False
            if j < len(e224) and e224[j] is not None:
                line224 = float(e224[j])
                held224 = (
                    low <= line224 * (1 + float(settings.retest_tolerance_pct) / 100.0)
                    and close >= line224 * (1 - float(settings.acceptance_tolerance_pct) / 100.0)
                )

            held112 = False
            if j < len(e112) and e112[j] is not None:
                line112 = float(e112[j])
                held112 = (
                    low <= line112 * (1 + float(settings.retest_tolerance_pct) / 100.0)
                    and close >= line112 * (1 - float(settings.acceptance_tolerance_pct) / 100.0)
                )

            if held224 or held112:
                found_idx = j
                found_line = 224 if held224 else 112
                break

        if found_idx >= 0:
            markers.append({
                "index": found_idx,
                "kind": "historical_core",
                "label": "밥3",
                "stage": f"과거 유사 · {found_line}EMA 눌림/안착",
                "breakout_index": i,
                "retest_line": found_line,
            })
            # Avoid several tags for repeated recrosses inside the same bowl.
            cooldown_until = found_idx + 20

    return markers


def _directionality(values: list[float]) -> float:
    if len(values) < 3:
        return 1.0
    travel = sum(abs(float(values[i]) - float(values[i - 1])) for i in range(1, len(values)))
    if travel <= 0:
        return 0.0
    return abs(float(values[-1]) - float(values[0])) / travel


def _base_context(candles: list[dict], end_idx: int, settings: BowlSettings) -> tuple[bool, float, float]:
    end_idx = max(0, min(len(candles) - 1, int(end_idx)))
    start = max(0, end_idx - max(20, int(settings.base_window)) + 1)
    seg = candles[start:end_idx + 1]
    if len(seg) < 20:
        return False, 999.0, 1.0
    lo = min(float(c["low"]) for c in seg)
    hi = max(float(c["high"]) for c in seg)
    mid = (hi + lo) / 2.0 if hi + lo else 0.0
    width = (hi - lo) / mid * 100.0 if mid > 0 else 999.0
    direction = _directionality([float(c["close"]) for c in seg])
    ok = bool(width <= float(settings.base_max_range_pct) and direction <= float(settings.base_max_directionality))
    return ok, width, direction


def analyze_bowl(candles_raw: List[dict], settings: BowlSettings | None = None) -> tuple[BowlAnalysis, dict]:
    """PUMA 밥그릇 3번 자리 analyzer.

    Transparent model used by the program:
      1) long decline / long stay below EMA224
      2) bottom/base with reverse MA context and evidence of strong volume
      3) price approaches then breaks EMA224, holds above it, and ideally retests

    The user's first photographed swing searcher is treated as a pre-3 filter:
    EMA224 within 2% + 112-bar record volume inside 20 bars + 60<112<224.
    It is not treated as a proprietary formula clone.
    """
    settings = settings or BowlSettings()
    candles = normalize_candles(candles_raw)
    if len(candles) < settings.ema_period + 20:
        raise ValueError(f'밥그릇3번 분석에는 최소 {settings.ema_period + 20}개 이상의 일봉이 필요합니다.')

    closes = [float(c['close']) for c in candles]
    e60 = ema(closes, 60)
    e112 = ema(closes, 112)
    e224 = ema(closes, settings.ema_period)
    n = len(candles)
    last = n - 1
    last_ema = float(e224[last] or 0.0)
    current = closes[last]
    distance = ((current / last_ema - 1) * 100.0) if last_ema else 999.0

    reference = evaluate_swing_reference_profiles(candles)
    ref_a = reference.get('A') or {}
    a_features = ref_a.get('features') or {}
    near224 = bool(a_features.get('near224'))
    record112 = bool(a_features.get('record112_20'))
    reverse_now = bool(a_features.get('reverse_60_112_224'))

    # Current bowl-1/2 context: how long price has stayed below the 224 EMA.
    current_prior_start = max(settings.ema_period - 1, n - int(settings.below_lookback))
    current_prior = [j for j in range(current_prior_start, n) if e224[j] is not None]
    current_below_count = sum(1 for j in current_prior if closes[j] < float(e224[j]))
    long_below_context = bool(
        len(current_prior) >= min(int(settings.min_below_closes), int(settings.below_lookback))
        and current_below_count >= int(settings.min_below_closes)
    )

    # Find the latest genuine 224 break after a long below-224 period.
    search_start = max(settings.ema_period, n - 200)
    breakout_idx = -1
    below_count_at_break = 0
    breakout_volume_ratio = 0.0
    for i in range(search_start, n):
        if e224[i] is None or e224[i - 1] is None:
            continue
        prior_start = max(settings.ema_period - 1, i - int(settings.below_lookback))
        prior = [j for j in range(prior_start, i) if e224[j] is not None]
        below_count = sum(1 for j in prior if closes[j] < float(e224[j]))
        enough = len(prior) >= min(int(settings.min_below_closes), int(settings.below_lookback))
        crossed = (
            closes[i - 1] <= float(e224[i - 1])
            and closes[i] > float(e224[i]) * (1 + float(settings.breakout_buffer_pct) / 100.0)
        )
        if enough and below_count >= int(settings.min_below_closes) and crossed:
            breakout_idx = i
            below_count_at_break = below_count
            prior_vol = [
                float(candles[j]['volume'])
                for j in range(max(0, i - 20), i)
                if float(candles[j]['volume']) > 0
            ]
            avg = sum(prior_vol) / len(prior_vol) if prior_vol else 0.0
            breakout_volume_ratio = float(candles[i]['volume']) / avg if avg > 0 else 0.0

    long_below = bool(long_below_context or breakout_idx >= 0)

    # Publicly described / photo-supported stage-2 context.
    base_end = breakout_idx - 1 if breakout_idx > 0 else last
    base_ok, base_width, base_direction = _base_context(candles, base_end, settings)
    reclaimed112 = _crossed_above_recent(closes, e112, settings.reclaim_112_lookback)

    # If a breakout already happened, use the historical pre-break below count;
    # if it has not, Photo A can identify the '3번 직전' preparation zone.
    stage2_ready = bool(
        long_below_context
        and near224
        and record112
        and (reverse_now or reclaimed112)
    )

    accepted = False
    accepted_count = 0
    accepted_idx = -1
    retest = False
    retest_idx = -1
    retest_line = 0
    support_alive = False
    if breakout_idx >= 0:
        after = range(breakout_idx, min(n, breakout_idx + int(settings.acceptance_window)))
        running_accepts = 0
        for j in after:
            if (
                e224[j] is not None
                and closes[j] >= float(e224[j]) * (1 - float(settings.acceptance_tolerance_pct) / 100.0)
            ):
                running_accepts += 1
                if accepted_idx < 0 and running_accepts >= int(settings.acceptance_min_closes):
                    accepted_idx = j
        accepted_count = running_accepts
        accepted = accepted_idx >= 0

        # 밥3 핵심은 '224 돌파 그 자체'가 아니라 이후 눌림이 224 또는 최소 112에서
        # 실제로 지지/안착되는 자리다. 돌파봉 자체는 눌림으로 인정하지 않는다.
        tail_start = max(breakout_idx + 1, n - 35)
        for j in range(tail_start, n):
            low = float(candles[j]['low'])
            close = closes[j]

            held224 = False
            if e224[j] is not None:
                line224 = float(e224[j])
                held224 = (
                    low <= line224 * (1 + float(settings.retest_tolerance_pct) / 100.0)
                    and close >= line224 * (1 - float(settings.acceptance_tolerance_pct) / 100.0)
                )

            held112 = False
            if e112[j] is not None:
                line112 = float(e112[j])
                held112 = (
                    low <= line112 * (1 + float(settings.retest_tolerance_pct) / 100.0)
                    and close >= line112 * (1 - float(settings.acceptance_tolerance_pct) / 100.0)
                )

            if held224 or held112:
                retest = True
                retest_idx = j
                retest_line = 224 if held224 else 112

        if retest:
            current_support = (
                float(e224[last]) if retest_line == 224 and e224[last] is not None
                else float(e112[last]) if retest_line == 112 and e112[last] is not None
                else 0.0
            )
            support_alive = bool(
                current_support > 0
                and current >= current_support * (1 - float(settings.acceptance_tolerance_pct) / 100.0)
            )

    # Score is a progression score, not a probability.
    score = 0
    if long_below:
        score += 15
    if base_ok:
        score += 10
    if reverse_now:
        score += 10
    if reclaimed112:
        score += 10
    if record112:
        score += 15
    if near224:
        score += 15

    if breakout_idx >= 0:
        score += 20
        if breakout_volume_ratio >= 1.5:
            score += 5
    if accepted:
        score += 10
    if retest:
        score += 10
    if last_ema and 0 <= distance <= float(settings.max_entry_distance_pct):
        score += 5

    # Prevent a generic old downtrend from being classified as a Bowl-3
    # candidate when neither the photo-A prebreak setup nor the 224 breakout exists.
    if not stage2_ready and breakout_idx < 0:
        score = min(score, 49)

    # 224 위로 이미 크게 이격되어 상승한 종목은 '현재 밥3 자리'가 아니다.
    # 과거 구조는 차트에 남기되 현재 중장기 후보에서는 제외한다.
    extended_above_224 = bool(last_ema > 0 and is_bowl3_overextended(distance, settings))
    bowl3_confirmed = is_bowl3_confirmed_state(
        breakout_idx,
        retest,
        support_alive,
        extended_above_224,
    )

    # 사용자가 말한 밥3 정의를 엄격히 적용:
    # 224 돌파 → 눌림 → 224 또는 112 안착까지 와야 목록상 밥3이다.
    if not bowl3_confirmed:
        score = min(score, 49)

    score = min(100, score)

    if extended_above_224:
        stage = f'224 돌파 후 이격과다 · +{distance:.1f}%'
    elif bowl3_confirmed:
        stage = f'밥3 핵심 · {retest_line}EMA 눌림/안착 확인'
    elif retest and not support_alive:
        stage = f'224 돌파 후 {retest_line}EMA 지지 이탈'
    elif accepted:
        stage = '224 돌파 유지 · 눌림/안착 대기'
    elif breakout_idx >= 0:
        stage = '224EMA 돌파 · 눌림 대기'
    elif stage2_ready:
        stage = '224EMA 돌파 직전 준비구간'
    elif long_below:
        stage = '밥2 바닥/역배열 형성 · 224 돌파 대기'
    else:
        stage = '밥1/2 구조 확인 중'

    context_below = below_count_at_break if breakout_idx >= 0 else current_below_count
    reasons = [
        f'224EMA 아래 {context_below}봉',
        f'2번구간 {"확인" if base_ok else "미확인"}',
        f'역배열 {"확인" if reverse_now else "미확인"}',
        f'112봉 신고거래량 {"확인" if record112 else "미확인"}',
        f'224 ±2% {"확인" if near224 else "미확인"}',
    ]

    arrow_series = build_arrow_signals(candles)
    arrow_reason = latest_signal_reason({'candles': candles, **arrow_series})

    details = {
        '간단 이유': ' · '.join(reasons[:5]),
        '밥그릇 단계': stage,
        '밥3 직전조건': (
            f"{'충족' if stage2_ready else '미충족'} · "
            f"224±2% {'O' if near224 else 'X'} / "
            f"112봉 신고거래량 {'O' if record112 else 'X'} / "
            f"60<112<224 {'O' if reverse_now else 'X'} / "
            f"2번구간 {'O' if base_ok else 'X'}"
        ),
        '장기 224EMA 아래': f'{context_below}봉 확인' if long_below else '미확인',
        '역배열 60<112<224': '확인' if reverse_now else '미확인',
        '112EMA 선행 회복': '최근 회복 확인' if reclaimed112 else '미확인',
        '112봉 신고거래량': '최근20봉 내 확인' if record112 else '미확인',
        '2번구간 횡보': (
            f"{'확인' if base_ok else '미확인'} · 폭 {base_width:.1f}% · 방향성 {base_direction:.2f}"
        ),
        '224EMA 돌파': (
            f'확인 · 돌파봉 거래량/20봉평균 {breakout_volume_ratio:.2f}배'
            if breakout_idx >= 0 else '대기'
        ),
        '224EMA 위 유지': f'확인 · {accepted_count}봉' if accepted else '대기',
        '눌림/안착': (
            f'확인 · {retest_line}EMA 지지 · 현재유지 {"O" if support_alive else "X"}'
            if retest else '대기'
        ),
        '밥3 확정': '확정' if bowl3_confirmed else '미확정',
        '224EMA 거리': (
            f'{last_ema:,.0f} / {distance:+.2f}% · '
            f"{'이격과다·현재자리 제외' if extended_above_224 else '유효범위'}"
            if last_ema else '데이터 부족'
        ),
        '사진검색기 A': str(ref_a.get('summary') or '-'),
        '화살표 신호': arrow_reason,
    }

    result = BowlAnalysis(
        stage=stage,
        score=score,
        long_below=long_below,
        below_count=context_below,
        breakout=breakout_idx >= 0,
        breakout_index=breakout_idx,
        accepted=accepted,
        retest=retest,
        ema_value=last_ema,
        distance_pct=distance,
        details=details,
    )

    # Historical display markers are independent from the CURRENT classification.
    # Therefore old Bowl-3-like positions remain visible when newer data arrives.
    bowl3_markers = _historical_bowl3_markers(candles, e112, e224, settings)
    if breakout_idx < 0 and stage2_ready:
        bowl3_markers.append({
            'index': last,
            'kind': 'prebreak',
            'label': '224 직전',
            'stage': stage,
        })
    if breakout_idx >= 0:
        bowl3_markers.append({
            'index': breakout_idx,
            'kind': 'breakout',
            'label': '224 돌파',
            'stage': '224EMA 돌파',
        })
    if accepted and accepted_idx >= 0:
        bowl3_markers.append({
            'index': accepted_idx,
            'kind': 'accepted',
            'label': '돌파 유지',
            'stage': '224EMA 위 유지',
        })
    if bowl3_confirmed and retest_idx >= 0:
        # If the same bar was already found by the historical scanner, replace
        # that display-only tag with the stronger CURRENT confirmed marker.
        bowl3_markers = [
            m for m in bowl3_markers
            if int(m.get('index', -1)) != int(retest_idx)
        ]
        bowl3_markers.append({
            'index': retest_idx,
            'kind': 'core',
            'label': f'밥3 {retest_line}안착',
            'stage': f'{retest_line}EMA 눌림/안착',
        })

    bowl3_markers.sort(key=lambda m: int(m.get('index', -1)))

    series = {
        'candles': candles,
        'ema60': e60,
        'ema112': e112,
        'ema224': e224,
        'bowl_stage2_ready': stage2_ready,
        'bowl_breakout_idx': breakout_idx,
        'bowl_accepted_idx': accepted_idx,
        'bowl_retest_idx': retest_idx,
        'bowl_retest_line': retest_line,
        'bowl3_confirmed': bowl3_confirmed,
        'bowl3_markers': bowl3_markers,
        'bowl_reference_a': ref_a,
    }
    series.update(arrow_series)
    series.update(build_puma_watermelon(candles, arrow_series))
    wm_stage = series.get('watermelon_stage', [0])[-1] if series.get('watermelon_stage') else 0
    wm_score = series.get('watermelon_score', [0])[-1] if series.get('watermelon_score') else 0
    wm_reason = series.get('watermelon_reason', ['-'])[-1] if series.get('watermelon_reason') else '-'
    result.details['PUMA 수박근사'] = f'{wm_stage}단계 · {wm_score}/100 · {wm_reason}'
    return result, series
