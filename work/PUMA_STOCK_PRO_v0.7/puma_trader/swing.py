from __future__ import annotations

from dataclasses import dataclass, asdict
from math import sqrt
from statistics import mean
from typing import List, Dict, Optional


def _num(v):
    try:
        return abs(float(str(v).replace(',', '').strip()))
    except Exception:
        return 0.0


def ema(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    k = 2.0 / (period + 1.0)
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1.0 - k)
        out[i] = prev
    return out


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
    volume_ratio: float = 2.0
    upper_wick_ratio: float = 0.42
    upper_wick_vs_body: float = 1.2
    bearish_body_ratio: float = 0.58
    accumulation_lookback: int = 90
    accumulation_min_count: int = 1
    box_window: int = 18
    box_width_pct: float = 14.0
    breakout_buffer_pct: float = 0.2
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
    vols = [c['volume'] for c in candles]
    vma = rolling_mean(vols, settings.volume_period)
    flags = []
    meta = []
    for i, c in enumerate(candles):
        rng = max(c['high'] - c['low'], 1e-9)
        body = abs(c['close'] - c['open'])
        upper = max(0.0, c['high'] - max(c['open'], c['close']))
        body_ratio = body / rng
        upper_ratio = upper / rng
        ratio = 0.0
        if i > 0 and vma[i - 1]:
            ratio = c['volume'] / vma[i - 1]
        high_volume = ratio >= settings.volume_ratio
        long_upper = upper_ratio >= settings.upper_wick_ratio and upper >= body * settings.upper_wick_vs_body
        big_bear = c['close'] < c['open'] and body_ratio >= settings.bearish_body_ratio
        is_acc = bool(high_volume and (long_upper or big_bear))
        flags.append(is_acc)
        meta.append({
            'volume_ratio': ratio,
            'upper_wick_ratio': upper_ratio,
            'body_ratio': body_ratio,
            'pattern': '긴 윗꼬리' if long_upper else ('장대음봉' if big_bear else '-'),
        })
    return flags, meta


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


def analyze(candles_raw: List[dict], settings: SwingSettings | None = None) -> tuple[SwingAnalysis, dict]:
    settings = settings or SwingSettings()
    candles = normalize_candles(candles_raw)
    if len(candles) < 60:
        raise ValueError('분석에는 최소 60개 이상의 일봉이 필요합니다.')
    closes = [c['close'] for c in candles]
    e20 = ema(closes, settings.ema_short)
    e60 = ema(closes, settings.ema_mid)
    e112 = ema(closes, settings.ema_long1)
    e224 = ema(closes, settings.ema_long2)
    e448 = ema(closes, settings.ema_long3)
    blue = shifted_bbands_upper(closes, settings.blue_period, settings.blue_dev, settings.blue_shift)
    acc_flags, acc_meta = accumulation_flags(candles, settings)

    last = len(candles) - 1
    reverse = False
    if e112[last] is not None and e224[last] is not None and e448[last] is not None:
        reverse = e112[last] < e224[last] < e448[last]
    # 장기 448 데이터 부족 시 112<224만 참고 표시하되 '확인'은 false 유지

    look_start = max(0, len(candles) - settings.accumulation_lookback)
    acc_idx = [i for i in range(look_start, len(candles)) if acc_flags[i]]
    box = _find_box(candles, settings)
    bval = blue[last] or 0.0
    current = closes[last]
    bdist = ((current / bval - 1) * 100) if bval else 999.0
    bnear = bool(bval and abs(bdist) <= settings.blue_near_pct)

    stage = '장기 역배열 확인'
    score = 0
    if reverse:
        score += 20
        stage = '매집봉 대기'
    if len(acc_idx) >= settings.accumulation_min_count:
        score += 20
        stage = '공구리(박스권) 확인'
    if box:
        score += 20
        stage = '박스 상단 돌파 대기' if box.get('breakout_idx', -1) < 0 else '상단 안착 확인'
    breakout = bool(box and box.get('breakout_idx', -1) >= 0)
    if breakout:
        score += 15
    accepted = bool(box and box.get('accepted'))
    if accepted:
        score += 15
        stage = '파란점선 / 최종 타점 대기'
    if bnear:
        score += 10
        if accepted:
            stage = '수박·화살표 최종 타점 대기'

    details = {
        '장기 EMA 역배열': '확인' if reverse else '미확인',
        '매집봉/구간': f'{len(acc_idx)}회 감지',
        '공구리(박스권)': '확인' if box else '미확인',
        '박스 상단 돌파': '확인' if breakout else '대기',
        '상단 박스 안착': '확인' if accepted else '대기',
        '파란점선': (f'{bval:,.0f} / 거리 {bdist:+.2f}%' if bval else '데이터 부족'),
        '수박/화살표': '외부 신호 대기',
    }
    analysis = SwingAnalysis(
        stage=stage, score=score, reverse_order=reverse,
        accumulation_indices=acc_idx, accumulation_count=len(acc_idx),
        box_found=bool(box), box_low=(box or {}).get('low', 0.0), box_high=(box or {}).get('high', 0.0),
        box_start=(box or {}).get('start', -1), box_end=(box or {}).get('end', -1),
        breakout_index=(box or {}).get('breakout_idx', -1), breakout=breakout, accepted=accepted,
        blue_value=bval, blue_distance_pct=bdist, blue_near=bnear,
        current_price=current, details=details,
    )
    series = {
        'candles': candles,
        'ema20': e20, 'ema60': e60, 'ema112': e112, 'ema224': e224, 'ema448': e448,
        'blue': blue, 'acc_flags': acc_flags, 'acc_meta': acc_meta,
        'box': box,
    }
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
        # 매집봉: 거래량 증가 + 긴 윗꼬리 or 장대음봉
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
