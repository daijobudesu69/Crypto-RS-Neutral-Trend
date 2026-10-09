"""Stage 6 — lag/cost stress for B, trend sleeve A sized for small capital, combination. IS only."""
import os
import numpy as np, pandas as pd
import lab, strat as S

P = lab.load_panel("binance", "1d")
C = P["close"]
r = C.pct_change(fill_method=None)
vol = lab.ewm_vol(P, 30)
IS = dict(start="2020-07-01", end="2024-12-31")
U = {n: lab.universe_mask(P, top=n, min_hist=200) for n in [5, 8, 10, 15, 20, 30]}
rows, RET = [], {}


def run(name, W, extra=None, cost=0.0007, lag=1, keep=True):
    bt = lab.backtest(W, P, cost=cost, lag=lag, **IS)
    m = lab.metrics(bt["net"], name)
    m["t"] = lab.tstat_daily(bt["net"]); m["turn"] = bt["turn"].mean()
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


print("=== B ensemble (7,14,28,56) buffer grid, top20")
SCe = S.ra_score(C, vol, (7, 14, 28, 56))
SC2 = S.ra_score(C, vol, (14, 28))
for n_in in [3, 4, 5, 6]:
    for n_out in [n_in + 2, n_in + 4, n_in + 6]:
        wl, ws = S.hyst_book(SCe, U[20], n_in, n_out)
        run(f"Bens top20 in{n_in} out{n_out}", wl - ws, keep=False)

print("=== B stress: lag and cost (L7-56 ens, in4 out8, top20)")
wl, ws = S.hyst_book(SCe, U[20], 4, 8)
WB = wl - ws
run("B base", WB)
run("B lag+1 day", WB, lag=2, keep=False)
run("B cost 0.15%/side", WB, cost=0.0015, keep=False)
run("B cost 0.25%/side", WB, cost=0.0025, keep=False)
run("B no funding cost", WB, keep=False) if False else None

print("=== A trend sleeve for small capital: few liquid coins, per-coin vol target, long-only")
DP = S.donch_pos(C)
ET = S.ema_trend(C)
for nm, sig in [("donch", DP), ("ema", ET), ("blend", (DP + ET) / 2)]:
    for n in [5, 8, 10]:
        for cv in [0.4]:
            w = (sig.clip(lower=0) * (cv / vol)).where(U[n], 0).fillna(0).clip(upper=1.5).div(n)
            run(f"A {nm} LO top{n}", w, {"n": n}, keep=(nm == "blend"))

print("=== A on BTC+ETH only")
for nm, sig in [("donch", DP), ("blend", (DP + ET) / 2)]:
    w = (sig[["BTC", "ETH"]].clip(lower=0) * (0.4 / vol[["BTC", "ETH"]])).clip(upper=1.5) / 2
    run(f"A {nm} BTC+ETH", w)

# correlations
R = pd.DataFrame(RET).dropna()
btc = r["BTC"].reindex(R.index)
print("\ncorr with BTC:", R.corrwith(btc).round(2).to_dict())
print("corr B vs A blend top10:", round(R["B base"].corr(R["A blend LO top10"]), 3))

print("=== Combination: B + A blend top10, each sleeve vol-targeted, then combined")
WA = ((DP + ET) / 2).clip(lower=0).mul(0.4 / vol).where(U[10], 0).fillna(0).clip(upper=1.5).div(10)
for tvB, tvA in [(0.2, 0.2), (0.25, 0.15), (0.3, 0.2), (0.2, 0.3)]:
    WBs, kB = S.book_vol_scale(WB, r, tvB)
    WAs, kA = S.book_vol_scale(WA, r, tvA)
    run(f"COMBO B{tvB}+A{tvA}", WBs.add(WAs, fill_value=0), {"tvB": tvB, "tvA": tvA})
WBs, _ = S.book_vol_scale(WB, r, 0.25)
run("B alone vt25", WBs)

pd.DataFrame(rows).to_csv(os.path.join(lab.RES, "stage6_is.csv"), index=False)
pd.DataFrame(RET).to_pickle(os.path.join(lab.CACHE, "stage6_ret.pkl"))
