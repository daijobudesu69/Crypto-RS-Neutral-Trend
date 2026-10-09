"""In-sample diagnostics of the frozen RNT spec (Binance prices, 2020-07 .. 2024-12)."""
import os, json
import numpy as np, pandas as pd
import lab, rnt, account

P = lab.load_panel("binance", "1d")
D = rnt.build(P)
IS = dict(start="2020-07-01", end="2024-12-31")
out = {}
for nm, W in [("RNT", D["W"]), ("RS-neutral", D["W_rs"]), ("Trend", D["W_tr"])]:
    bt = lab.backtest(W, P, **IS)
    m = lab.metrics(bt["net"], nm)
    m["t"] = lab.tstat_daily(bt["net"]); m["gexp"] = bt["gross_exp"].mean(); m["gexp_max"] = bt["gross_exp"].max()
    m["turn"] = bt["turn"].mean()
    print(lab.fmt(m), f"t {m['t']:.2f} gexp {m['gexp']:.2f} max {m['gexp_max']:.2f} turn {m['turn']:.2f}")
    print("   yearly:", (lab.yearly(bt["net"]) * 100).round(1).to_dict())
    out[nm] = {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in m.items()}
    if nm == "RNT":
        net = bt["net"]
        print("   worst days:", (net.nsmallest(5) * 100).round(2).to_dict())
        eq = (1 + net).cumprod(); dd = eq / eq.cummax() - 1
        print("   max DD trough:", dd.idxmin().date(), "peak:", eq[:dd.idxmin()].idxmax().date())
        print("   costs/yr: fees", round(bt["cost"].mean() * 365 * 100, 2), "% funding", round(bt["fund"].mean() * 365 * 100, 2), "%")
r = P["close"].pct_change(fill_method=None)
R = pd.DataFrame({k: lab.backtest(v, P, **IS)["net"] for k, v in [("rs", D["W_rs"]), ("tr", D["W_tr"])]})
print("corr rs/tr", R.corr().iloc[0, 1].round(3), " corr with BTC:", R.corrwith(r["BTC"].reindex(R.index)).round(2).to_dict())

print("\n=== 200 USD account sim, IS (Binance prices)")
daily, trips, orders = account.simulate(D["W"], P, 200, 10, 0.25, 0.0007, **IS)
ret = daily["equity"].pct_change().fillna(daily["equity"].iloc[0] / 200 - 1)
m = lab.metrics(ret, "RNT $200 IS")
print(lab.fmt(m))
print("  final equity", round(daily["equity"].iloc[-1], 1), "orders", len(orders), "orders/month", round(len(orders) / (len(daily) / 30.4), 1),
      "round trips", trips["exit"].notna().sum(), "avg gross lev", round(daily["gross_lev"].mean(), 2), "max", round(daily["gross_lev"].max(), 2))
json.dump(out, open(os.path.join(lab.RES, "is_frozen_metrics.json"), "w"), indent=1, default=str)
