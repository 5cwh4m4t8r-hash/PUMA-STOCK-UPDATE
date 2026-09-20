from __future__ import annotations

from math import sqrt
from statistics import fmean as mean
from typing import List, Optional


PINK = "#ff33cc"
BLUE = "#1746ff"
RED = "#ff2e2e"


def _ema(values: List[float], period: int) -> List[Optional[float]]:
    """영웅문 EAVG 호환 방식.

    첫 유효값 자체를 첫 지수평균으로 두고 이후 모든 봉을
    alpha=2/(period+1)로 누적한다. 기간만큼 기다린 뒤 SMA를 seed로
    쓰는 일반 라이브러리 방식은 장기 112/224/448 교차 시점을
    영웅문과 다르게 만들 수 있어 사용하지 않는다.
    """
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if period <= 0 or n == 0:
        return out
    k = 2.0 / (period + 1.0)
    prev = float(values[0])
    out[0] = prev
    for i in range(1, n):
        prev = float(values[i]) * k + prev * (1.0 - k)
        out[i] = prev
    return out


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


def _sar(candles: List[dict], af: float = 0.066, max_af: float = 0.016) -> List[Optional[float]]:
    """Parabolic SAR compatible implementation for the user's SAR(af,maxAF) inputs.

    Parameters are kept literally as supplied by the user/HTS formula.
    """
    n = len(candles)
    if n == 0:
        return []
    if n == 1:
        return [float(candles[0]["low"])]

    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    closes = [float(c["close"]) for c in candles]

    out: List[Optional[float]] = [None] * n
    up = closes[1] >= closes[0]
    sar = lows[0] if up else highs[0]
    ep = max(highs[0], highs[1]) if up else min(lows[0], lows[1])
    af_value = float(af)
    out[0] = sar

    for i in range(1, n):
        sar = sar + af_value * (ep - sar)

        if up:
            sar = min(sar, lows[i - 1])
            if i >= 2:
                sar = min(sar, lows[i - 2])
            if lows[i] < sar:
                up = False
                sar = ep
                ep = lows[i]
                af_value = float(af)
            elif highs[i] > ep:
                ep = highs[i]
                af_value = min(af_value + float(af), float(max_af))
        else:
            sar = max(sar, highs[i - 1])
            if i >= 2:
                sar = max(sar, highs[i - 2])
            if highs[i] > sar:
                up = True
                sar = ep
                ep = highs[i]
                af_value = float(af)
            elif lows[i] < ep:
                ep = lows[i]
                af_value = min(af_value + float(af), float(max_af))
        out[i] = sar
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
            "signal_pink": [], "signal_blue": [], "signal_red": [], "signal_black": [],
            "signal_sar": [], "signal_bb40_22": [],
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

    pink = [False] * n
    blue = [False] * n
    red = [False] * n
    black = [False] * n
    for i in range(n):
        sar_ok = sar[i] is not None and c[i] >= float(sar[i])

        # if(b or b2 or b3,a,0)
        pink[i] = bool((x112[i] or x224[i] or x448[i]) and x_bb[i])

        # if(a,b,0)
        blue[i] = bool(sar_ok and x_bb[i] and x112[i])

        # if(a,b,0)
        red[i] = bool(sar_ok and x224[i])

        # 검정 화살표: 사용자가 제공한 영웅문 원식 그대로.
        # Disparity(224) <= 109
        # && CrossUp(c, BBandsUp(40,2.2))
        # && V > eavg(V,40)*1.5
        # && V > V(1)*1.5
        # && eavg(c,1) >= eavg(c,112)
        if i > 0 and e224[i] is not None and e112[i] is not None and vema40[i] is not None:
            disparity224 = c[i] / float(e224[i]) * 100.0 if float(e224[i]) else 999.0
            black[i] = bool(
                disparity224 <= 109.0
                and x_bb[i]
                and v[i] > float(vema40[i]) * 1.5
                and v[i] > v[i - 1] * 1.5
                and c[i] >= float(e112[i])
            )
    return {
        "signal_pink": pink,
        "signal_blue": blue,
        "signal_red": red,
        "signal_black": black,
        "signal_sar": sar,
        "signal_bb40_22": bb,
    }


def latest_signal_reason(series: dict) -> str:
    candles = series.get("candles") or []
    if not candles:
        return "화살표 없음"
    i = len(candles) - 1
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
