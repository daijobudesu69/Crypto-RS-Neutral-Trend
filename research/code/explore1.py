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

# ---------- H1/H2 time-series momentum (ensemble of lookbacks), vol-scaled, top-30
for U, un in [(U30, "30"), (U15, "15")]:
    n = U.sum(axis=1).replace(0, np.nan)
    sigs = []
    for L in [10, 20, 40, 80, 160]:
        sigs.append(np.sign(C / C.shift(L) - 1))
    S = sum(sigs) / len(sigs)  # in [-1,1]
    base = (S * (0.40 / vol)).where(U, 0).fillna(0).clip(-1, 1)   # each coin aims 40% vol
    base = base.div(n, axis=0).fillna(0)                          # equal risk budget across coins
    run(f"H1 TSMOM LS ens top{un}", base)
    run(f"H2 TSMOM long-only ens top{un}", base.clip(lower=0))
    # EMA-cross ensemble
    e = []
    for f_, s_ in [(8, 32), (16, 64), (32, 128)]:
        e.append(np.sign(C.ewm(span=f_).mean() - C.ewm(span=s_).mean()))
    S2 = sum(e) / 3
    w2 = (S2 * (0.40 / vol)).where(U, 0).fillna(0).clip(-1, 1).div(n, axis=0).fillna(0)
    run(f"H1b EMA-ens LS top{un}", w2)
    run(f"H2b EMA-ens long-only top{un}", w2.clip(lower=0))

# ---------- H3 cross-sectional momentum, market neutral (rank-based), top30
for L in [7, 14, 28, 56]:
    mom = (C / C.shift(L) - 1).where(U30)
    rk = mom.rank(axis=1, pct=True)
    w = ((rk >= 0.8).astype(float) - (rk <= 0.2).astype(float)).where(U30, 0)
    k = (w != 0).sum(axis=1).replace(0, np.nan)
    run(f"H3 XS-mom LS L{L}", w.div(k, axis=0).fillna(0))

# ---------- H4 cross-sectional short-term reversal (market neutral), top30
for L in [1, 3, 5]:
    mom = (C / C.shift(L) - 1).where(U30)
    rk = mom.rank(axis=1, pct=True)
    w = ((rk <= 0.2).astype(float) - (rk >= 0.8).astype(float)).where(U30, 0)
    k = (w != 0).sum(axis=1).replace(0, np.nan)
    run(f"H4 XS-reversal L{L}", w.div(k, axis=0).fillna(0))

# ---------- H5 low-vol anomaly: long low vol, short high vol (dollar neutral)
rk = vol.where(U30).rank(axis=1, pct=True)
w = ((rk <= 0.3).astype(float) - (rk >= 0.7).astype(float)).where(U30, 0)
k = (w != 0).sum(axis=1).replace(0, np.nan)
run("H5 low-vol minus high-vol", w.div(k, axis=0).fillna(0))

# ---------- H7 post-listing short: short coins in their first 90 days (any liquidity), equal weight, max 10% each
age = C.notna().cumsum()
newc = (age >= 3) & (age <= 60) & C.notna()
k = newc.sum(axis=1).replace(0, np.nan)
run("H7 short new listings d3-60", (-newc.astype(float)).div(k.clip(lower=10), axis=0).fillna(0))
newc = (age >= 3) & (age <= 120) & C.notna()
k = newc.sum(axis=1).replace(0, np.nan)
run("H7 short new listings d3-120", (-newc.astype(float)).div(k.clip(lower=10), axis=0).fillna(0))

# ---------- H8 overextension fade: coin outperformed BTC by > X% in 3 days -> short 3 days
rel3 = (C / C.shift(3)).div(C["BTC"] / C["BTC"].shift(3), axis=0) - 1
for X in [0.3, 0.5]:
    ev = (rel3 > X) & U30
    hold = ev.astype(float).rolling(3, min_periods=1).max().astype(bool) & C.notna()
    run(f"H8 fade +{int(X*100)}% vs BTC 3d", -(hold.astype(float) * 0.1))
    ev = (rel3 < -X) & U30
    hold = ev.astype(float).rolling(3, min_periods=1).max().astype(bool) & C.notna()
    run(f"H8b buy -{int(X*100)}% vs BTC 3d", (hold.astype(float) * 0.1))

# ---------- H9 breadth regime timing on EW basket
above = (C > C.rolling(50).mean()).where(U30)
br = above.sum(axis=1) / U30.sum(axis=1)
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

pd.DataFrame(rows).to_csv(lab.os.path.join(lab.RES, "stage1_is.csv"), index=False)
