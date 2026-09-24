from __future__ import annotations

from dataclasses import dataclass, asdict
from math import sqrt
from statistics import mean
from typing import List, Dict, Optional

from .indicators import ichimoku_cloud, hero_eavg
from .signals import build_arrow_signals, latest_signal_reason
from .watermelon_proxy import build_puma_watermelon
from .market_path import analyze_market_path
from .swing_reference import evaluate_swing_reference_profiles


def _num(v):
    try:
        return abs(float(str(v).replace(',', '').strip()))
    except Exception:
        return 0.0


def ema(values: List[float], period: int) -> List[Optional[float]]:
    """Shared Kiwoom-style EAVG used by chart, Bowl and signal logic."""
    return hero_eavg(values, period)


def rolling_mean(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0:
        return out
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= period:
            s -= values[i - period]
        if i >= period - 1:
            out[i] = s / period
    return out


def rolling_std(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if period <= 1:
        return out
    for i in range(period - 1, len(values)):
        xs = values[i - period + 1:i + 1]
        m = sum(xs) / period
        out[i] = sqrt(sum((x - m) ** 2 for x in xs) / period)
    return out


def shifted_bbands_upper(closes: List[float], period: int = 26, dev: float = 2.6, shift_bars: int = 26):
    ma = rolling_mean(closes, period)
    sd = rolling_std(closes, period)
    upper: List[Optional[float]] = [None] * len(closes)
    for i in range(len(closes)):
        if ma[i] is not None and sd[i] is not None:
            upper[i] = ma[i] + dev * sd[i]
    # PUMA 기본 구현: 과거 계산값을 shift_bars 이후 봉에 표시.
    # 영웅문 shift 방향 차이가 확인되면 설정에서 반대로 바꿀 수 있도록 UI에 표기한다.
    shifted: List[Optional[float]] = [None] * len(closes)
    for i in range(len(closes)):
        j = i - shift_bars
        if j >= 0:
            shifted[i] = upper[j]
    return shifted


@dataclass
class SwingSettings:
    ema_short: int = 20
    ema_mid: int = 60
    ema_long1: int = 112
    ema_long2: int = 224
    ema_long3: int = 448
    volume_period: int = 20
    volume_ratio: float = 1.8
    upper_wick_ratio: float = 0.42
    upper_wick_vs_body: float = 1.2
    bearish_body_ratio: float = 0.58
    accumulation_lookback: int = 112
    accumulation_min_count: int = 2
    accumulation_cluster_window: int = 20
    box_window: int = 90  # legacy compatibility; dynamic box uses box_period_min/max
    # legacy fields kept for old config compatibility; v2.2 does not force box duration.
    box_period_min: int = 60
    box_period_max: int = 112
    box_search_lookback: int = 160
    box_width_pct: float = 30.0
    box_min_coverage: float = 0.68
    box_min_touches: int = 3
    box_min_alternations: int = 3
    box_touch_tolerance_pct: float = 2.0
    box_max_drift_pct: float = 5.0
    box_max_directionality: float = 0.50
    breakout_volume_ratio: float = 3.0
    pullback_volume_max_ratio: float = 0.60
    pullback_base_volume_max_ratio: float = 1.00
    pullback_support_tolerance_pct: float = 3.0
    pullback_ma_touch_tolerance_pct: float = 2.0
    long_ma_break_buffer_pct: float = 0.15
    bottom_drawdown_pct: float = 10.0
    bottom_lookback: int = 240
    bottom_exclude_recent: int = 20
    bowl_below_lookback: int = 100
    bowl_min_below_closes: int = 70
    pullback_confirm_bars: int = 1
    rebreak_volume_ratio: float = 3.0
    path_max_pullback_bars: int = 12
    path_duplicate_suppress_bars: int = 8
    breakout_buffer_pct: float = 0.15
    acceptance_window: int = 8
    acceptance_min_closes: int = 4
    acceptance_tolerance_pct: float = 1.0
    blue_period: int = 26
    blue_dev: float = 2.6
    blue_shift: int = 26
    blue_near_pct: float = 3.0

    def to_dict(self):
        return asdict(self)


@dataclass
class SwingAnalysis:
    stage: str
    score: int
    reverse_order: bool
    accumulation_indices: List[int]
    accumulation_count: int
    box_found: bool
    box_low: float
    box_high: float
    box_start: int
    box_end: int
    breakout_index: int
    breakout: bool
    accepted: bool
    blue_value: float
    blue_distance_pct: float
    blue_near: bool
    current_price: float
    details: Dict[str, str]


def normalize_candles(rows: List[dict]) -> List[dict]:
    """키움/CSV 형태를 시간 오름차순 OHLCV 표준 형태로 변환."""
    out = []
    for r in rows:
        dt = str(r.get('dt') or r.get('date') or r.get('cntr_tm') or '')
        out.append({
            'date': dt,
            'open': _num(r.get('open_pric', r.get('open', 0))),
            'high': _num(r.get('high_pric', r.get('high', 0))),
            'low': _num(r.get('low_pric', r.get('low', 0))),
            'close': _num(r.get('cur_prc', r.get('close', 0))),
            'volume': _num(r.get('trde_qty', r.get('volume', 0))),
        })
    out = [r for r in out if r['close'] > 0]
    if len(out) >= 2 and out[0]['date'] > out[-1]['date']:
        out.reverse()
    return out


def accumulation_flags(candles: List[dict], settings: SwingSettings):
    """Detect volume/price-behavior accumulation candidates.

    The user's rule is volume-first, not candle-shape-only:
      - a long upper wick with clearly elevated volume can be accumulation,
      - a large bearish dump can also be accumulation when volume explodes,
      - volume does not need to be 3x the 20-bar average; a visually standout
        volume spike versus recent history is enough,
      - unusually large volume with only a muted price response is suspicious
        accumulation/absorption,
      - tiny ambiguous cross/doji candles remain excluded.

    Final chart/scoring still uses confirm_accumulation_flags(), so repeated
    evidence is required before the chart says 'confirmed accumulation'.
    """
    vols = [float(c['volume']) for c in candles]
    vma = rolling_mean(vols, settings.volume_period)
    raw = []
    meta = []

    for i, c in enumerate(candles):
        rng = max(float(c['high']) - float(c['low']), 1e-9)
        body = abs(float(c['close']) - float(c['open']))
        upper = max(0.0, float(c['high']) - max(float(c['open']), float(c['close'])))
        lower = max(0.0, min(float(c['open']), float(c['close'])) - float(c['low']))
        body_ratio = body / rng
        upper_ratio = upper / rng
        close_pos = (float(c['close']) - float(c['low'])) / rng

        ratio = 0.0
        if i > 0 and vma[i - 1]:
            ratio = float(c['volume']) / float(vma[i - 1])

        # "눈에 띄는 거래량"은 고정 3배가 아니라 최근 분포까지 함께 본다.
        recent = sorted(
            float(candles[j]['volume'])
            for j in range(max(0, i - 60), i)
            if float(candles[j]['volume']) > 0
        )
        recent_p85 = 0.0
        recent_p95 = 0.0
        if recent:
            p85_idx = min(len(recent) - 1, int((len(recent) - 1) * 0.85))
            p95_idx = min(len(recent) - 1, int((len(recent) - 1) * 0.95))
            recent_p85 = recent[p85_idx]
            recent_p95 = recent[p95_idx]

        current_vol = float(c['volume'])
        # Old saved configs may still contain 3.0. Treat this as a reference
        # sensitivity, never as a hard 300% gate.
        relative_ref = min(2.20, max(1.35, float(settings.volume_ratio)))
        visually_high = bool(
            ratio >= relative_ref
            or (recent_p85 > 0 and current_vol >= recent_p85 and ratio >= 1.30)
            or (recent_p95 > 0 and current_vol >= recent_p95 and ratio >= 1.25)
        )

        # 작은 십자가/도지는 앞서 정한 대로 제외.
        meaningful_body = body_ratio >= 0.10

        # 긴 윗꼬리 + 수상한 거래량.
        wick_body_req = max(float(settings.upper_wick_vs_body), 1.35)
        upper_ratio_req = max(float(settings.upper_wick_ratio), 0.40)
        long_upper = (
            upper_ratio >= upper_ratio_req
            and upper >= max(body * wick_body_req, lower * 1.15)
        )

        # 장대음봉 급락도 거래량이 확실히 터졌다면 매집 후보.
        big_bear = (
            float(c['close']) < float(c['open'])
            and body_ratio >= float(settings.bearish_body_ratio)
            and close_pos <= 0.42
        )
        bear_volume = bool(
            big_bear
            and (
                ratio >= relative_ref
                or (recent_p85 > 0 and current_vol >= recent_p85 and ratio >= 1.35)
                or (recent_p95 > 0 and current_vol >= recent_p95 and ratio >= 1.25)
            )
        )

        # 가격 반응 대비 거래량이 과도한 흡수형 매집.
        # 전일 종가 대비 +3% 이내 상승/보합인데 거래량만 최근 상위권이면 후보.
        prev_close = float(candles[i - 1]['close']) if i > 0 else float(c['open'])
        close_change_pct = (
            (float(c['close']) / prev_close - 1.0) * 100.0
            if prev_close > 0 else 0.0
        )
        muted_price_response = bool(
            meaningful_body
            and -3.5 <= close_change_pct <= 3.0
            and (
                ratio >= max(1.50, relative_ref * 0.90)
                or (recent_p85 > 0 and current_vol >= recent_p85 and ratio >= 1.25)
                or (recent_p95 > 0 and current_vol >= recent_p95 and ratio >= 1.25)
            )
        )

        candidate = bool(
            meaningful_body
            and (
                (visually_high and long_upper)
                or bear_volume
                or muted_price_response
            )
        )

        if candidate:
            if bear_volume:
                pattern = '고거래량 장대음봉'
            elif long_upper:
                pattern = '고거래량 긴 윗꼬리'
            else:
                pattern = '가격반응대비 이상거래량'
        else:
            pattern = '-'

        raw.append(candidate)
        meta.append({
            'volume_ratio': ratio,
            'volume_recent_p85': recent_p85,
            'volume_recent_p95': recent_p95,
            'volume_visually_high': visually_high,
            'volume_relative_reference': relative_ref,
            'upper_wick_ratio': upper_ratio,
            'body_ratio': body_ratio,
            'close_change_pct': close_change_pct,
            'pattern': pattern,
            'raw_candidate': candidate,
            'confirmed': False,
            'cluster_size': 0,
            'big_bear': bool(big_bear),
            'muted_price_response': bool(muted_price_response),
            'excluded_small_cross': bool(not meaningful_body),
        })
    return raw, meta


def confirm_accumulation_flags(raw_flags: List[bool], meta: List[dict], cluster_window: int = 20):
    """Confirm only repeated candidates; single hits stay as '후보'."""
    raw_idx = [i for i, flag in enumerate(raw_flags) if flag]
    groups = []
    group = []
    for idx in raw_idx:
        if not group or idx - group[-1] <= cluster_window:
            group.append(idx)
        else:
            groups.append(group)
            group = [idx]
    if group:
        groups.append(group)

    confirmed = [False] * len(raw_flags)
    for group in groups:
        size = len(group)
        if size < 2:
            continue
        for idx in group:
            confirmed[idx] = True
            if idx < len(meta):
                meta[idx]['confirmed'] = True
                meta[idx]['cluster_size'] = size
    return confirmed


def _find_box(candles: List[dict], settings: SwingSettings):
    n = len(candles)
    w = settings.box_window
    if n < w + 3:
        return None
    # 최근 80봉 범위에서 "박스 -> 상단 돌파 -> 위쪽 안착"을 뒤에서부터 탐색
    start_min = max(0, n - 120)
    best = None
    for end in range(n - 2, start_min + w - 2, -1):
        start = end - w + 1
        seg = candles[start:end + 1]
        low = min(c['low'] for c in seg)
        high = max(c['high'] for c in seg)
        mid = (high + low) / 2 if high + low else 1
        width_pct = (high - low) / mid * 100
        if width_pct > settings.box_width_pct:
            continue
        # 박스 이후 첫 유효 돌파 탐색
        breakout_idx = -1
        for j in range(end + 1, min(n, end + 1 + settings.acceptance_window + 8)):
            if candles[j]['close'] > high * (1 + settings.breakout_buffer_pct / 100):
                breakout_idx = j
                break
        if breakout_idx < 0:
            # 현재가 박스 내부면 '공구리 형성' 후보로 유지
            if start >= n - 80:
                best = dict(start=start, end=end, low=low, high=high, width_pct=width_pct,
                            breakout_idx=-1, accepted=False)
                break
            continue
        after = candles[breakout_idx:min(n, breakout_idx + settings.acceptance_window)]
        accepted_count = sum(1 for c in after if c['close'] >= high * (1 - settings.acceptance_tolerance_pct / 100))
        accepted = accepted_count >= settings.acceptance_min_closes
        return dict(start=start, end=end, low=low, high=high, width_pct=width_pct,
                    breakout_idx=breakout_idx, accepted=accepted, accepted_count=accepted_count)
    return best


def detect_breakout_pullback(candles: List[dict]) -> dict:
    """Detect a strong 기준봉 -> high-volume shakeout -> contracting pullback.

    This is ticker-agnostic. It is designed to recognize patterns like:
    quiet base -> +18% or stronger breakout close -> 2~6 bars of pullback ->
    price still above the breakout candle open/base while volume contracts.
    """
    n = len(candles)
    default = {
        'confirmed': False, 'quality': 0, 'impulse_index': -1,
        'impulse_change_pct': 0.0, 'bars_after': 0, 'volume_contraction': 1.0,
        'current_above_impulse_open': False, 'retrace_pct': 0.0, 'reason': '미확인',
    }
    if n < 25:
        return default

    vols = [float(c['volume']) for c in candles]
    candidates = []
    start = max(20, n - 12)
    for i in range(start, n - 1):
        prev_close = float(candles[i-1]['close'])
        c = candles[i]
        if prev_close <= 0:
            continue
        chg = (float(c['close']) / prev_close - 1.0) * 100.0
        base_vol = mean(vols[max(0, i-20):i]) if i > 0 else 0.0
        vol_ratio = (float(c['volume']) / base_vol) if base_vol else 0.0
        strong_close = float(c['close']) >= float(c['high']) * 0.90
        if chg >= 18.0 and vol_ratio >= 3.0 and strong_close:
            candidates.append((i, chg, vol_ratio))

    if not candidates:
        return default

    i, chg, vol_ratio = candidates[-1]
    bars_after = n - 1 - i
    if not (2 <= bars_after <= 6):
        return default

    impulse = candles[i]
    after = candles[i+1:]
    current = candles[-1]
    peak_high = max(float(c['high']) for c in after) if after else float(impulse['high'])
    peak_vol = max(float(c['volume']) for c in ([impulse] + after))
    current_vol = float(current['volume'])
    contraction = current_vol / peak_vol if peak_vol else 1.0

    impulse_open = float(impulse['open'])
    current_close = float(current['close'])
    above_open = current_close >= impulse_open * 1.03
    retrace = ((peak_high - current_close) / peak_high * 100.0) if peak_high else 0.0
    controlled_pullback = 5.0 <= retrace <= 35.0
    volume_calm = contraction <= 0.45

    quality = 0
    quality += 30
    if vol_ratio >= 8.0:
        quality += 15
    elif vol_ratio >= 5.0:
        quality += 10
    if above_open:
        quality += 25
    if controlled_pullback:
        quality += 15
    if volume_calm:
        quality += 20
    quality = min(100, quality)

    confirmed = bool(above_open and controlled_pullback and volume_calm and quality >= 65)
    reason = (
        f"기준봉 {chg:+.1f}% · {bars_after}봉 눌림 · "
        f"거래량 {contraction*100:.0f}%로 감소 · "
        f"기준봉 시가 {'상회' if above_open else '이탈'}"
    )
    return {
        'confirmed': confirmed,
        'quality': quality,
        'impulse_index': i,
        'impulse_change_pct': chg,
        'bars_after': bars_after,
        'volume_contraction': contraction,
        'current_above_impulse_open': above_open,
        'retrace_pct': retrace,
        'reason': reason,
    }



def analyze(candles_raw: List[dict], settings: SwingSettings | None = None) -> tuple[SwingAnalysis, dict]:
    settings = settings or SwingSettings()
    candles = normalize_candles(candles_raw)
    if len(candles) < 60:
        raise ValueError('분석에는 최소 60개 이상의 일봉이 필요합니다.')
    closes = [c['close'] for c in candles]
    e5 = ema(closes, 5)
    e20 = ema(closes, settings.ema_short)
    e60 = ema(closes, settings.ema_mid)
    e112 = ema(closes, settings.ema_long1)
    e224 = ema(closes, settings.ema_long2)
    e448 = ema(closes, settings.ema_long3)
    blue = shifted_bbands_upper(closes, settings.blue_period, settings.blue_dev, settings.blue_shift)
    raw_acc_flags, acc_meta = accumulation_flags(candles, settings)
    acc_flags = confirm_accumulation_flags(raw_acc_flags, acc_meta, settings.accumulation_cluster_window)

    last = len(candles) - 1
    reverse = False
    if e112[last] is not None and e224[last] is not None and e448[last] is not None:
        reverse = e112[last] < e224[last] < e448[last]
    # 장기 448 데이터 부족 시 112<224만 참고 표시하되 '확인'은 false 유지

    look_start = max(0, len(candles) - settings.accumulation_lookback)
    acc_idx = [i for i in range(look_start, len(candles)) if acc_flags[i]]
    raw_acc_idx = [
        i for i in range(look_start, len(candles))
        if i < len(acc_meta) and bool(acc_meta[i].get('raw_candidate'))
    ]
    required_acc = max(2, int(settings.accumulation_min_count or 2))
    market_path = analyze_market_path(candles, settings)
    box = market_path.get('box')
    boxes = market_path.get('boxes', [])
    core_path = market_path.get('current', {})
    bval = blue[last] or 0.0
    current = closes[last]
    bdist = ((current / bval - 1) * 100) if bval else 999.0
    bnear = bool(bval and abs(bdist) <= settings.blue_near_pct)
    reference = evaluate_swing_reference_profiles(candles)
    reference_best = int(reference.get('best_score', 0) or 0)
    reference_exact = list(reference.get('exact_matches') or [])

    stage = '장기 역배열 확인'
    score = 0
    if reverse:
        score += 20
        stage = '매집봉 대기'
    if len(acc_idx) >= required_acc:
        score += 20
        stage = '공구리(박스권) 확인'
    if box:
        if box.get('structure_type') == '공구리':
            score += 20
            stage = '공구리 확인 · 돌파 대기' if box.get('breakout_idx', -1) < 0 else '공구리 상단 돌파 확인'
        else:
            score += 10
            stage = '전고점언덕 저항 확인'
    breakout = bool(core_path.get('breakout_idx', -1) >= 0)
    if breakout:
        score += 15
    accepted = bool(breakout and core_path.get('support_hold'))
    if accepted:
        score += 15
    if bnear:
        score += 10
    if core_path.get('stage_key') == 'PULLBACK':
        score += 15
    if core_path.get('active'):
        score += 25
        stage = str(core_path.get('stage') or stage)
    elif box and not breakout:
        stage = '공구리 확인 · 바닥/밥그릇3에서 112·224 동반 돌파 대기'

    # The three user-provided Kiwoom searchers are independent candidate
    # signatures. A strong exact/near match is allowed to classify a stock as
    # swing-worthy even before the older reverse-MA/box path is fully mature.
    structural_score = min(100, score)
    score = min(100, max(structural_score, reference_best))
    if reference_exact:
        tags = '/'.join(reference_exact)
        stage = f'스윙검색기 {tags} 일치 · {stage}'
    elif reference_best >= 70:
        stage = f'스윙검색기 근접 {reference.get("best_key","-")} · {stage}'

    reasons = [
        ('장기 역배열 확인' if reverse else '장기 역배열 미확인'),
        (f'매집확정 {len(acc_idx)}봉' if len(acc_idx) >= required_acc else f'매집확정 없음 / 후보 {len(raw_acc_idx)}봉'),
        (
            '공구리 확인'
            if box and box.get('structure_type') == '공구리'
            else ('전고점언덕 확인' if box else '공구리 미확인')
        ),
        (str(core_path.get('stage') or '112·224 동반 돌파 대기')),
    ]
    if bnear:
        reasons.append(f'파란점선 근접 {bdist:+.2f}%')
    if core_path.get('active'):
        reasons.insert(0, str(core_path.get('stage')))
    if reference_best >= 55:
        reasons.insert(0, f"{reference.get('best_name','검색기')} {reference_best}/100")

    arrow_series = build_arrow_signals(candles)
    overlay_suppressed = bool(arrow_series.get('long_trend_suppressed_now'))
    arrow_reason = latest_signal_reason({'candles': candles, **arrow_series})

    details = {
        '간단 이유': ' · '.join(reasons[:4]),
        '장기 EMA 역배열': '확인' if reverse else '미확인',
        '매집봉/구간': (f'확정 {len(acc_idx)}봉 · 후보 {len(raw_acc_idx)}봉' if acc_idx else f'확정 없음 · 후보 {len(raw_acc_idx)}봉'),
        '공구리(박스권)': (
            (
                f"확인 · 실제 수평구간 {box.get('period',0)}봉 · "
                f"지지 {box.get('low',0):,.0f} / 저항 {box.get('high',0):,.0f} · "
                f"상단 {box.get('top_touches',0)}회 / 하단 {box.get('bottom_touches',0)}회 · "
                f"왕복 {box.get('alternations',0)}회 · 기울기 {box.get('drift_pct',0):.1f}%"
            )
            if box and box.get('structure_type') == '공구리'
            else (
                f"공구리 미확인 · 전고점 저항 {box.get('high',0):,.0f} 확인"
                if box else '미확인'
            )
        ),
        '단테식 돌파·눌림 경로': (
            f"{'활성' if core_path.get('active') else '대기'} · {core_path.get('stage','-')} · "
            f"{core_path.get('reason','-')}"
        ),
        '112/224 동반 돌파': (
            f"확인 · {core_path.get('context_name','-')} · "
            f"{core_path.get('breakout_ma_period',0)}EMA + "
            f"{'공구리 상단' if core_path.get('structure_type')=='공구리' else '전고점'}"
            if breakout else '대기 · 바닥권/밥그릇3 + 112/224 상향돌파 + 공구리/전고점 동시 돌파 필요'
        ),
        '112/224 눌림': (
            f"확인 · 음봉 {core_path.get('pullback_ma_period',0)}EMA 접촉 · "
            f"거래량/돌파봉 {core_path.get('pullback_volume_ratio',1):.2f} · "
            f"20봉평균대비 {core_path.get('pullback_base_volume_ratio',1):.2f}"
            if core_path.get('pullback_idx',-1) >= 0
            else '대기 · 돌파 후 음봉이 112/224EMA까지 눌리고 거래량 감소 필요'
        ),
        '재돌파': (
            f"확인 · 거래량 {core_path.get('rebreak_volume_ratio',0):.2f}배"
            if core_path.get('stage') == '확정 재돌파'
            else '대기 · 확정 눌림 이후 재상승 필요'
        ),
        '파란점선': (f'{bval:,.0f} / 거리 {bdist:+.2f}%' if bval else '데이터 부족'),
        '스윙검색기 A · 224근접': str((reference.get('A') or {}).get('summary') or '-'),
        '스윙검색기 B · 급등후눌림': str((reference.get('B') or {}).get('summary') or '-'),
        '스윙검색기 C · 장기돌파': str((reference.get('C') or {}).get('summary') or '-'),
        '스윙검색기 종합': f"{reference.get('best_name','-')} · {reference_best}/100 · 정확일치 {','.join(reference_exact) if reference_exact else '없음'}",
        '화살표 신호': arrow_reason,
        '장기정배열 이격 제외': (
            '적용 · 112>224>448 정배열 + 현재가 224EMA 대비 +8% 초과'
            if overlay_suppressed else '미적용'
        ),
    }
    analysis = SwingAnalysis(
        stage=stage, score=score, reverse_order=reverse,
        accumulation_indices=acc_idx, accumulation_count=len(acc_idx),
        box_found=bool(box), box_low=(box or {}).get('low', 0.0), box_high=(box or {}).get('high', 0.0),
        box_start=(box or {}).get('start', -1), box_end=(box or {}).get('end', -1),
        breakout_index=core_path.get('breakout_idx', -1), breakout=breakout, accepted=accepted,
        blue_value=bval, blue_distance_pct=bdist, blue_near=bnear,
        current_price=current, details=details,
    )
    series = {
        'candles': candles,
        'ema5': e5, 'ema20': e20, 'ema60': e60, 'ema112': e112, 'ema224': e224, 'ema448': e448,
        'blue': blue, 'raw_acc_flags': raw_acc_flags, 'acc_flags': acc_flags, 'acc_meta': acc_meta,
        'box': box,
        'boxes': boxes,
        'pullback': core_path,
        'core_path': core_path,
        'path_breakout': market_path.get('path_breakout', []),
        'path_pullback': market_path.get('path_pullback', []),
        'path_rebreakout': market_path.get('path_rebreakout', []),
        'path_breakout_ma': market_path.get('path_breakout_ma', []),
        'path_pullback_ma': market_path.get('path_pullback_ma', []),
        'swing_reference': reference,
        'overlay_suppressed_long_trend': overlay_suppressed,
    }
    series.update(ichimoku_cloud(candles))
    series.update(arrow_series)
    series.update(build_puma_watermelon(candles, arrow_series, acc_flags=acc_flags))
    wm_stage = series.get('watermelon_stage', [0])[-1] if series.get('watermelon_stage') else 0
    wm_score = series.get('watermelon_score', [0])[-1] if series.get('watermelon_score') else 0
    wm_reason = series.get('watermelon_reason', ['-'])[-1] if series.get('watermelon_reason') else '-'
    analysis.details['PUMA 수박근사'] = f'{wm_stage}단계 · {wm_score}/100 · {wm_reason}'
    return analysis, series


def demo_candles(n: int = 520) -> List[dict]:
    """UI 확인용 합성 일봉. 실제 투자판단 데이터가 아니다."""
    import random
    from datetime import date, timedelta
    rnd = random.Random(26092026)
    rows = []
    p = 6800.0
    start = date.today() - timedelta(days=n * 2)
    d = start
    for i in range(n):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        # 오래 하락 -> 바닥 -> 매집 -> 박스 -> 상단 박스 -> 돌파
        if i < 250:
            drift = -0.0020 + rnd.uniform(-0.012, 0.010)
        elif i < 350:
            drift = -0.0002 + rnd.uniform(-0.010, 0.010)
        elif i < 430:
            drift = 0.0003 + rnd.uniform(-0.007, 0.007)
        elif i < 485:
            drift = 0.0010 + rnd.uniform(-0.006, 0.007)
        else:
            drift = 0.0040 + rnd.uniform(-0.010, 0.014)
        op = p
        cl = max(500, op * (1 + drift))
        base_rng = abs(cl - op) + op * rnd.uniform(0.004, 0.012)
        hi = max(op, cl) + base_rng * rnd.uniform(0.2, 0.8)
        lo = min(op, cl) - base_rng * rnd.uniform(0.2, 0.8)
        vol = int(120000 + rnd.random() * 180000)
        # 매집봉 예시: 거래량 증가 + 긴 윗꼬리 / 장대음봉 급락
        if i in (365, 389, 421):
            vol *= 7
            hi = max(op, cl) + op * 0.10
            cl = op * 1.01
        if i in (447,):
            vol *= 8
            cl = op * 0.88
            lo = min(lo, cl * 0.98)
        rows.append({'dt': d.strftime('%Y%m%d'), 'open_pric': int(op), 'high_pric': int(hi),
                     'low_pric': int(max(100, lo)), 'cur_prc': int(cl), 'trde_qty': vol})
        p = cl
        d += timedelta(days=1)
    return rows
