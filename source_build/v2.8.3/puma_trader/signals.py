from __future__ import annotations

from math import sqrt
from statistics import fmean as mean
from typing import List, Optional

from .indicators import hero_eavg


PINK = "#ff33cc"
BLUE = "#1746ff"
RED = "#ff2e2e"


def _ema(values: List[float], period: int) -> List[Optional[float]]:
    """Compatibility wrapper around the single PUMA/영웅문 EAVG engine."""
    return hero_eavg(values, period)


def _bbands_up(values: List[float], period: int = 40, dev: float = 2.2) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0:
        return out
    for i in range(period - 1, len(values)):
        seg = values[i - period + 1:i + 1]
        m = mean(seg)
        variance = sum((x - m) ** 2 for x in seg) / period
        out[i] = m + float(dev) * sqrt(variance)
    return out


def _crossup(values: List[float], target: List[Optional[float]]) -> List[bool]:
    out = [False] * len(values)
    for i in range(1, len(values)):
        a0, a1 = target[i - 1], target[i]
        if a0 is None or a1 is None:
            continue
        out[i] = values[i - 1] <= a0 and values[i] > a1
    return out


def _sar(candles: List[dict], af: float = 0.02, max_af: float = 0.2) -> List[Optional[float]]:
    """Hero/YesLanguage-compatible Parabolic SAR state machine.

    Kiwoom Hero uses SAR(af,maxAF) as a built-in stateful indicator.
    The previous PUMA implementation used a simplified two-bar initialization,
    which can move c>=SAR across different dates.  This version mirrors the
    public Hero-compatible state transition used by YesLanguage conversions:
    direction discovery -> EP activation -> acceleration/cap -> reversal reset.

    User parameters are preserved literally, including af=0.066/maxAF=0.016.
    """
    n = len(candles)
    if n == 0:
        return []

    highs = [float(x["high"]) for x in candles]
    lows = [float(x["low"]) for x in candles]
    closes = [float(x["close"]) for x in candles]
    out: List[Optional[float]] = [None] * n

    direction = 0
    sar_value = closes[0]
    af_value = 0.02
    high_value = highs[0]
    low_value = lows[0]
    ep = 0.0
    out[0] = sar_value

    for i in range(1, n):
        high = highs[i]
        low = lows[i]
        close = closes[i]
        prev_close = closes[i - 1]

        if ep != 0.0:
            if direction == 1:
                ep = high_value
                sar_value = sar_value + af_value * (ep - sar_value)
                if high > high_value:
                    high_value = high
                    af_value = af_value + float(af)
                    if af_value >= float(max_af):
                        af_value = float(max_af)
                if low < sar_value:
                    direction = -1
                    sar_value = ep
                    af_value = 0.0
                    ep = 0.0
                    low_value = low
            else:
                ep = low_value
                sar_value = sar_value + af_value * (ep - sar_value)
                if low < low_value:
                    low_value = low
                    af_value = af_value + float(af)
                    if af_value >= float(max_af):
                        af_value = float(max_af)
                if high > sar_value:
                    direction = 1
                    sar_value = ep
                    af_value = 0.0
                    ep = 0.0
                    high_value = high
        else:
            # Hero-style direction discovery before SAR becomes active.
            if direction == 0:
                if close > prev_close:
                    direction = 1
                elif close < prev_close:
                    direction = -1
                high_value = max(high_value, high)
                low_value = min(low_value, low)
            else:
                # First bar after direction discovery activates EP/AF.
                if direction == 1:
                    ep = high_value
                    af_value = float(af)
                    sar_value = sar_value + af_value * (ep - sar_value)
                    if high > high_value:
                        high_value = high
                        af_value = af_value + float(af)
                        if af_value >= float(max_af):
                            af_value = float(max_af)
                else:
                    ep = low_value
                    af_value = float(af)
                    sar_value = sar_value + af_value * (ep - sar_value)
                    if low < low_value:
                        low_value = low
                        af_value = af_value + float(af)
                        if af_value >= float(max_af):
                            af_value = float(max_af)

                # Immediate reversal check on activation bar.
                if direction == 1 and low < sar_value:
                    direction = -1
                    sar_value = ep
                    af_value = 0.0
                    ep = 0.0
                    low_value = low
                elif direction == -1 and high > sar_value:
                    direction = 1
                    sar_value = ep
                    af_value = 0.0
                    ep = 0.0
                    high_value = high

        out[i] = sar_value

    return out

LONG_TREND_SUPPRESS_DISPARITY_224 = 108.0


def long_trend_suppression_mask(
    candles: List[dict],
    e112: List[Optional[float]] | None = None,
    e224: List[Optional[float]] | None = None,
    e448: List[Optional[float]] | None = None,
) -> List[bool]:
    """Suppress bottom/reversal overlays in an already extended long-MA uptrend.

    User rule:
      EMA112 > EMA224 > EMA448 (112+ long MAs in bullish order)
      AND price is already extended upward.

    The existing Bowl-3 rule already treats > +8% from EMA224 as overextended,
    so the same established boundary is reused here instead of inventing a
    second distance rule.
    """
    n = len(candles)
    if not n:
        return []
    closes = [float(x["close"]) for x in candles]
    e112 = e112 if e112 is not None else _ema(closes, 112)
    e224 = e224 if e224 is not None else _ema(closes, 224)
    e448 = e448 if e448 is not None else _ema(closes, 448)
    out = [False] * n
    for i in range(n):
        a = e112[i] if i < len(e112) else None
        b = e224[i] if i < len(e224) else None
        d = e448[i] if i < len(e448) else None
        if a is None or b is None or d is None or float(b) <= 0:
            continue
        ordered = float(a) > float(b) > float(d)
        disparity224 = closes[i] / float(b) * 100.0
        out[i] = bool(
            ordered
            and closes[i] > float(a)
            and disparity224 > LONG_TREND_SUPPRESS_DISPARITY_224
        )
    return out


def build_arrow_signals(candles: List[dict]) -> dict:
    """Exact user formulas translated from the supplied 영웅문 signal settings.

    Pink:
      a=crossup(c,bbandsup(Period,D1));
      b/b2/b3=crossup(c,eavg(c,112/224/448));
      if(b or b2 or b3,a,0)
      Period=40, D1=2.2

    Blue:
      a=c >= SAR(af,maxAF);
      b=crossup(c,bbandsup(40,2.2)) and crossup(c,eavg(c,Period1));
      if(a,b,0)
      Period1=112, af=0.066, maxAF=0.016

    Red:
      a=c >= SAR(af,maxAF);
      b=crossup(c,eavg(c,Period1));
      if(a,b,0)
      Period1=224, af=0.066, maxAF=0.016

    Black (user-supplied exact HTS formula):
      Disparity(Period) <= Percent
      && CrossUp(c, BBandsUp(Period1,D1))
      && V > eavg(V,Period2) * Multiple
      && V > V(1) * Multiple
      && eavg(c,Period3) >= eavg(c,Period4)
      Period=224, Percent=109, Period1=40, D1=2.2,
      Period2=40, Multiple=1.5, Period3=1, Period4=112
    """
    n = len(candles)
    if n == 0:
        return {
            "signal_pink_raw": [], "signal_blue_raw": [], "signal_red_raw": [], "signal_black_raw": [],
            "signal_pink": [], "signal_blue": [], "signal_red": [], "signal_black": [],
            "signal_sar": [], "signal_bb40_22": [],
            "long_trend_suppressed": [], "long_trend_suppressed_now": False,
        }

    c = [float(x["close"]) for x in candles]
    v = [float(x["volume"]) for x in candles]
    e112 = _ema(c, 112)
    e224 = _ema(c, 224)
    e448 = _ema(c, 448)
    bb = _bbands_up(c, 40, 2.2)
    vema40 = _ema(v, 40)
    sar = _sar(candles, 0.066, 0.016)

    x_bb = _crossup(c, bb)
    x112 = _crossup(c, e112)
    x224 = _crossup(c, e224)
    x448 = _crossup(c, e448)

    pink_raw = [False] * n
    blue_raw = [False] * n
    red_raw = [False] * n
    black_raw = [False] * n
    for i in range(n):
        sar_ok = sar[i] is not None and c[i] >= float(sar[i])

        # if(b or b2 or b3,a,0)
        pink_raw[i] = bool((x112[i] or x224[i] or x448[i]) and x_bb[i])

        # if(a,b,0)
        blue_raw[i] = bool(sar_ok and x_bb[i] and x112[i])

        # if(a,b,0)
        red_raw[i] = bool(sar_ok and x224[i])

        # 검정 화살표: 사용자가 제공한 영웅문 원식 그대로.
        # Disparity(224) <= 109
        # && CrossUp(c, BBandsUp(40,2.2))
        # && V > eavg(V,40)*1.5
        # && V > V(1)*1.5
        # && eavg(c,1) >= eavg(c,112)
        if i > 0 and e224[i] is not None and e112[i] is not None and vema40[i] is not None:
            # User chart rule: all price moving averages are exponential.
            # Therefore 224-period disparity is measured against EAVG/EMA224.
            disparity224 = c[i] / float(e224[i]) * 100.0 if float(e224[i]) else 999.0
            black_raw[i] = bool(
                disparity224 <= 109.0
                and x_bb[i]
                and v[i] > float(vema40[i]) * 1.5
                and v[i] > v[i - 1] * 1.5
                and c[i] >= float(e112[i])
            )
    suppressed = long_trend_suppression_mask(candles, e112, e224, e448)
    pink = [bool(v and not suppressed[i]) for i, v in enumerate(pink_raw)]
    blue = [bool(v and not suppressed[i]) for i, v in enumerate(blue_raw)]
    red = [bool(v and not suppressed[i]) for i, v in enumerate(red_raw)]
    black = [bool(v and not suppressed[i]) for i, v in enumerate(black_raw)]

    return {
        # raw = user's literal four formulas, before PUMA's requested context filter.
        "signal_pink_raw": pink_raw,
        "signal_blue_raw": blue_raw,
        "signal_red_raw": red_raw,
        "signal_black_raw": black_raw,
        # display/usage signals after the long-MA bullish/overextended exclusion.
        "signal_pink": pink,
        "signal_blue": blue,
        "signal_red": red,
        "signal_black": black,
        "signal_sar": sar,
        "signal_bb40_22": bb,
        "long_trend_suppressed": suppressed,
        "long_trend_suppressed_now": bool(suppressed[-1]) if suppressed else False,
    }


def latest_signal_reason(series: dict) -> str:
    candles = series.get("candles") or []
    if not candles:
        return "화살표 없음"
    i = len(candles) - 1
    if bool(series.get("long_trend_suppressed_now")):
        return "112>224>448 정배열 + 224EMA 대비 +8% 초과 · 화살표/바닥형 지표 제외"
    names = []
    if i < len(series.get("signal_pink", [])) and series["signal_pink"][i]:
        names.append("분홍: BB상단40/2.2 + EMA112/224/448 중 하나 동시 상향돌파")
    if i < len(series.get("signal_blue", [])) and series["signal_blue"][i]:
        names.append("파랑: SAR 위 + BB상단40/2.2 + EMA112 동시 상향돌파")
    if i < len(series.get("signal_red", [])) and series["signal_red"][i]:
        names.append("빨강: SAR 위 + EMA224 상향돌파")
    if i < len(series.get("signal_black", [])) and series["signal_black"][i]:
        names.append("검정: 224이격≤109% + BB상단40/2.2 돌파 + 거래량 40EMA·전봉 대비 1.5배 + EMA112 위")
    return " / ".join(names) if names else "현재봉 화살표 없음"
