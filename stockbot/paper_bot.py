"""Ежедневный сигнал-бот (без автоторговли): python paper_bot.py
Печатает, что купить (просадка >= dip_pct при цене выше SMA200) и когда продавать.
Сделки вы совершаете вручную."""
import yfinance as yf
from config import Config
from strategy import buy_signal

cfg = Config()
slot = cfg.capital_eur / cfg.max_positions
for t in cfg.tickers:
    d = yf.download(t, period="2y", auto_adjust=True, progress=False)
    d = d.rename(columns=str.lower)
    d.columns = [c if isinstance(c, str) else c[0] for c in d.columns]
    if len(d) < cfg.trend_sma + 2:
        continue
    px = float(d["close"].iloc[-1])
    chg = (px / float(d["close"].iloc[-2]) - 1) * 100
    if buy_signal(d, len(d) - 1, cfg):
        print(f"BUY {t}: {chg:+.1f}% за день, цена {px:.2f}. Сумма ~{slot:.0f}€. "
              f"Продать: +{cfg.take_profit_pct}% (~{px*(1+cfg.take_profit_pct/100):.2f}), "
              f"стоп -{cfg.stop_loss_pct}% (~{px*(1-cfg.stop_loss_pct/100):.2f}), "
              f"или через {cfg.max_hold_days} торг. дней.")
    else:
        print(f"-- {t}: {chg:+.1f}% — сигнала нет")
