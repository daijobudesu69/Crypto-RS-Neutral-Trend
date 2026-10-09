"""IS survivorship check: frozen spec on Binance alive-only vs Binance incl. dead/low-volume perps (2020-07 .. 2024-12).
Dead coins have no funding data in the lake -> funding 0 for them (stated in the report)."""
import os, json
import numpy as np, pandas as pd
import lab, rnt, account

IS = dict(start="2020-07-01", end="2024-12-31")
B = lab.load_panel("binance", "1d")
BX = lab.load_panel_ext("binance")
r = BX["close"].pct_change(fill_method=None)
# guard: flag absurd single-day moves (bad prints / relisting splices)
bad = (r > 3.0) | (r < -0.95)
print("absurd daily moves:", int(bad.sum().sum()), list(r.columns[bad.any()])[:20])
# all flagged moves were verified as real (LUNA crash, DOGE pump, squeezes) -> keep them
print("panels:", B["close"].shape, BX["close"].shape)
out = {}
for nm, P in [("alive-only", B), ("incl. dead+small", BX)]:
    D = rnt.build(P)
    for eng in ["W", "W_rs", "W_tr"]:
        bt = lab.backtest(D[eng], P, **IS)
        m = lab.metrics(bt["net"], f"{nm} {eng}")
        print(lab.fmt(m), "| yearly", (lab.yearly(bt["net"]) * 100).round(0).to_dict())
        out[f"{nm} {eng}"] = {"sharpe": m["sharpe"], "cagr": m["cagr"], "mdd": m["mdd"]}
    d, t, o = account.simulate(D["W"], P, 200, 10, 0.40, 0.0007, **IS)
    rr = d["equity"].pct_change().fillna(d["equity"].iloc[0] / 200 - 1); m = lab.metrics(rr)
    print(f"  {nm} 200 USD account: end {d['equity'].iloc[-1]:.0f}  SR {m['sharpe']:.2f}  mdd {m['mdd']*100:.1f}%")
    out[f"{nm} account"] = {"end": d["equity"].iloc[-1], "sharpe": m["sharpe"], "mdd": m["mdd"]}
    U = D["U_rs"].loc[IS["start"]:IS["end"]]
    dead_in = [c for c in U.columns if c not in B["close"].columns and U[c].any()]
    print("  coins not in alive lake that entered RS top-20:", len(dead_in), dead_in[:40])
json.dump(out, open(os.path.join(lab.RES, "survivorship_is.json"), "w"), indent=1, default=float)
