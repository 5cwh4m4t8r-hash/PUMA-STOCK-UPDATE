from __future__ import annotations
from datetime import datetime
from statistics import mean
from .models import StrategySettings, SignalResult, Position


def _num(v):
    try:
        return abs(float(str(v).replace(",", "").strip()))
    except Exception:
        return 0.0


def sma(values, period):
    if len(values) < period or period <= 0:
        return None
    return sum(values[-period:]) / period


def ema_last(values, period):
    """PUMA 전 전략의 기본 이평은 EMA(지수이동평균)로 통일."""
    if len(values) < period or period <= 0:
        return None
    prev = sum(values[:period]) / period
    k = 2.0 / (period + 1.0)
    for v in values[period:]:
        prev = v * k + prev * (1.0 - k)
    return prev


def rsi(values, period=14):
    if len(values) < period + 1:
        return None
    gains, losses = [], []
    for a, b in zip(values[-period-1:-1], values[-period:]):
        d = b - a
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def in_scan_window(settings: StrategySettings, now=None):
    now = now or datetime.now()
    hm = now.strftime("%H:%M")
    return settings.scan_start <= hm <= settings.scan_end


def evaluate_buy(candles, settings: StrategySettings) -> SignalResult:
    if len(candles) < max(settings.ma_slow, settings.breakout_lookback, 20) + 2:
        return SignalResult(False, "데이터 부족")

    candles = list(reversed(candles))  # API 최신순 -> 시간순
    closes = [_num(c.get("cur_prc")) for c in candles]
    highs = [_num(c.get("high_pric")) for c in candles]
    volumes = [_num(c.get("trde_qty")) for c in candles]
    current = closes[-1]
    prev_close = closes[-2] or current
    change_pct = (current / prev_close - 1) * 100 if prev_close else 0.0

    # 장중 등락률이 없을 경우 최근 봉 대비 변화율을 사용한다.
    if not (settings.min_change_pct <= change_pct <= settings.max_change_pct):
        return SignalResult(False, f"등락률 {change_pct:.2f}%", current_price=current, change_pct=change_pct)

    avg_vol = mean(volumes[-11:-1]) if len(volumes) >= 11 else mean(volumes[:-1])
    vol_ratio = (volumes[-1] / avg_vol) if avg_vol else 0.0
    if vol_ratio < settings.volume_ratio_min:
        return SignalResult(False, f"거래량 {vol_ratio:.2f}배", current_price=current, change_pct=change_pct, volume_ratio=vol_ratio)

    score = 1
    if settings.use_ma_stack:
        fast = ema_last(closes, settings.ma_fast)
        mid = ema_last(closes, settings.ma_mid)
        slow = ema_last(closes, settings.ma_slow)
        if None in (fast, mid, slow) or not (current >= fast > mid > slow):
            return SignalResult(False, "이평 정배열 불충족", score, current, change_pct, vol_ratio)
        score += 1

    if settings.use_breakout:
        prior_high = max(highs[-settings.breakout_lookback-1:-1])
        if current <= prior_high:
            return SignalResult(False, "돌파 불충족", score, current, change_pct, vol_ratio)
        score += 1

    cur_rsi = rsi(closes)
    if settings.use_rsi:
        if cur_rsi is None or not (settings.rsi_min <= cur_rsi <= settings.rsi_max):
            return SignalResult(False, f"RSI {cur_rsi if cur_rsi is not None else '-'}", score, current, change_pct, vol_ratio, cur_rsi)
        score += 1

    return SignalResult(True, "매수조건 충족", score, current, change_pct, vol_ratio, cur_rsi)


def evaluate_sell(position: Position, current_price: float, settings: StrategySettings, now=None):
    pnl = position.pnl_pct(current_price)
    position.highest_price = max(position.highest_price, current_price)

    stop_price = float(getattr(position, "stop_price", 0) or 0)
    partial_taken = bool(getattr(position, "partial_taken", False))
    now = now or datetime.now()

    if stop_price > 0:
        # 가보자 손절은 진입형태에 따라 구조적으로 올라간다.
        # 차 눌림: 기준봉 시가 / 전고 몸통돌파: 직전 차 눌림 저점.
        if current_price <= stop_price:
            entry_kind = str(getattr(position, "entry_kind", "") or "")
            stop_label = "직전 차 저점" if entry_kind == "BODY_REBREAK" else "기준봉 시가"
            return True, f"가보자 {stop_label} 이탈 손절 {current_price:,.0f} <= {stop_price:,.0f}"

        # +4% 최초 도달은 엔진에서 절반익절 처리.
        if not partial_taken:
            if pnl >= settings.take_profit_pct:
                return True, f"가보자 1차 절반익절 대기 {pnl:.2f}%"
        else:
            # 절반익절 이후 잔량 규칙:
            # 1) 절반익절 가격보다 위로 가면 추가상승 확인 -> 전량매도
            # 2) 절반익절 가격보다 아래로 가면 하락 전환 -> 전량매도
            # 3) 11:00 도달 시 방향과 무관하게 잔량 종료
            partial_price = float(getattr(position, "partial_price", 0) or 0)
            if partial_price <= 0:
                partial_price = position.entry_price * (1.0 + settings.take_profit_pct / 100.0)

            cutoff = str(getattr(settings, "gabojago_remainder_exit_time", "11:00") or "11:00")
            if now.strftime("%H:%M") >= cutoff:
                return True, f"가보자 {cutoff} 잔량 전량매도 · 기준 {partial_price:,.0f}"

            if current_price > partial_price:
                return True, f"가보자 절반익절 후 추가상승 전량매도 {current_price:,.0f} > {partial_price:,.0f}"
            if current_price < partial_price:
                return True, f"가보자 절반익절 후 하락 전량매도 {current_price:,.0f} < {partial_price:,.0f}"

            return False, f"가보자 잔량 대기 · 기준 {partial_price:,.0f} · {cutoff} 이전"

    else:
        # 비-가보자 기존 포지션 규칙 유지.
        if pnl <= settings.stop_loss_pct:
            return True, f"손절 {pnl:.2f}%"
        if pnl >= settings.take_profit_pct:
            return True, f"익절 {pnl:.2f}%"
        if settings.trailing_enabled and pnl >= settings.trailing_start_pct:
            drop_from_high = (current_price / position.highest_price - 1) * 100 if position.highest_price else 0
            if drop_from_high <= -abs(settings.trailing_gap_pct):
                return True, f"트레일링 {drop_from_high:.2f}%"

    if settings.force_exit_enabled and now.strftime("%H:%M") >= settings.force_exit_time:
        return True, "장 종료 전 청산"
    return False, "보유"
