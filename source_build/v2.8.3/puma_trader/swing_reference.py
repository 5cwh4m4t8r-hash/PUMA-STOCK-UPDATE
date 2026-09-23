from __future__ import annotations

from math import sqrt
from statistics import mean
from typing import Optional

from .indicators import hero_eavg


def _ema(values: list[float], period: int) -> list[Optional[float]]:
    return hero_eavg(values, period)


def _rolling_mean(values: list[float], period: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += float(value)
        if i >= period:
            total -= float(values[i - period])
        if i >= period - 1:
            out[i] = total / period
    return out


def _rolling_std(values: list[float], period: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(values)
    if period <= 1:
        return out
    for i in range(period - 1, len(values)):
        seg = [float(x) for x in values[i - period + 1:i + 1]]
        avg = sum(seg) / period
        out[i] = sqrt(sum((x - avg) ** 2 for x in seg) / period)
    return out


def _bb_upper(closes: list[float], period: int = 40, dev: float = 2.2) -> list[Optional[float]]:
    ma = _rolling_mean(closes, period)
    sd = _rolling_std(closes, period)
    out: list[Optional[float]] = [None] * len(closes)
    for i in range(len(closes)):
        if ma[i] is not None and sd[i] is not None:
            out[i] = float(ma[i]) + float(dev) * float(sd[i])
    return out


def _ichimoku_visible_spans(candles: list[dict]) -> tuple[list[Optional[float]], list[Optional[float]]]:
    """Return the leading spans at the candle where they are visually plotted.

    Kiwoom's current 'price >= leading span' condition compares the current
    price with the cloud value visible at the current date. Standard Ichimoku
    spans are shifted 26 bars forward, so bar i uses source calculations from
    i-26.
    """
    n = len(candles)
    a: list[Optional[float]] = [None] * n
    b: list[Optional[float]] = [None] * n

    def midpoint(end: int, period: int) -> Optional[float]:
        start = end - period + 1
        if start < 0:
            return None
        seg = candles[start:end + 1]
        hi = max(float(x["high"]) for x in seg)
        lo = min(float(x["low"]) for x in seg)
        return (hi + lo) / 2.0

    for i in range(n):
        src = i - 26
        if src < 0:
            continue
        tenkan = midpoint(src, 9)
        kijun = midpoint(src, 26)
        span_b = midpoint(src, 52)
        if tenkan is not None and kijun is not None:
            a[i] = (tenkan + kijun) / 2.0
        if span_b is not None:
            b[i] = span_b
    return a, b


def _parabolic_sar(candles: list[dict], step: float = 0.016, max_af: float = 0.066) -> list[Optional[float]]:
    """Standard PSAR proxy for the photographed Kiwoom 0.066/0.016 setting.

    Kiwoom displays the pair as 0.066/0.016. Standard PSAR APIs conventionally
    take step then maximum, therefore PUMA evaluates it as step=0.016,
    maximum=0.066 and labels it a transparent proxy rather than claiming an
    undocumented proprietary formula.
    """
    n = len(candles)
    out: list[Optional[float]] = [None] * n
    if n < 3:
        return out

    rising = float(candles[1]["close"]) >= float(candles[0]["close"])
    ep = float(candles[0]["high"] if rising else candles[0]["low"])
    sar = float(candles[0]["low"] if rising else candles[0]["high"])
    af = float(step)
    out[0] = sar

    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if rising:
            sar = min(sar, float(candles[i - 1]["low"]))
            if i >= 2:
                sar = min(sar, float(candles[i - 2]["low"]))
            if float(candles[i]["low"]) < sar:
                rising = False
                sar = ep
                ep = float(candles[i]["low"])
                af = float(step)
            elif float(candles[i]["high"]) > ep:
                ep = float(candles[i]["high"])
                af = min(float(max_af), af + float(step))
        else:
            sar = max(sar, float(candles[i - 1]["high"]))
            if i >= 2:
                sar = max(sar, float(candles[i - 2]["high"]))
            if float(candles[i]["high"]) > sar:
                rising = True
                sar = ep
                ep = float(candles[i]["high"])
                af = float(step)
            elif float(candles[i]["low"]) < ep:
                ep = float(candles[i]["low"])
                af = min(float(max_af), af + float(step))
        out[i] = sar
    return out


def _crossed(closes: list[float], line: list[Optional[float]], i: int, up: bool) -> bool:
    if i <= 0 or i >= len(line) or line[i] is None or line[i - 1] is None:
        return False
    if up:
        return closes[i - 1] <= float(line[i - 1]) and closes[i] > float(line[i])
    return closes[i - 1] >= float(line[i - 1]) and closes[i] < float(line[i])


def _crossed_recent(closes: list[float], line: list[Optional[float]], lookback: int, up: bool) -> bool:
    start = max(1, len(closes) - max(1, int(lookback)))
    return any(_crossed(closes, line, i, up) for i in range(start, len(closes)))


def _bb_break_recent(closes: list[float], upper: list[Optional[float]], lookback: int) -> bool:
    start = max(1, len(closes) - max(1, int(lookback)))
    for i in range(start, len(closes)):
        if upper[i] is None or upper[i - 1] is None:
            continue
        if closes[i - 1] <= float(upper[i - 1]) and closes[i] > float(upper[i]):
            return True
    return False


def _record_volume_recent(volumes: list[float], record_period: int, lookback: int) -> tuple[bool, int]:
    """True when a bar in the recent window sets a new record vs prior N bars."""
    if len(volumes) < 2:
        return False, -1
    record_period = max(1, int(record_period))
    start = max(record_period, len(volumes) - max(1, int(lookback)))
    for i in range(start, len(volumes)):
        prior = volumes[i - record_period:i]
        if len(prior) == record_period and float(volumes[i]) >= max(float(x) for x in prior):
            return True, i
    return False, -1


def _near(price: float, line: Optional[float], pct: float) -> bool:
    return bool(line and float(line) > 0 and abs(float(price) / float(line) - 1.0) * 100.0 <= float(pct))


def _profile(name: str, score: int, matched: bool, checks: list[tuple[str, bool]], features: dict) -> dict:
    passed = [label for label, ok in checks if ok]
    failed = [label for label, ok in checks if not ok]
    return {
        "name": name,
        "score": int(max(0, min(100, score))),
        "matched": bool(matched),
        "passed": passed,
        "failed": failed,
        "features": dict(features),
        "summary": (
            f"{'일치' if matched else '근접'} {int(max(0, min(100, score)))}/100"
            + (f" · 확인: {', '.join(passed)}" if passed else "")
            + (f" · 부족: {', '.join(failed[:3])}" if failed else "")
        ),
    }


def evaluate_swing_reference_profiles(candles: list[dict]) -> dict:
    """Analyze the three photographed Kiwoom swing-searcher logics.

    The screenshots are used as the user's reference filters. PUMA does not
    pretend to reproduce hidden/undocumented Kiwoom internals; conditions that
    are clearly visible are implemented directly, while Parabolic is a stated
    standard-PSAR proxy.
    """
    n = len(candles)
    if n < 60:
        empty = _profile("검색기", 0, False, [], {})
        return {"A": empty, "B": empty, "C": empty, "best_name": "-", "best_score": 0, "exact_matches": []}

    closes = [float(c["close"]) for c in candles]
    volumes = [float(c["volume"]) for c in candles]
    e10 = _ema(closes, 10)
    e20 = _ema(closes, 20)
    e60 = _ema(closes, 60)
    e112 = _ema(closes, 112)
    e224 = _ema(closes, 224)
    bb40 = _bb_upper(closes, 40, 2.2)
    cloud_a, cloud_b = _ichimoku_visible_spans(candles)
    psar = _parabolic_sar(candles, 0.016, 0.066)
    last = n - 1
    price = closes[last]

    cloud1 = bool(cloud_a[last] is not None and price >= float(cloud_a[last]))
    cloud2 = bool(cloud_b[last] is not None and price >= float(cloud_b[last]))
    cloud_both = cloud1 and cloud2

    # Photo A: 224MA within 2% + 112-bar record volume within 20 bars
    # + reverse MA stack 60 < 112 < 224.
    near224 = _near(price, e224[last], 2.0)
    record112, record112_idx = _record_volume_recent(volumes, 112, 20)
    reverse_60_112_224 = bool(
        e60[last] is not None and e112[last] is not None and e224[last] is not None
        and float(e60[last]) < float(e112[last]) < float(e224[last])
    )
    a_checks = [
        ("224EMA ±2%", near224),
        ("최근20봉 112봉 신고거래량", record112),
        ("60<112<224 역배열", reverse_60_112_224),
    ]
    a_score = int(35 * near224 + 35 * record112 + 30 * reverse_60_112_224)
    profile_a = _profile(
        "A · 224근접 역배열/신고거래량형",
        a_score,
        all(ok for _, ok in a_checks),
        a_checks,
        {
            "near224": near224,
            "record112_20": record112,
            "record112_index": record112_idx,
            "reverse_60_112_224": reverse_60_112_224,
        },
    )

    # Photo B: strong 10-bar range -> cloud breakout -> short-MA dead crosses
    # and 10/20MA proximity -> PSAR rising -> BB40/2.2 breakout in last 10
    # -> 60-bar record volume in last 10. This is a breakout-then-pullback filter.
    seg10 = candles[max(0, n - 10):]
    lo10 = min(float(c["low"]) for c in seg10)
    hi10 = max(float(c["high"]) for c in seg10)
    range10_pct = (hi10 / lo10 - 1.0) * 100.0 if lo10 > 0 else 0.0
    range29 = range10_pct >= 29.0
    dead10 = _crossed_recent(closes, e10, 5, False)
    dead20 = _crossed_recent(closes, e20, 5, False)
    near10 = _near(price, e10[last], 2.0)
    near20 = _near(price, e20[last], 2.0)
    psar_rising = bool(psar[last] is not None and psar[last - 1] is not None and float(psar[last]) > float(psar[last - 1]))
    bb10 = _bb_break_recent(closes, bb40, 10)
    record60, record60_idx = _record_volume_recent(volumes, 60, 10)
    b_checks = [
        ("10봉 변동폭≥29%", range29),
        ("선행스팬1·2 상회", cloud_both),
        ("1/10EMA 데드", dead10),
        ("1/20EMA 데드", dead20),
        ("10EMA ±2%", near10),
        ("20EMA ±2%", near20),
        ("PSAR 상승", psar_rising),
        ("BB40/2.2 최근10봉 상향돌파", bb10),
        ("최근10봉 60봉 신고거래량", record60),
    ]
    b_weights = [15, 15, 8, 8, 10, 10, 9, 12, 13]
    b_score = sum(w for w, (_, ok) in zip(b_weights, b_checks) if ok)
    profile_b = _profile(
        "B · 급등후 단기이평 눌림형",
        b_score,
        all(ok for _, ok in b_checks),
        b_checks,
        {
            "range10_pct": range10_pct,
            "cloud_both": cloud_both,
            "dead10": dead10,
            "dead20": dead20,
            "near10": near10,
            "near20": near20,
            "psar_rising": psar_rising,
            "bb40_break_10": bb10,
            "record60_10": record60,
            "record60_index": record60_idx,
        },
    )

    # Photo C ('돈 복사기'): PSAR cross in 5 bars + 5-day avg volume >= 1m
    # + BB40/2.2 breakout in 5 bars + price/EMA112 golden cross in 5 bars
    # + price above both Ichimoku leading spans.
    psar_cross5 = _crossed_recent(closes, psar, 5, True)
    avg5 = mean(volumes[-5:]) if len(volumes) >= 5 else 0.0
    avg5_million = avg5 >= 1_000_000
    bb5 = _bb_break_recent(closes, bb40, 5)
    cross112_5 = _crossed_recent(closes, e112, 5, True)
    c_checks = [
        ("PSAR 최근5봉 상향돌파", psar_cross5),
        ("5봉 평균거래량≥100만", avg5_million),
        ("BB40/2.2 최근5봉 상향돌파", bb5),
        ("1/112EMA 최근5봉 골든", cross112_5),
        ("선행스팬1·2 상회", cloud_both),
    ]
    c_weights = [20, 15, 20, 20, 25]
    c_score = sum(w for w, (_, ok) in zip(c_weights, c_checks) if ok)
    profile_c = _profile(
        "C · 장기선 돌파 모멘텀형",
        c_score,
        all(ok for _, ok in c_checks),
        c_checks,
        {
            "psar_cross5": psar_cross5,
            "avg5_volume": avg5,
            "bb40_break_5": bb5,
            "cross112_5": cross112_5,
            "cloud_both": cloud_both,
        },
    )

    profiles = {"A": profile_a, "B": profile_b, "C": profile_c}
    best_key = max(profiles, key=lambda k: int(profiles[k]["score"]))
    exact = [k for k, item in profiles.items() if item.get("matched")]
    return {
        **profiles,
        "best_key": best_key,
        "best_name": profiles[best_key]["name"],
        "best_score": int(profiles[best_key]["score"]),
        "exact_matches": exact,
    }
