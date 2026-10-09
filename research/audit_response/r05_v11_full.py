"""Audit response r05 — RNT v1.1 (post-audit fix: age from real trading days, percentile among coins trading today).
IS (Binance + dead coins with REAL funding) and OOS (HYPE incl. delisted): headline, stress, end-date, engines,
neighbour grid. Plus an optional regime filter for engine 1, evaluated but NOT adopted (post-hoc)."""
import os, sys, copy, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "code"))
import lab, rnt, account

HERE = os.path.dirname(os.path.abspath(__file__))
V11 = dict(age_mode="real", pct_scope="traded")
IS = ("2020-07-01", "2024-12-31"); OOS = ("2025-01-01", "2026-09-30")
H = lab.load_panel_ext("hl")
BXf = pd.read_pickle(os.path.join(lab.CACHE, "panel_binance_1d_ext_realfund.pkl"))
R = {}


def spec(**kw):
    s = copy.deepcopy(rnt.SPEC); s.update(V11); s.update(kw); return s


def acct(W, P, a, b, tag, cost=0.0007):
    d, t, o = account.simulate(W, P, 200, 10, 0.40, cost, start=a, end=b)
    eq = d["equity"]; r = eq.pct_change().fillna(eq.iloc[0] / 200 - 1); m = lab.metrics(r)
    closed = t[t["exit"].notna()]
    y = (1 + r).groupby(r.index.year).prod() - 1
    out = {"end": eq.iloc[-1], "cagr": m["cagr"], "vol": m["vol"], "sharpe": m["sharpe"], "sortino": m["sortino"], "calmar": m["calmar"],
           "mdd": m["mdd"], "avg_dd": m["avg_dd"], "t": lab.tstat_daily(r), "orders": len(o), "orders_pm": len(o) / (len(d) / 30.4),
           "trips": len(closed), "trips_pm": len(closed) / (len(d) / 30.4), "win_rate": (closed.pnl > 0).mean(),
           "pf": closed[closed.pnl > 0].pnl.sum() / -closed[closed.pnl <= 0].pnl.sum(), "fees": -d["fees"].sum(),
           "funding": d["pnl_funding"].sum(), "yearly": {int(k): v for k, v in y.items()},
           "pos_months": int(((1 + r).groupby(r.index.to_period("M")).prod() - 1 > 0).sum()),
           "n_months": int(r.index.to_period("M").nunique()), "open_pnl": t[t["exit"].isna()].pnl.sum()}
    dd = eq / eq.cummax() - 1
    uw, cur = 0, 0
    for v in dd.values:
        cur = cur + 1 if v < 0 else 0; uw = max(uw, cur)
    out["max_underwater"] = uw
    print(f"{tag:<46} {out['end']:7.0f} | SR {out['sharpe']:.2f} So {out['sortino']:.2f} DD {out['mdd']*100:5.1f}% avgDD {out['avg_dd']*100:4.1f}% "
          f"uw {uw}d | yr {', '.join(f'{k}:{v*100:+.0f}%' for k, v in out['yearly'].items())}", flush=True)
    R[tag] = out
    return d, t, o, r


print("=== v1.1 OOS HYPE (headline)")
D = rnt.build(H, spec())
d, t, o, r = acct(D["W"], H, *OOS, "v1.1 OOS RNT")
d.to_csv(os.path.join(HERE, "v11_oos_daily.csv")); t.to_csv(os.path.join(HERE, "v11_oos_trips.csv"), index=False)
acct(D["W_rs"], H, *OOS, "v1.1 OOS Mesin1 saja")
acct(D["W_tr"], H, *OOS, "v1.1 OOS Mesin2 saja")
acct(D["W"], H, *OOS, "v1.1 OOS biaya 2x", cost=0.0015)
acct(D["W"].shift(1).fillna(0), H, *OOS, "v1.1 OOS telat 1 hari")
eq = d["equity"]
R["end_date"] = {k: float(eq.loc[:k].iloc[-1]) for k in ["2025-06-30", "2025-12-31", "2026-03-31", "2026-06-30", "2026-07-31", "2026-08-31", "2026-09-30"]}
print("nilai per tanggal:", {k: round(v) for k, v in R["end_date"].items()})
v10 = pd.read_csv(os.path.join(lab.RES, "oos_daily_hype.csv"), index_col=0, parse_dates=True)["equity"]
R["v10_end_date"] = {k: float(v10.loc[:k].iloc[-1]) for k in R["end_date"]}

print("=== v1.1 IS Binance + koin mati + funding riil")
DI = rnt.build(BXf, spec())
di, ti, oi, ri = acct(DI["W"], BXf, *IS, "v1.1 IS RNT")
di.to_csv(os.path.join(HERE, "v11_is_daily.csv"))
acct(DI["W_rs"], BXf, *IS, "v1.1 IS Mesin1 saja")
acct(DI["W_tr"], BXf, *IS, "v1.1 IS Mesin2 saja")

print("=== v1.1 OOS tetangga parameter (dilaporkan saja)")
grid = [("dasar", {}), ("buffer 3/7", {"rs_in": 3, "rs_out": 7}), ("buffer 5/9", {"rs_in": 5, "rs_out": 9}),
        ("buffer 4/6", {"rs_in": 4, "rs_out": 6}), ("buffer 4/10", {"rs_in": 4, "rs_out": 10}),
        ("lookback 14/28", {"rs_lookbacks": (14, 28)}), ("lookback 7/14/28", {"rs_lookbacks": (7, 14, 28)}),
        ("lookback 28/56", {"rs_lookbacks": (28, 56)}), ("RS top-15", {"rs_top": 15}), ("RS top-30", {"rs_top": 30}),
        ("trend top-3", {"tr_top": 3}), ("trend top-8", {"tr_top": 8}), ("vol mesin 15%", {"sleeve_vol": 0.15}),
        ("vol mesin 25%", {"sleeve_vol": 0.25}), ("umur 120 hari", {"min_hist": 120}), ("umur 300 hari", {"min_hist": 300})]
G = []
for nm, ch in grid:
    Dv = rnt.build(H, spec(**ch))
    dv, _, _ = account.simulate(Dv["W"], H, 200, 10, 0.40, 0.0007, start=OOS[0], end=OOS[1])
    rv = dv["equity"].pct_change().fillna(dv["equity"].iloc[0] / 200 - 1); mv = lab.metrics(rv)
    DvI = rnt.build(BXf, spec(**ch))
    bi = lab.backtest(DvI["W"], BXf, start=IS[0], end=IS[1]); mi = lab.metrics(bi["net"])
    G.append({"variant": nm, "oos_end": dv["equity"].iloc[-1], "oos_sharpe": mv["sharpe"], "oos_mdd": mv["mdd"], "is_sharpe": mi["sharpe"]})
    print(f"  {nm:<18} OOS {dv['equity'].iloc[-1]:5.0f} SR {mv['sharpe']:.2f} DD {mv['mdd']*100:5.1f}% | IS SR {mi['sharpe']:.2f}", flush=True)
R["grid"] = G

print("=== opsi (TIDAK diadopsi): Mesin 1 dimatikan/separuh saat BTC 90 hari turun")
for P, a, b, nm in [(BXf, *IS, "IS"), (H, *OOS, "OOS")]:
    Dx = rnt.build(P, spec())
    btc = P["close"]["BTC"]
    up = (btc / btc.shift(90) - 1 > 0).astype(float)
    for lab_, f in [("off", up), ("separuh", 0.5 + 0.5 * up)]:
        W = Dx["W_rs"].mul(f, axis=0).add(Dx["W_tr"], fill_value=0)
        dx, _, _ = account.simulate(W, P, 200, 10, 0.40, 0.0007, start=a, end=b)
        rx = dx["equity"].pct_change().fillna(dx["equity"].iloc[0] / 200 - 1); mx = lab.metrics(rx)
        print(f"  {nm} filter {lab_:<8}: {dx['equity'].iloc[-1]:6.0f} SR {mx['sharpe']:.2f} DD {mx['mdd']*100:5.1f}%", flush=True)
        R[f"regime_{nm}_{lab_}"] = {"end": dx["equity"].iloc[-1], "sharpe": mx["sharpe"], "mdd": mx["mdd"]}
json.dump(R, open(os.path.join(HERE, "r05_v11.json"), "w"), indent=1, default=float)
