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


def evaluate_sell(
    position: Position,
    current_price: float,
    settings: StrategySettings,
    now=None,
    *,
    bar_key: str = "",
    previous_bar_close: float = 0.0,
):
    pnl = position.pnl_pct(current_price)
    position.highest_price = max(position.highest_price, current_price)

    stop_price = float(getattr(position, "stop_price", 0) or 0)
    partial_taken = bool(getattr(position, "partial_taken", False))
    now = now or datetime.now()

    if stop_price > 0:
        # 가보자 손절은 '차 저점'을 기준으로 하고, 추세가 올라가면 손절선도 위로만 이동한다.
        if current_price <= stop_price:
            return True, f"가보자 차 저점 이탈 손절 {current_price:,.0f} <= {stop_price:,.0f}"

        # 당일 단타 최종 안전청산. 추세추적 중에는 장중 고정 목표가로 잔량을 끊지 않는다.
        day_exit = str(getattr(settings, "gabojago_force_exit_time", "15:20") or "15:20")
        if now.strftime("%H:%M") >= day_exit:
            return True, f"가보자 당일 단타 {day_exit} 전량청산"

        partial_target = float(
            getattr(settings, "gabojago_partial_profit_pct", settings.take_profit_pct)
            or settings.take_profit_pct
        )
        trend_tracking = bool(getattr(settings, "gabojago_trend_tracking_enabled", True))

        # +4% 최초 도달의 일부익절은 엔진에서 처리한다.
        if not partial_taken:
            if pnl >= partial_target:
                ratio = float(getattr(settings, "gabojago_partial_sell_ratio", 0.25) or 0.25)
                pct = max(1, int(round(ratio * 100)))
                return False, f"가보자 +{partial_target:.1f}% {pct}% 익절 대기 · 추세추적"
        elif trend_tracking:
            return False, (
                f"가보자 추세추적 보유 · 현재 손절선 {stop_price:,.0f} "
                f"· 새 차 저점 확정 시 손절선 상향"
            )
        else:
            # 레거시 잔량 규칙. 추세추적을 끈 경우에만 사용한다.
            partial_price = float(getattr(position, "partial_price", 0) or 0)
            if partial_price <= 0:
                partial_price = position.entry_price * (1.0 + settings.take_profit_pct / 100.0)

            band_pct = abs(float(getattr(settings, "gabojago_remainder_band_pct", 2.0) or 2.0))
            upper = partial_price * (1.0 + band_pct / 100.0)
            lower = partial_price * (1.0 - band_pct / 100.0)

            if current_price >= upper:
                return True, (
                    f"가보자 잔량 +{band_pct:.1f}% 전량매도 "
                    f"{current_price:,.0f} >= {upper:,.0f} · 기준 {partial_price:,.0f}"
                )

            trigger_bar = str(getattr(position, "remainder_down_trigger_bar", "") or "")
            wait_bar = str(getattr(position, "remainder_down_wait_bar", "") or "")

            if trigger_bar:
                # 이탈이 발생한 봉이 끝난 뒤, 다음 한 봉을 통째로 기다린다.
                if not bar_key or bar_key == trigger_bar:
                    return False, (
                        f"가보자 잔량 -{band_pct:.1f}% 이탈봉 관찰 중 · "
                        f"하단 {lower:,.0f}"
                    )

                if not wait_bar:
                    position.remainder_down_wait_bar = str(bar_key)
                    return False, (
                        f"가보자 잔량 회복 확인봉 관찰 중 · "
                        f"하단 {lower:,.0f}"
                    )

                if bar_key == wait_bar:
                    return False, (
                        f"가보자 잔량 회복 확인봉 관찰 중 · "
                        f"하단 {lower:,.0f}"
                    )

                # wait_bar가 끝난 뒤 새 봉이 시작된 시점:
                # 직전 완료봉 종가로 회복 여부를 확정한다.
                confirm_close = float(previous_bar_close or 0)
                if confirm_close > 0 and confirm_close <= lower:
                    return True, (
                        f"가보자 잔량 -{band_pct:.1f}% 다음봉 미회복 전량매도 · "
                        f"확인봉 종가 {confirm_close:,.0f} <= {lower:,.0f}"
                    )

                # 확인봉 종가가 하단선 위로 회복했으면 다시 정상 보유.
                position.remainder_down_trigger_bar = ""
                position.remainder_down_wait_bar = ""
                return False, (
                    f"가보자 잔량 -{band_pct:.1f}% 회복 확인 · "
                    f"기준 {partial_price:,.0f}"
                )

            if current_price <= lower:
                position.remainder_down_trigger_bar = str(bar_key or now.strftime("%Y%m%d%H%M"))
                position.remainder_down_wait_bar = ""
                return False, (
                    f"가보자 잔량 -{band_pct:.1f}% 이탈 · 다음 5분봉까지 관찰 "
                    f"{current_price:,.0f} <= {lower:,.0f}"
                )

            return False, (
                f"가보자 잔량 보유 · 기준 {partial_price:,.0f} "
                f"범위 {lower:,.0f}~{upper:,.0f}"
            )

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
