"""Параметры стратегии «покупка на падении» для акций."""
from dataclasses import dataclass, field


@dataclass
class Config:
    tickers: list = field(default_factory=lambda: [
        "NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "AVGO", "ASML"])
    capital_eur: float = 630.0
    dip_pct: float = 4.0          # покупаем, если за день упало на >= 4%
    trend_sma: int = 200          # только если цена выше SMA200 (долгосрочный рост)
    take_profit_pct: float = 6.0  # продаём при +6%
    stop_loss_pct: float = 7.0    # режем убыток при -7%
    max_hold_days: int = 20       # иначе выходим по времени
    max_positions: int = 3        # делим капитал на 3 позиции
    fee_pct: float = 0.1          # комиссия брокера на сделку (в одну сторону)
    slippage_pct: float = 0.05
