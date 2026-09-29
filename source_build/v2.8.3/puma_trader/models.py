from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass
class StrategySettings:
    timeframe_min: int = 5
    # NXT 프리마켓 08:00부터 검색과 실제 자동매매를 함께 시작한다.
    # 08:50~09:00 거래 공백에는 신규주문을 보내지 않고, 09:00부터 정규장 흐름을 이어 본다.
    scan_start: str = "08:00"
    trade_start: str = "08:00"
    nxt_premarket_end: str = "08:50"
    scan_end: str = "10:00"
    min_change_pct: float = 0.5
    max_change_pct: float = 12.0
    volume_ratio_min: float = 2.0
    use_ma_stack: bool = True
    ma_fast: int = 5
    ma_mid: int = 20
    ma_slow: int = 60
    use_breakout: bool = True
    breakout_lookback: int = 20
    use_rsi: bool = True
    rsi_min: float = 50.0
    rsi_max: float = 78.0

    # 후보 종목 공급원
    candidate_source: str = "HERO4"  # WATCHLIST / HERO4 / BOTH
    hero_condition_seq: str = ""
    hero_condition_name: str = ""
    hero_condition_names: list[str] = field(default_factory=lambda: [
        "단타단타(시원놈)",
        "5분봉_단타(시원놈)",
        "단타1",
        "시초가1번",
        "시초가1-1번",
        "시초가2번",
        "시초가멀티",
    ])
    hero_secondary_filter: bool = True
    hero_entry_only: bool = False
    puma_secondary_min_score: int = 3

    # 사용자 전용 가보자 단타
    gabojago_enabled: bool = True
    gabojago_daily_volume_ratio: float = 3.0
    gabojago_min_stop_gap_pct: float = 0.5
    # 1차 차 조기진입: 영 고점에서 65% 이상 되돌린 깊은 눌림만 차 후보로 본다.
    # 가격 기준으로는 B < 현재가 <= B + (H-B)*0.35.
    gabojago_cha_max_ratio: float = 0.35
    # 진행 중 현재봉을 차로 조기판정할 때, 영 구간 평균 초당 거래량 대비
    # 현재봉 초당 거래량이 이 배수 이하여야 거래량 둔화로 인정한다.
    gabojago_cha_volume_pace_ratio: float = 1.00
    # 봉 시작 직후 노이즈를 피하기 위한 최소 실시간 관찰시간(초).
    gabojago_cha_min_live_seconds: int = 20
    gabojago_partial_profit_pct: float = 4.0
    # 추세추적: +4%에서 일부만 확보하고 나머지는 높아지는 차 저점을 따라간다.
    gabojago_trend_tracking_enabled: bool = True
    gabojago_partial_sell_ratio: float = 0.25
    gabojago_trend_force_exit_time: str = "15:00"
    gabojago_remainder_band_pct: float = 2.0  # 추세추적 OFF일 때만 쓰는 레거시 값
    gabojago_force_exit_time: str = "13:00"  # 레거시 모드 전용

    # 주문 / 리스크
    # 1차 시드 구간: 50만원에서 시작해 현재 시드를 다음 매매에 전액 재투입.
    # 300만원 도달 전까지 수익/손실을 그대로 복리 반영한다.
    order_budget: int = 500_000  # 레거시/수동 표시값
    compound_seed_enabled: bool = True
    seed_initial_capital: int = 500_000
    seed_phase1_target: int = 3_000_000
    daily_loss_limit_pct: float = -4.0
    max_positions: int = 1
    cooldown_min: int = 10
    max_daily_orders: int = 10
    account_sync_sec: int = 5
    order_exchange: str = "KRX"  # KRX / NXT / SOR

    # 매도
    take_profit_pct: float = 4.0
    stop_loss_pct: float = -2.0
    trailing_enabled: bool = True
    trailing_start_pct: float = 2.0
    trailing_gap_pct: float = 1.2
    force_exit_enabled: bool = True
    force_exit_time: str = "15:00"

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class Position:
    code: str
    name: str
    qty: int
    entry_price: float
    highest_price: float
    opened_at: str
    broker_order_no: str = ""
    stop_price: float = 0.0
    entry_kind: str = ""
    partial_taken: bool = False
    partial_price: float = 0.0
    partial_time: str = ""
    remainder_down_trigger_bar: str = ""
    remainder_down_wait_bar: str = ""

    def pnl_pct(self, current_price: float) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (current_price / self.entry_price - 1.0) * 100.0


@dataclass
class SignalResult:
    passed: bool
    reason: str
    score: int = 0
    current_price: float = 0.0
    change_pct: float = 0.0
    volume_ratio: float = 0.0
    rsi: Optional[float] = None
