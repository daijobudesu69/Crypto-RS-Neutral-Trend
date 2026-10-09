"""Stage 1 — screen hypothesis families on Binance IS 2020-2024 only (OOS untouched).
All signals use OHLCV only (available from HYPE candles). Funding is a cost, never a signal."""
import numpy as np, pandas as pd
import lab

P = lab.load_panel("binance", "1d")
C = P["close"]
r = C.pct_change(fill_method=None)
U30 = lab.universe_mask(P, top=30, min_hist=200)
U15 = lab.universe_mask(P, top=15, min_hist=200)
vol = lab.ewm_vol(P, 30)
IS = dict(start="2020-07-01", end="2024-12-31")
rows = []


def run(name, W, cost=0.0007):
    bt = lab.backtest(W, P, cost=cost, **IS)
    m = lab.metrics(bt["net"], name)
    g = lab.metrics(bt["gross"], name)
    m["sharpe_gross"] = g["sharpe"]
    m["t"] = lab.tstat_daily(bt["net"])
    m["turn_d"] = bt["turn"].mean()
    m["exp"] = bt["gross_exp"].mean()
    m["fund_ann"] = bt["fund"].mean() * 365
    y = lab.yearly(bt["net"])
    for yr, v in y.items():
        m[f"y{yr}"] = v
    rows.append(m)
    print(lab.fmt(m), f" t {m['t']:.2f} SRg {m['sharpe_gross']:.2f} turn {m['turn_d']:.3f} exp {m['exp']:.2f}", flush=True)
    return bt


def volscale(sig, U, tv=0.15, cap=0.25):
    """per-coin weight = sig * tv/vol, normalised so the sum of |w| across eligible coins <= 1 * (n scale)."""
    w = (sig * (tv / vol)).where(U, 0.0).clip(-cap, cap).fillna(0.0)
    return w


# ---------- B0 baselines
n30 = U30.sum(axis=1).replace(0, np.nan)
run("B0 EW long top30", U30.astype(float).div(n30, axis=0).fillna(0))
run("B0 BTC hold", pd.DataFrame({"BTC": 1.0}, index=C.index))

# ---------- H9 breadth regime timing on EW basket
above = (C > C.rolling(50).mean()).where(U30)
br = above.sum(axis=1) / U30.sum(axis=1).replace(0, np.nan)
for th in [0.5, 0.6]:
    reg = (br > th).astype(float)
    run(f"H9 EW long when breadth50>{th}", U30.astype(float).div(n30, axis=0).fillna(0).mul(reg, axis=0))

# ---------- H10 vol-managed BTC
bv = vol["BTC"]
run("H10 BTC vol-target 50%", pd.DataFrame({"BTC": (0.5 / bv).clip(upper=2)}, index=C.index))

# ---------- H11 day-of-week (BTC long only on given weekday)
dow = pd.Series(C.index.dayofweek, index=C.index)
for d in range(7):
    # weight at close of day t earns day t+1 -> choose W[t]=1 if (t+1) weekday == d
    w = ((dow.shift(-1) == d).astype(float)).to_frame("BTC")
    run(f"H11 BTC long on weekday {d}", w, cost=0.0007)

pd.DataFrame(rows).to_csv(lab.os.path.join(lab.RES, "stage1b_is.csv"), index=False)
