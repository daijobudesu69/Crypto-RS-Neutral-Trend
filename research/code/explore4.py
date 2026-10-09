"""Stage 4 — build robust trend + relative-strength sleeves on IS only (2020-07 .. 2024-12)."""
import os
import numpy as np, pandas as pd
import lab

P = lab.load_panel("binance", "1d")
C = P["close"]
r = C.pct_change(fill_method=None)
vol = lab.ewm_vol(P, 30)
IS = dict(start="2020-07-01", end="2024-12-31")
U = {n: lab.universe_mask(P, top=n, min_hist=200) for n in [10, 15, 20, 30, 40]}
rows = []
RET = {}


def run(name, W, extra=None, cost=0.0007, keep=False):
    bt = lab.backtest(W, P, cost=cost, **IS)
    m = lab.metrics(bt["net"], name)
    m["t"] = lab.tstat_daily(bt["net"]); m["turn"] = bt["turn"].mean(); m["fund_ann"] = bt["fund"].mean() * 365
    m["gexp"] = bt["gross_exp"].mean(); m["nexp"] = bt["net_exp"].mean()
    for yr, v in lab.yearly(bt["net"]).items():
        m[f"y{yr}"] = v
    if extra:
        m.update(extra)
    rows.append(m)
    if keep:
        RET[name] = bt["net"]
    ys = " ".join(f"{v*100:5.0f}" for k, v in m.items() if str(k).startswith("y20"))
    print(lab.fmt(m), f"t {m['t']:.2f} turn {m['turn']:.2f} gexp {m['gexp']:.2f} nexp {m['nexp']:+.2f} | {ys}", flush=True)
    return bt


def trend_score(kind, C):
    if kind == "ema":
        e = [np.sign(C.ewm(span=f, min_periods=s).mean() - C.ewm(span=s, min_periods=s).mean()) for f, s in [(8, 32), (16, 64), (32, 128)]]
        return sum(e) / 3
    if kind == "tsmom":
        return sum(np.sign(C / C.shift(L) - 1) for L in [20, 40, 80, 160]) / 4
    if kind == "donch":
        out = []
        for n in [20, 55, 100]:
            hi = C.rolling(n).max(); lo = C.rolling(n).min()
            out.append(((C - lo) / (hi - lo) * 2 - 1))  # position in channel, -1..1
        return sum(out) / 3
    if kind == "blend":
        return (trend_score("ema", C) + trend_score("tsmom", C) + trend_score("donch", C)) / 3


def vt_portfolio(W, tv, lb=60, cap=3.0):
    """scale whole book to target vol using trailing realised vol of the (unscaled) book."""
    pr = (W.shift(1) * r).sum(axis=1)
    rv = pr.rolling(lb, min_periods=20).std() * np.sqrt(365)
    k = (tv / rv).clip(upper=cap).shift(0).fillna(0)
    return W.mul(k, axis=0)


print("=== A: TS trend, long-only, per-coin vol parity (each coin 1/N of risk), portfolio not scaled")
for kind in ["ema", "tsmom", "donch", "blend"]:
    S = trend_score(kind, C)
    for n in [10, 20, 30]:
        w = (S.clip(lower=0) * (0.5 / vol)).where(U[n], 0).fillna(0).clip(upper=1.0)
        w = w.div(n, axis=0)
        run(f"A {kind} LO top{n}", w, {"sleeve": "A", "kind": kind, "top": n})
for kind in ["ema", "blend"]:
    S = trend_score(kind, C)
    w = (S * (0.5 / vol)).where(U[20], 0).fillna(0).clip(-1, 1).div(20)
    run(f"A {kind} LS top20", w, {"sleeve": "A", "kind": kind + "_LS", "top": 20})
    # asymmetric: shorts only when BTC trend is down
    bt_dn = (trend_score(kind, C)["BTC"] < 0)
    ws = w.clip(upper=0).mul(bt_dn.astype(float), axis=0)
    run(f"A {kind} long + short-if-BTC-down top20", w.clip(lower=0) + ws, {"sleeve": "A", "kind": kind + "_asym", "top": 20})

print("=== B: XS relative strength, market neutral, ensemble of risk-adjusted lookbacks")
def xs_score(Ls, risk_adj=True):
    sc = 0
    for L in Ls:
        m = C / C.shift(L) - 1
        if risk_adj:
            m = m / (vol * np.sqrt(L / 365))
        sc = sc + m.rank(axis=1, pct=True)
    return sc / len(Ls)


def xs_w(score, Um, q=0.2, gross=1.0):
    s = score.where(Um)
    rk = s.rank(axis=1, pct=True)
    wl = (rk >= 1 - q).astype(float); ws = (rk <= q).astype(float)
    wl = wl.div(wl.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * gross / 2
    ws = ws.div(ws.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * gross / 2
    return wl, ws


for Ls in [(14, 28), (14, 28, 42), (7, 14, 28, 56), (21, 42), (28,), (14,), (10, 20, 40, 80)]:
    for ra in [True, False]:
        for n in [20, 30, 40]:
            wl, ws = xs_w(xs_score(Ls, ra), U[n])
            run(f"B L{'-'.join(map(str, Ls))} {'RA' if ra else 'raw'} top{n}", wl - ws,
                {"sleeve": "B", "Ls": str(Ls), "ra": ra, "top": n})

print("=== C: dual filter — long top-q AND own trend up; short bottom-q AND own trend down")
S = trend_score("ema", C)
for n in [20, 30]:
    wl, ws = xs_w(xs_score((14, 28, 42)), U[n], q=0.3)
    wl = wl.where(S > 0, 0); ws = ws.where(S < 0, 0)
    run(f"C dual q30 top{n}", wl - ws, {"sleeve": "C", "top": n})
    run(f"C dual long-only q30 top{n}", wl, {"sleeve": "C", "top": n})

pd.DataFrame(rows).to_csv(os.path.join(lab.RES, "stage4_is.csv"), index=False)
