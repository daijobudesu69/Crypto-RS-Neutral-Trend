"""Stage 2 — dissect cross-sectional momentum long/short on IS only (2020-07 .. 2024-12)."""
import numpy as np, pandas as pd
import lab

P = lab.load_panel("binance", "1d")
C = P["close"]
vol = lab.ewm_vol(P, 30)
IS = dict(start="2020-07-01", end="2024-12-31")
rows = []


def xs_weights(score, U, q=0.2, nfix=None, invvol=False, gross=1.0):
    s = score.where(U)
    rk = s.rank(axis=1, pct=True) if nfix is None else s.rank(axis=1, ascending=False)
    cnt = s.notna().sum(axis=1)
    if nfix is None:
        L = (rk >= 1 - q); S = (rk <= q)
    else:
        L = rk <= nfix
        S = rk.gt(cnt - nfix, axis=0)
    wl = L.astype(float); ws = S.astype(float)
    if invvol:
        wl = wl / vol; ws = ws / vol
    wl = wl.div(wl.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * gross / 2
    ws = ws.div(ws.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * gross / 2
    return wl, ws


def run(name, W, extra=None, cost=0.0007):
    bt = lab.backtest(W, P, cost=cost, **IS)
    m = lab.metrics(bt["net"], name)
    m["t"] = lab.tstat_daily(bt["net"]); m["turn"] = bt["turn"].mean(); m["fund_ann"] = bt["fund"].mean() * 365
    for yr, v in lab.yearly(bt["net"]).items():
        m[f"y{yr}"] = v
    if extra:
        m.update(extra)
    rows.append(m)
    ys = " ".join(f"{v*100:6.0f}" for k, v in m.items() if str(k).startswith("y20"))
    print(lab.fmt(m), f"t {m['t']:.2f} turn {m['turn']:.2f} fund {m['fund_ann']*100:5.1f}% | {ys}", flush=True)
    return bt


U = {n: lab.universe_mask(P, top=n, min_hist=200) for n in [15, 20, 30, 50]}
mom = {L: C / C.shift(L) - 1 for L in [3, 5, 7, 10, 14, 21, 28, 42, 56, 90]}

print("--- leg decomposition, L14 top30 q20")
wl, ws = xs_weights(mom[14], U[30])
run("long leg only (0.5x)", wl)
run("short leg only (0.5x)", -ws)
run("LS", wl - ws)

print("--- lookback x universe (q20, EW)")
for n in [15, 20, 30, 50]:
    for L in [5, 7, 10, 14, 21, 28, 42, 56, 90]:
        wl, ws = xs_weights(mom[L], U[n])
        run(f"XS L{L} top{n}", wl - ws, {"L": L, "top": n, "q": 0.2, "kind": "raw"})

print("--- risk-adjusted momentum (ret/vol), ensemble")
ens = sum(mom[L].rank(axis=1, pct=True) for L in [7, 14, 28, 56]) / 4
for n in [20, 30, 50]:
    wl, ws = xs_weights(ens, U[n])
    run(f"XS ens7-56 top{n}", wl - ws, {"top": n, "kind": "ens"})
    wl, ws = xs_weights(ens, U[n], invvol=True)
    run(f"XS ens7-56 top{n} invvol", wl - ws, {"top": n, "kind": "ens_iv"})
for L in [14, 28]:
    ra = mom[L] / vol
    wl, ws = xs_weights(ra, U[30])
    run(f"XS riskadj L{L} top30", wl - ws)

print("--- residual momentum vs BTC (beta 60d)")
r = C.pct_change(fill_method=None)
beta = r.rolling(60, min_periods=40).cov(r["BTC"]).div(r["BTC"].rolling(60, min_periods=40).var(), axis=0)
for L in [14, 28]:
    res = (r - beta.mul(r["BTC"], axis=0)).rolling(L).sum()
    wl, ws = xs_weights(res, U[30])
    run(f"XS residual L{L} top30", wl - ws)

print("--- quantile")
for q in [0.1, 0.2, 0.3, 0.5]:
    wl, ws = xs_weights(mom[14], U[30], q=q)
    run(f"XS L14 top30 q{q}", wl - ws)
for nf in [3, 5]:
    wl, ws = xs_weights(mom[14], U[30], nfix=nf)
    run(f"XS L14 top30 n{nf}", wl - ws)

pd.DataFrame(rows).to_csv(lab.os.path.join(lab.RES, "stage2_xs_is.csv"), index=False)
