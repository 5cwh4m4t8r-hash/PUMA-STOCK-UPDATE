from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass
class StrategySettings:
    timeframe_min: int = 5
    scan_start: str = "08:50"
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
    hero_entry_only: bool = True
    puma_secondary_min_score: int = 3

    # 사용자 전용 가보자 단타
    gabojago_enabled: bool = True
    gabojago_daily_volume_ratio: float = 3.0
    gabojago_min_stop_gap_pct: float = 0.5
    gabojago_partial_profit_pct: float = 4.0
    gabojago_remainder_band_pct: float = 2.0
    gabojago_force_exit_time: str = "13:00"

    # 주문 / 리스크
    order_budget: int = 500_000  # 가보자 자동매수 고정금액
    max_positions: int = 3
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
    force_exit_time: str = "15:20"

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
