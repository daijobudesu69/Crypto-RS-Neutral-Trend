"""ONE-SHOT out-of-sample run of the frozen RNT spec: 2025-01-01 .. 2026-09-30 (requested by the user).
Primary = HYPE prices + HYPE universe INCLUDING coins delisted since (no survivorship) + HYPE hourly funding,
200 USD account with 10 USD minimum order. Nothing in rnt.SPEC is changed after this run."""
import os, json
import numpy as np, pandas as pd
import lab, rnt, account

S0, S1 = "2025-01-01", "2026-09-30"
OUT = {}


def acct(W, P, tag, cost=0.0007, lag0=False):
    daily, trips, orders = account.simulate(W, P, 200.0, 10.0, 0.40, cost, start=S0, end=S1)
    eq = daily["equity"]
    ret = eq.pct_change().fillna(eq.iloc[0] / 200 - 1)
    m = lab.metrics(ret, tag)
    closed = trips[trips["exit"].notna()]
    wins, losses = closed[closed.pnl > 0].pnl, closed[closed.pnl <= 0].pnl
    months = len(daily) / 30.4
    m.update({
        "final_equity": eq.iloc[-1], "orders": len(orders), "orders_pm": len(orders) / months,
        "round_trips": len(closed), "trips_pm": len(closed) / months, "win_rate": (closed.pnl > 0).mean(),
        "avg_win": wins.mean(), "avg_loss": losses.mean(), "profit_factor": wins.sum() / -losses.sum() if len(losses) else np.nan,
        "fees": -daily["fees"].sum(), "funding": daily["pnl_funding"].sum(), "avg_gross_lev": daily["gross_lev"].mean(),
        "max_gross_lev": daily["gross_lev"].max(), "avg_net_lev": daily["net_lev"].mean(),
        "long_trips": int((closed.side > 0).sum()), "short_trips": int((closed.side < 0).sum()),
        "long_pnl": closed[closed.side > 0].pnl.sum(), "short_pnl": closed[closed.side < 0].pnl.sum(),
        "t": lab.tstat_daily(ret),
    })
    y = (1 + ret).groupby(ret.index.year).prod() - 1
    m["y2025"], m["y2026ytd"] = y.get(2025, np.nan), y.get(2026, np.nan)
    print(lab.fmt(m), f"| end ${m['final_equity']:.0f} orders/mo {m['orders_pm']:.0f} trips/mo {m['trips_pm']:.0f} "
          f"WR {m['win_rate']*100:.0f}% PF {m['profit_factor']:.2f} 2025 {m['y2025']*100:+.0f}% 2026 {m['y2026ytd']*100:+.0f}%", flush=True)
    OUT[tag] = {k: (float(v) if isinstance(v, (int, float, np.floating, np.integer)) else v) for k, v in m.items()}
    return daily, trips, orders, ret


def weights_only(W, P, tag, **kw):
    bt = lab.backtest(W, P, start=S0, end=S1, **kw)
    m = lab.metrics(bt["net"], tag)
    m["t"] = lab.tstat_daily(bt["net"])
    y = lab.yearly(bt["net"])
    m["y2025"], m["y2026ytd"] = y.get(2025, np.nan), y.get(2026, np.nan)
    print(lab.fmt(m), f"| t {m['t']:.2f} 2025 {m['y2025']*100:+.0f}% 2026 {m['y2026ytd']*100:+.0f}%", flush=True)
    OUT[tag] = {k: (float(v) if isinstance(v, (int, float, np.floating, np.integer)) else v) for k, v in m.items()}
    return bt


H = lab.load_panel_ext("hl")            # HYPE incl. delisted
Ha = lab.load_panel("hl", "1d")         # HYPE alive only
B = lab.load_panel("binance", "1d")     # Binance alive only

DH = rnt.build(H)
print("=== PRIMARY: 200 USD account on HYPE (incl. delisted coins), OOS", S0, "->", S1)
daily, trips, orders, ret = acct(DH["W"], H, "RNT HYPE $200")
daily.to_csv(os.path.join(lab.RES, "oos_daily_hype.csv"))
trips.to_csv(os.path.join(lab.RES, "oos_trips_hype.csv"), index=False)
orders.to_csv(os.path.join(lab.RES, "oos_orders_hype.csv"), index=False)
acct(DH["W_rs"], H, "RS-neutral only HYPE $200")
acct(DH["W_tr"], H, "Trend only HYPE $200")

print("=== stress (same frozen spec)")
acct(DH["W"], H, "RNT HYPE $200 cost 0.15%", cost=0.0015)
W_lag = DH["W"].shift(1).fillna(0)
acct(W_lag, H, "RNT HYPE $200 executed 1 day late")

print("=== weights-only (no min-order), for reference")
bt_h = weights_only(DH["W"], H, "RNT weights HYPE ext")
bt_rs = weights_only(DH["W_rs"], H, "RS weights HYPE ext")
bt_tr = weights_only(DH["W_tr"], H, "Trend weights HYPE ext")
DA = rnt.build(Ha)
weights_only(DA["W"], Ha, "RNT weights HYPE alive-only")
DB = rnt.build(B)
weights_only(DB["W"], B, "RNT weights Binance alive-only")

print("=== benchmarks (HYPE)")
C = H["close"]
r = C.pct_change(fill_method=None)
btc = r["BTC"].loc[S0:S1].fillna(0)
OUT["BTC buy&hold"] = lab.metrics(btc, "BTC buy&hold"); print(lab.fmt(OUT["BTC buy&hold"]))
U20 = DH["U_rs"]
ew = r.where(U20.shift(1)).mean(axis=1).loc[S0:S1].fillna(0)
OUT["EW top20 basket"] = lab.metrics(ew, "EW top20 basket"); print(lab.fmt(OUT["EW top20 basket"]))

# correlations and leg info
rr = pd.DataFrame({"rs": bt_rs["net"], "tr": bt_tr["net"], "btc": btc})
print("corr:", rr.corr().round(2).to_dict())
OUT["corr"] = rr.corr().round(3).to_dict()
json.dump(OUT, open(os.path.join(lab.RES, "oos_metrics.json"), "w"), indent=1, default=str)
pd.DataFrame({"rnt": bt_h["net"], "rs": bt_rs["net"], "tr": bt_tr["net"], "btc": btc, "ew20": ew}).to_csv(os.path.join(lab.RES, "oos_weights_daily.csv"))
