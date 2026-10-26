import pandas as pd
from config import Config


def buy_signal(df: pd.DataFrame, i: int, cfg: Config) -> bool:
    """df: колонка 'close'. Сигнал на закрытии дня i."""
    if i < cfg.trend_sma:
        return False
    day_ret = df["close"].iloc[i] / df["close"].iloc[i - 1] - 1
    sma = df["close"].iloc[i - cfg.trend_sma + 1:i + 1].mean()
    return day_ret * 100 <= -cfg.dip_pct and df["close"].iloc[i] > sma


def exit_reason(entry: float, price: float, held: int, cfg: Config):
    pnl = (price / entry - 1) * 100
    if pnl >= cfg.take_profit_pct:
        return "take_profit"
    if pnl <= -cfg.stop_loss_pct:
        return "stop_loss"
    if held >= cfg.max_hold_days:
        return "time_exit"
    return None
