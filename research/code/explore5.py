"""Stage 5 — refine sleeve B (risk-adjusted relative strength, market neutral) and sleeve A (trend), IS only."""
import os
import numpy as np, pandas as pd
from numba import njit
import lab

P = lab.load_panel("binance", "1d")
C = P["close"]
r = C.pct_change(fill_method=None)
vol = lab.ewm_vol(P, 30)
IS = dict(start="2020-07-01", end="2024-12-31")
U20 = lab.universe_mask(P, top=20, min_hist=200)
U30 = lab.universe_mask(P, top=30, min_hist=200)
rows = []


def run(name, W, extra=None, cost=0.0007, quiet=False):
    bt = lab.backtest(W, P, cost=cost, **IS)
    m = lab.metrics(bt["net"], name)
    m["t"] = lab.tstat_daily(bt["net"]); m["turn"] = bt["turn"].mean(); m["fund_ann"] = bt["fund"].mean() * 365
    m["gexp"] = bt["gross_exp"].mean(); m["nexp"] = bt["net_exp"].mean()
    m["sr_gross"] = lab.metrics(bt["gross"])["sharpe"]
    for yr, v in lab.yearly(bt["net"]).items():
        m[f"y{yr}"] = v
    if extra:
        m.update(extra)
    rows.append(m)
    if not quiet:
        ys = " ".join(f"{v*100:5.0f}" for k, v in m.items() if str(k).startswith("y20"))
        print(lab.fmt(m), f"t {m['t']:.2f} SRg {m['sr_gross']:.2f} turn {m['turn']:.2f} gexp {m['gexp']:.2f} | {ys}", flush=True)
    return bt


def ra_score(Ls):
    sc = 0
    for L in Ls:
        m = (C / C.shift(L) - 1) / (vol * np.sqrt(L / 365))
        sc = sc + m.rank(axis=1, pct=True)
    return sc / len(Ls)


@njit(cache=True)
def _hyst(rk, n_in, n_out, valid):
    """rk: rank (1 = best) per day x coin (nan = not eligible). Long book: enter if rank<=n_in, stay while rank<=n_out."""
    T, N = rk.shape
    out = np.zeros((T, N))
    for t in range(T):
        for j in range(N):
            if not valid[t, j]:
                continue
            prev = out[t - 1, j] if t > 0 else 0.0
            x = rk[t, j]
            if prev > 0:
                if x <= n_out:
                    out[t, j] = 1.0
            elif x <= n_in:
                out[t, j] = 1.0
    return out


def hyst_book(score, U, n_in, n_out, gross=1.0):
    s = score.where(U)
    valid = s.notna().values
    rl = s.rank(axis=1, ascending=False).fillna(9999).values
    rs = s.rank(axis=1, ascending=True).fillna(9999).values
    L = pd.DataFrame(_hyst(rl, n_in, n_out, valid), index=s.index, columns=s.columns)
    S = pd.DataFrame(_hyst(rs, n_in, n_out, valid), index=s.index, columns=s.columns)
    wl = L.div(L.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * gross / 2
    ws = S.div(S.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * gross / 2
    return wl, ws


SC = ra_score((14, 28))

print("=== B legs (L14-28 RA, top20, 4 in / exit at rank>4 i.e. no buffer)")
wl, ws = hyst_book(SC, U20, 4, 4)
run("B legs: long only (0.5x)", wl)
run("B legs: short only (0.5x)", -ws)
run("B LS no buffer n4", wl - ws)

print("=== B buffer grid (top20 / top30)")
for U, un in [(U20, 20), (U30, 30)]:
    for n_in in [3, 4, 5, 6]:
        for n_out in [n_in, n_in + 2, n_in + 4, n_in + 6]:
            wl, ws = hyst_book(SC, U, n_in, n_out)
            run(f"B top{un} in{n_in} out{n_out}", wl - ws, {"top": un, "n_in": n_in, "n_out": n_out})

print("=== B lookback robustness with buffer in4/out8, top20")
for Ls in [(7, 14), (14,), (14, 28), (28,), (14, 28, 42), (21, 42), (7, 14, 28, 56), (10, 20, 40, 80), (42,), (56,)]:
    wl, ws = hyst_book(ra_score(Ls), U20, 4, 8)
    run(f"B L{'-'.join(map(str, Ls))} in4 out8", wl - ws, {"Ls": str(Ls)})

print("=== B vol window for risk adjustment")
for span in [14, 60, 90]:
    v2 = lab.ewm_vol(P, span)
    sc = sum(((C / C.shift(L) - 1) / (v2 * np.sqrt(L / 365))).rank(axis=1, pct=True) for L in (14, 28)) / 2
    wl, ws = hyst_book(sc, U20, 4, 8)
    run(f"B vol span {span} in4 out8", wl - ws)

print("=== B weekly rebalance (score updated only on Mondays)")
mask = pd.Series(C.index.dayofweek == 0, index=C.index)
wl, ws = hyst_book(SC, U20, 4, 8)
Wwk = (wl - ws).where(mask, np.nan).ffill().fillna(0)
run("B in4 out8 weekly", Wwk)

pd.DataFrame(rows).to_csv(os.path.join(lab.RES, "stage5_is.csv"), index=False)
