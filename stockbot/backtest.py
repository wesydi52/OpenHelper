"""Бэктест: python backtest.py [--synthetic]. Вход/выход по цене закрытия."""
import sys
import numpy as np
import pandas as pd
from config import Config
from strategy import buy_signal, exit_reason


def load(tickers, years=5):
    import yfinance as yf
    out = {}
    for t in tickers:
        d = yf.download(t, period=f"{years}y", auto_adjust=True, progress=False)
        if len(d):
            d = d.rename(columns=str.lower)
            d.columns = [c if isinstance(c, str) else c[0] for c in d.columns]
            out[t] = d[["close"]].dropna()
    return out


def synthetic(tickers, n=1300, seed=1):
    rng = np.random.default_rng(seed)
    out = {}
    for t in tickers:
        r = rng.standard_t(4, n) * 0.014 + 0.0006
        out[t] = pd.DataFrame({"close": 100 * np.exp(np.cumsum(r))},
                              index=pd.bdate_range("2021-01-01", periods=n))
    return out


def run(data, cfg: Config):
    cash, pos, trades = cfg.capital_eur, {}, []
    slot = cfg.capital_eur / cfg.max_positions
    dates = sorted(set().union(*[d.index for d in data.values()]))
    equity = []
    for dt in dates:
        for t in list(pos):
            d = data[t]
            if dt not in d.index:
                continue
            p = pos[t]
            p["held"] += 1
            px = d.loc[dt, "close"]
            why = exit_reason(p["entry"], px, p["held"], cfg)
            if why:
                sell = px * (1 - cfg.slippage_pct / 100)
                proceeds = p["qty"] * sell * (1 - cfg.fee_pct / 100)
                cash += proceeds
                trades.append(dict(t=t, date=dt, why=why, days=p["held"],
                                   ret=(proceeds / p["cost"] - 1) * 100))
                del pos[t]
        for t, d in data.items():
            if t in pos or len(pos) >= cfg.max_positions or dt not in d.index:
                continue
            i = d.index.get_loc(dt)
            if buy_signal(d, i, cfg) and cash >= slot * 0.99:
                spend = min(slot, cash)
                buy = d["close"].iloc[i] * (1 + cfg.slippage_pct / 100)
                cost = spend
                qty = spend * (1 - cfg.fee_pct / 100) / buy
                cash -= spend
                pos[t] = dict(entry=buy, qty=qty, held=0, cost=cost)
        mv = sum(p["qty"] * data[t]["close"].asof(dt) for t, p in pos.items())
        equity.append((dt, cash + mv))
    eq = pd.Series(dict(equity))
    return eq, pd.DataFrame(trades)


def report(eq, tr, cfg):
    years = max((eq.index[-1] - eq.index[0]).days / 365, 1e-9)
    tot = eq.iloc[-1] / cfg.capital_eur - 1
    dd = (eq / eq.cummax() - 1).min()
    print(f"Период: {years:.1f} лет | Итог: {eq.iloc[-1]:.0f}€ ({tot*100:+.1f}%) "
          f"| в год ~{((1+tot)**(1/years)-1)*100:+.1f}% | макс. просадка {dd*100:.1f}%")
    if len(tr):
        print(f"Сделок: {len(tr)} | winrate {(tr.ret>0).mean()*100:.0f}% | "
              f"ср. {tr.ret.mean():+.2f}% | ср. срок {tr.days.mean():.1f} дн.")
        print(tr.groupby("why").agg(n=("ret", "size"), avg=("ret", "mean"), days=("days", "mean")).round(2))
    # окна 1..6 месяцев
    for m in range(1, 7):
        w = 21 * m
        r = (eq.shift(-w) / eq - 1).dropna() * 100
        if len(r):
            print(f"{m} мес: медиана {r.median():+.1f}% | P10 {r.quantile(.1):+.1f}% | "
                  f"P90 {r.quantile(.9):+.1f}% | в минусе {(r<0).mean()*100:.0f}% окон")


if __name__ == "__main__":
    cfg = Config()
    data = synthetic(cfg.tickers) if "--synthetic" in sys.argv else load(cfg.tickers)
    eq, tr = run(data, cfg)
    report(eq, tr, cfg)
