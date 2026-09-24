from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .swing import ema, normalize_candles
from .signals import build_arrow_signals, latest_signal_reason
from .watermelon_proxy import build_puma_watermelon
from .swing_reference import evaluate_swing_reference_profiles
from .market_path import find_box_before


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


def _is_bullish_body_224_breakout(
    candles: list[dict],
    e224,
    i: int,
    settings: BowlSettings,
) -> bool:
    """True only when a bullish candle body itself crosses EMA224."""
    if i <= 0 or i >= len(candles) or i >= len(e224):
        return False
    if e224[i] is None or e224[i - 1] is None:
        return False
    c = candles[i]
    op = float(c["open"])
    close = float(c["close"])
    line = float(e224[i])
    prev_close = float(candles[i - 1]["close"])
    prev_line = float(e224[i - 1])
    return bool(
        close > op
        and op <= line
        and close > line * (1 + float(settings.breakout_buffer_pct) / 100.0)
        and prev_close <= prev_line
    )


def _concrete_mid_before(
    candles: list[dict],
    breakout_idx: int,
    settings: BowlSettings,
) -> tuple[float, dict | None]:
    """Return the midpoint of the concrete box immediately before breakout."""
    if breakout_idx <= 0:
        return 0.0, None
    try:
        box = find_box_before(candles, breakout_idx - 1, settings)
    except Exception:
        box = None
    if not isinstance(box, dict) or box.get("structure_type") != "공구리":
        return 0.0, box if isinstance(box, dict) else None
    low = float(box.get("low", 0) or 0)
    high = float(box.get("high", 0) or 0)
    if low <= 0 or high <= low:
        return 0.0, box
    return (low + high) / 2.0, box


def _find_bowl3_pullback(
    candles: list[dict],
    e112,
    breakout_idx: int,
    settings: BowlSettings,
    *,
    end_idx: int | None = None,
) -> dict | None:
    """Find the first bearish pullback to the breakout-open/EMA112/concrete-mid.

    The bullish EMA224 body-breakout candle is the reference candle. A Bowl-3
    retest is not another touch of EMA224 by itself: a later bearish candle must
    pull back to the reference candle open, EMA112, or the midpoint of the
    concrete box that existed before the breakout, while closing without a
    material support failure.
    """
    if breakout_idx < 0 or breakout_idx >= len(candles):
        return None

    ref_open = float(candles[breakout_idx]["open"])
    concrete_mid, box = _concrete_mid_before(candles, breakout_idx, settings)
    stop = min(
        len(candles),
        int(end_idx) if end_idx is not None else breakout_idx + 36,
    )
    start = breakout_idx + 1
    touch_tol = float(settings.retest_tolerance_pct) / 100.0
    hold_tol = float(settings.acceptance_tolerance_pct) / 100.0

    for j in range(start, stop):
        candle = candles[j]
        op = float(candle["open"])
        close = float(candle["close"])
        low = float(candle["low"])

        # User definition: the pullback candle itself must be bearish.
        if close >= op:
            continue

        targets: list[tuple[str, int, float]] = []
        if ref_open > 0:
            targets.append(("기준봉시가", 0, ref_open))
        if j < len(e112) and e112[j] is not None and float(e112[j]) > 0:
            targets.append(("112EMA", 112, float(e112[j])))
        if concrete_mid > 0:
            targets.append(("공구리중간", 0, concrete_mid))

        for source, line_no, target in targets:
            touched = low <= target * (1 + touch_tol)
            held = close >= target * (1 - hold_tol)
            if touched and held:
                return {
                    "index": j,
                    "source": source,
                    "line": line_no,
                    "value": target,
                    "reference_open": ref_open,
                    "concrete_mid": concrete_mid,
                    "box": box,
                }
    return None


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
        crossed = _is_bullish_body_224_breakout(candles, e224, i, settings)
        if not (enough and below_count >= int(settings.min_below_closes) and crossed):
            continue

        # Historical display uses the same strict user definition as current:
        # bullish body through EMA224, then bearish pullback to reference-open,
        # EMA112, or the prior concrete-box midpoint.
        pullback = _find_bowl3_pullback(
            candles, e112, i, settings, end_idx=min(n, i + 36)
        )
        found_idx = int(pullback["index"]) if pullback else -1
        found_line = int(pullback.get("line", 0)) if pullback else 0
        found_source = str(pullback.get("source", "")) if pullback else ""

        if found_idx >= 0:
            markers.append({
                "index": found_idx,
                "kind": "historical_core",
                "label": "밥3",
                "stage": f"과거 유사 · {found_source} 눌림",
                "breakout_index": i,
                "retest_line": found_line,
                "retest_source": found_source,
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
      3) a bullish candle body breaks EMA224; that candle becomes the reference candle
      4) a later bearish pullback reaches the reference open, EMA112, or concrete midpoint

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
        crossed = _is_bullish_body_224_breakout(candles, e224, i, settings)
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
    retest_source = ""
    retest_value = 0.0
    reference_open = float(candles[breakout_idx]["open"]) if breakout_idx >= 0 else 0.0
    concrete_mid = 0.0
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

        # 밥3 핵심:
        # 1) 양봉 몸통이 EMA224를 돌파한 봉 = 기준봉
        # 2) 이후 음봉 눌림이 기준봉 시가 / EMA112 / 공구리 중간값까지 내려옴
        # 3) 해당 기준을 종가로 크게 이탈하지 않고 지지
        pullback = _find_bowl3_pullback(
            candles, e112, breakout_idx, settings,
            end_idx=min(n, breakout_idx + 36),
        )
        if pullback:
            retest = True
            retest_idx = int(pullback["index"])
            retest_line = int(pullback.get("line", 0))
            retest_source = str(pullback.get("source", ""))
            retest_value = float(pullback.get("value", 0.0) or 0.0)
            reference_open = float(pullback.get("reference_open", reference_open) or reference_open)
            concrete_mid = float(pullback.get("concrete_mid", 0.0) or 0.0)

        if retest:
            if retest_source == "112EMA":
                current_support = float(e112[last]) if e112[last] is not None else 0.0
            else:
                current_support = retest_value
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
    # 224 양봉 몸통돌파 → 음봉 눌림 → 기준봉시가/112EMA/공구리중간 지지까지 와야 밥3이다.
    if not bowl3_confirmed:
        score = min(score, 49)

    score = min(100, score)

    if extended_above_224:
        stage = f'224 돌파 후 이격과다 · +{distance:.1f}%'
    elif bowl3_confirmed:
        stage = f'밥3 핵심 · {retest_source} 눌림 확인'
    elif retest and not support_alive:
        stage = f'224 양봉돌파 후 {retest_source} 지지 이탈'
    elif accepted:
        stage = '224 양봉 몸통돌파 유지 · 음봉 눌림 대기'
    elif breakout_idx >= 0:
        stage = '224EMA 양봉 몸통돌파 · 음봉 눌림 대기'
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
        '224EMA 양봉 몸통돌파': (
            f'확인 · 기준봉 시가 {reference_open:,.0f} · 돌파봉 거래량/20봉평균 {breakout_volume_ratio:.2f}배'
            if breakout_idx >= 0 else '대기'
        ),
        '224EMA 위 유지': f'확인 · {accepted_count}봉' if accepted else '대기',
        '눌림/안착': (
            f'확인 · 음봉 → {retest_source} {retest_value:,.0f} · 현재유지 {"O" if support_alive else "X"}'
            if retest else '대기 · 기준봉시가 / 112EMA / 공구리중간'
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
            'label': '224 양봉돌파',
            'stage': '224EMA 양봉 몸통돌파 · 기준봉',
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
            'label': f'밥3 {retest_source}',
            'stage': f'음봉 → {retest_source} 눌림',
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
        'bowl_retest_source': retest_source,
        'bowl_retest_value': retest_value,
        'bowl_reference_open': reference_open,
        'bowl_concrete_mid': concrete_mid,
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
