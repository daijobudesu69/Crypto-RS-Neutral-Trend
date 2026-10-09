"""Numbers + charts for the report. Uses the frozen spec only; the OOS neighbour grid is REPORTED, not used to select."""
import os, json, copy
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import lab, rnt, account

S0, S1 = "2025-01-01", "2026-09-30"
BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.6, "lines.linewidth": 2})
R = {}

H = lab.load_panel_ext("hl")
D = rnt.build(H)
daily, trips, orders = account.simulate(D["W"], H, 200, 10, 0.40, 0.0007, start=S0, end=S1)
eq = daily["equity"]
ret = eq.pct_change().fillna(eq.iloc[0] / 200 - 1)
m = lab.metrics(ret)
closed = trips[trips["exit"].notna()].copy()
closed["days"] = (pd.to_datetime(closed["exit"]) - pd.to_datetime(closed["entry"])).dt.days
dd = eq / eq.cummax() - 1
uw, mx, cur = [], 0, 0
for v in dd.values:
    cur = cur + 1 if v < 0 else 0
    mx = max(mx, cur)
mon = (1 + ret).groupby(ret.index.to_period("M")).prod() - 1
R["oos"] = {
    "start": 200.0, "end": float(eq.iloc[-1]), "total": float(m["total"]), "cagr": float(m["cagr"]), "vol": float(m["vol"]),
    "sharpe": float(m["sharpe"]), "sortino": float(m["sortino"]), "calmar": float(m["calmar"]), "mdd": float(m["mdd"]),
    "avg_dd": float(m["avg_dd"]), "n_dd": int(m["n_dd"]), "max_underwater_days": int(mx),
    "mdd_date": str(dd.idxmin().date()), "peak_equity": float(eq.max()), "low_equity": float(eq.min()),
    "orders": int(len(orders)), "orders_pm": len(orders) / (len(daily) / 30.4), "trips": int(len(closed)),
    "trips_pm": len(closed) / (len(daily) / 30.4), "win_rate": float((closed.pnl > 0).mean()),
    "avg_win": float(closed[closed.pnl > 0].pnl.mean()), "avg_loss": float(closed[closed.pnl <= 0].pnl.mean()),
    "pf": float(closed[closed.pnl > 0].pnl.sum() / -closed[closed.pnl <= 0].pnl.sum()),
    "hold_med": float(closed["days"].median()), "hold_mean": float(closed["days"].mean()),
    "fees": float(-daily["fees"].sum()), "funding": float(daily["pnl_funding"].sum()),
    "gross_lev_avg": float(daily["gross_lev"].mean()), "gross_lev_max": float(daily["gross_lev"].max()),
    "net_lev_avg": float(daily["net_lev"].mean()), "pos_months": int((mon > 0).sum()), "n_months": int(len(mon)),
    "best_month": float(mon.max()), "worst_month": float(mon.min()), "best_month_name": str(mon.idxmax()),
    "worst_month_name": str(mon.idxmin()), "best_day": float(ret.max()), "worst_day": float(ret.min()),
    "worst_day_date": str(ret.idxmin().date()),
    "y2025": float((1 + ret.loc["2025"]).prod() - 1), "y2026": float((1 + ret.loc["2026"]).prod() - 1),
    "eq_2025_end": float(eq.loc[:"2025-12-31"].iloc[-1]),
    "long_trips": int((closed.side > 0).sum()), "short_trips": int((closed.side < 0).sum()),
    "long_pnl": float(closed[closed.side > 0].pnl.sum()), "short_pnl": float(closed[closed.side < 0].pnl.sum()),
    "long_wr": float((closed[closed.side > 0].pnl > 0).mean()), "short_wr": float((closed[closed.side < 0].pnl > 0).mean()),
}
R["monthly"] = {str(k): float(v) for k, v in mon.items()}
R["quarterly"] = {str(k): float(v) for k, v in ((1 + ret).groupby(ret.index.to_period("Q")).prod() - 1).items()}
# per-month trade counts
R["orders_by_month"] = {str(k): int(v) for k, v in orders.groupby(pd.to_datetime(orders["date"]).dt.to_period("M")).size().items()}
R["top_coins"] = closed.groupby("coin").pnl.sum().sort_values().round(1).to_dict()
print(json.dumps(R["oos"], indent=1))

# engines as separate 200-USD accounts and benchmarks
eng = {}
for nm, W in [("RS-Neutral", D["W_rs"]), ("Trend", D["W_tr"])]:
    d2, _, _ = account.simulate(W, H, 200, 10, 0.40, 0.0007, start=S0, end=S1)
    eng[nm] = d2["equity"]
r = H["close"].pct_change(fill_method=None)
btc = (1 + r["BTC"].loc[S0:S1].fillna(0)).cumprod() * 200
ew = (1 + r.where(D["U_rs"].shift(1)).mean(axis=1).loc[S0:S1].fillna(0)).cumprod() * 200
R["bench_end"] = {"BTC": float(btc.iloc[-1]), "EW20": float(ew.iloc[-1]), "RS": float(eng["RS-Neutral"].iloc[-1]), "Trend": float(eng["Trend"].iloc[-1])}

# ---------------- chart 1: OOS equity + drawdown + rolling vol
fig, ax = plt.subplots(3, 1, figsize=(10, 9.2), sharex=True, gridspec_kw={"height_ratios": [3, 1.2, 1.2]})
a = ax[0]
a.plot(eq.index, eq.values, color=BLUE, label="RNT (akun 200 USD, HYPE)", zorder=3)
a.plot(btc.index, btc.values, color=ORANGE, label="Beli & tahan BTC", lw=1.6)
a.plot(ew.index, ew.values, color=AQUA, label="Basket rata 20 koin", lw=1.6)
a.axhline(200, color=INK2, lw=0.8, ls="--")
for s, c, lab_ in [(eq, BLUE, "RNT"), (btc, ORANGE, "BTC"), (ew, AQUA, "Basket")]:
    a.annotate(f"{lab_}: {s.iloc[-1]:,.0f} USD", (s.index[-1], s.iloc[-1]), xytext=(6, 0), textcoords="offset points",
               va="center", fontsize=9.5, color=INK, fontweight="bold" if lab_ == "RNT" else "normal")
a.set_ylabel("Ekuitas (USD)")
a.set_title("Modal 200 USD, Jan 2025 → 30 Sep 2026 (out-of-sample, harga HYPE)", loc="left", fontsize=12, color=INK)
a.legend(loc="upper left", frameon=False)
a.set_xlim(eq.index[0], eq.index[-1] + pd.Timedelta(days=95))
b = ax[1]
b.fill_between(dd.index, dd.values * 100, 0, color=RED, alpha=0.35, lw=0)
b.plot(dd.index, dd.values * 100, color=RED, lw=1.2)
b.set_ylabel("Drawdown (%)")
b.annotate(f"maks {dd.min()*100:.1f}%", (dd.idxmin(), dd.min() * 100), xytext=(8, -2), textcoords="offset points", fontsize=9, color=INK)
c = ax[2]
rv = ret.rolling(30).std() * np.sqrt(365) * 100
c.plot(rv.index, rv.values, color=BLUE, lw=1.5)
btv = r["BTC"].loc[S0:S1].rolling(30).std() * np.sqrt(365) * 100
c.plot(btv.index, btv.values, color=ORANGE, lw=1.2)
c.set_ylabel("Volatilitas 30h\n(% tahunan)")
hi_is_rnt = rv.iloc[-1] >= btv.iloc[-1]
c.annotate("RNT", (rv.index[-1], rv.iloc[-1]), xytext=(6, 7 if hi_is_rnt else -7), textcoords="offset points", fontsize=9, va="center")
c.annotate("BTC", (btv.index[-1], btv.iloc[-1]), xytext=(6, -7 if hi_is_rnt else 7), textcoords="offset points", fontsize=9, va="center")
c.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
fig.tight_layout()
fig.savefig(os.path.join(lab.CH, "oos_equity_200usd.png"), dpi=160)
plt.close(fig)

# ---------------- chart 2: monthly returns
fig, a = plt.subplots(figsize=(10, 3.6))
a.grid(axis="x", visible=False); a.set_axisbelow(True)
x = np.arange(len(mon))
a.bar(x, mon.values * 100, color=[BLUE if v > 0 else ORANGE for v in mon.values], width=0.72)
a.axhline(0, color=INK2, lw=0.8)
a.set_xticks(x, [p.strftime("%b\n%y") for p in mon.index], fontsize=8)
for i, v in enumerate(mon.values):
    a.annotate(f"{v*100:+.0f}", (i, v * 100), xytext=(0, 3 if v > 0 else -10), textcoords="offset points", ha="center", fontsize=7.5, color=INK2)
a.set_ylabel("Return bulanan (%)")
a.set_title(f"Return bulanan RNT (OOS): {int((mon>0).sum())} dari {len(mon)} bulan positif", loc="left", fontsize=12)
fig.tight_layout(); fig.savefig(os.path.join(lab.CH, "oos_monthly.png"), dpi=160); plt.close(fig)

# ---------------- chart 3: engines
fig, a = plt.subplots(figsize=(10, 4.2))
a.plot(eq.index, eq.values, color=BLUE, label="RNT (gabungan)")
a.plot(eng["RS-Neutral"].index, eng["RS-Neutral"].values, color=AQUA, lw=1.6, label="Mesin 1 saja: RS-Neutral")
a.plot(eng["Trend"].index, eng["Trend"].values, color=ORANGE, lw=1.6, label="Mesin 2 saja: Trend")
a.axhline(200, color=INK2, lw=0.8, ls="--")
for s, nm in [(eq, "RNT"), (eng["RS-Neutral"], "RS"), (eng["Trend"], "Trend")]:
    a.annotate(f"{nm}: {s.iloc[-1]:,.0f}", (s.index[-1], s.iloc[-1]), xytext=(6, 0), textcoords="offset points", va="center", fontsize=9)
a.set_xlim(eq.index[0], eq.index[-1] + pd.Timedelta(days=70))
a.legend(loc="upper left", frameon=False); a.set_ylabel("Ekuitas (USD)")
a.set_title("Kontribusi tiap mesin (masing-masing akun 200 USD)", loc="left", fontsize=12)
a.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
fig.tight_layout(); fig.savefig(os.path.join(lab.CH, "oos_engines.png"), dpi=160); plt.close(fig)

# ---------------- chart 4: IS (Binance) 200 USD, log scale
B = lab.load_panel("binance", "1d")
DB = rnt.build(B)
di, _, oi = account.simulate(DB["W"], B, 200, 10, 0.40, 0.0007, start="2020-07-01", end="2024-12-31")
ei = di["equity"]; ri = ei.pct_change().fillna(ei.iloc[0] / 200 - 1); mi = lab.metrics(ri)
bi = (1 + B["close"]["BTC"].pct_change().loc["2020-07-01":"2024-12-31"].fillna(0)).cumprod() * 200
ei.to_csv(os.path.join(lab.RES, "is_equity_binance.csv"))
R["is_acct"] = {"end": float(ei.iloc[-1]), "sharpe": float(mi["sharpe"]), "sortino": float(mi["sortino"]), "mdd": float(mi["mdd"]),
                "cagr": float(mi["cagr"]), "avg_dd": float(mi["avg_dd"]), "orders_pm": len(oi) / (len(di) / 30.4),
                "yearly": {int(k): float(v) for k, v in lab.yearly(ri).items()}, "btc_end": float(bi.iloc[-1])}
fig, a = plt.subplots(figsize=(10, 4.2))
a.plot(ei.index, ei.values, color=BLUE, label="RNT (akun 200 USD)")
a.plot(bi.index, bi.values, color=ORANGE, lw=1.6, label="Beli & tahan BTC")
a.set_yscale("log"); a.axhline(200, color=INK2, lw=0.8, ls="--")
from matplotlib.ticker import FixedLocator, NullLocator, FuncFormatter
a.yaxis.set_major_locator(FixedLocator([200, 400, 800, 1600, 3200])); a.yaxis.set_minor_locator(NullLocator())
a.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:,.0f}"))
a.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
for s, nm in [(ei, "RNT"), (bi, "BTC")]:
    a.annotate(f"{nm}: {s.iloc[-1]:,.0f}", (s.index[-1], s.iloc[-1]), xytext=(6, 0), textcoords="offset points", va="center", fontsize=9)
a.set_xlim(ei.index[0], ei.index[-1] + pd.Timedelta(days=150))
a.legend(loc="upper left", frameon=False); a.set_ylabel("Ekuitas (USD, skala log)")
a.set_title("In-sample (data riset): Jul 2020 → Des 2024, harga Binance", loc="left", fontsize=12)
fig.tight_layout(); fig.savefig(os.path.join(lab.CH, "is_equity_200usd.png"), dpi=160); plt.close(fig)

# ---------------- OOS neighbour sensitivity (reported only; spec is NOT changed)
grid = []
variants = [("baseline", {}), ("buffer 3/7", {"rs_in": 3, "rs_out": 7}), ("buffer 5/9", {"rs_in": 5, "rs_out": 9}),
            ("buffer 4/6", {"rs_in": 4, "rs_out": 6}), ("buffer 4/10", {"rs_in": 4, "rs_out": 10}),
            ("lookback 14/28", {"rs_lookbacks": (14, 28)}), ("lookback 7/14/28", {"rs_lookbacks": (7, 14, 28)}),
            ("lookback 28/56", {"rs_lookbacks": (28, 56)}), ("RS top-15", {"rs_top": 15}), ("RS top-30", {"rs_top": 30}),
            ("trend top-3", {"tr_top": 3}), ("trend top-8", {"tr_top": 8}), ("vol sleeve 15%", {"sleeve_vol": 0.15}),
            ("vol sleeve 25%", {"sleeve_vol": 0.25})]
for nm, ch in variants:
    sp = copy.deepcopy(rnt.SPEC); sp.update(ch)
    Dv = rnt.build(H, sp)
    dv, _, _ = account.simulate(Dv["W"], H, 200, 10, 0.40, 0.0007, start=S0, end=S1)
    rv_ = dv["equity"].pct_change().fillna(dv["equity"].iloc[0] / 200 - 1); mv = lab.metrics(rv_)
    grid.append({"variant": nm, "end": dv["equity"].iloc[-1], "sharpe": mv["sharpe"], "mdd": mv["mdd"]})
    print(nm, round(dv["equity"].iloc[-1]), round(mv["sharpe"], 2), round(mv["mdd"] * 100, 1), flush=True)
R["oos_grid"] = grid
json.dump(R, open(os.path.join(lab.RES, "report_numbers.json"), "w"), indent=1, default=str)
