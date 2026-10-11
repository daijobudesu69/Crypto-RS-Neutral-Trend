"""Grafik dan angka laporan RNT v1.1. Hanya butuh CSV di research/results dan research/audit_response
(dibuat oleh report_v11_data.py dan r01-r07), jadi bisa dijalankan di mana saja.

Keluaran: research/charts/v11_*.png dan research/results/v11_report_stats.json."""
import os, json
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
AUD = os.path.join(HERE, "..", "audit_response")
CH = os.path.join(HERE, "..", "charts")

BLUE, ORANGE, AQUA, RED, GREY, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#8a8985", "#7a5ad6"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.6, "lines.linewidth": 1.9, "axes.titlesize": 11.5, "axes.titleweight": "bold",
                     "axes.titlelocation": "left", "axes.axisbelow": True})

oos = pd.read_csv(os.path.join(RES, "v11_series_oos.csv"), index_col=0, parse_dates=True)
ist = pd.read_csv(os.path.join(RES, "v11_series_is.csv"), index_col=0, parse_dates=True)
trips_oos = pd.read_csv(os.path.join(AUD, "v11_oos_trips.csv"), parse_dates=["entry", "exit"])
trips_is = pd.read_csv(os.path.join(RES, "v11_is_trips.csv"), parse_dates=["entry", "exit"])
R = {}


# ------------------------------------------------------------------ metrik
def rets(eq):
    return eq.pct_change().fillna(eq.iloc[0] / 200 - 1)


def dd_of(eq):
    return eq / eq.cummax() - 1


def underwater_days(eq):
    dd, cur, best, best_end = dd_of(eq), 0, 0, None
    for dt, v in dd.items():
        cur = cur + 1 if v < 0 else 0
        if cur > best:
            best, best_end = cur, dt
    return best, best_end


def met(eq):
    r = rets(eq)
    days = len(r)
    dd = dd_of(eq)
    down = r[r < 0]
    sharpe = r.mean() / r.std() * np.sqrt(365)
    sortino = r.mean() / np.sqrt((np.minimum(r, 0) ** 2).mean()) * np.sqrt(365)
    cagr = (eq.iloc[-1] / 200) ** (365 / days) - 1
    uw, uw_end = underwater_days(eq)
    mon = (1 + r).groupby(r.index.to_period("M")).prod() - 1
    return {"end": float(eq.iloc[-1]), "total": float(eq.iloc[-1] / 200 - 1), "cagr": float(cagr), "vol": float(r.std() * np.sqrt(365)),
            "sharpe": float(sharpe), "sortino": float(sortino), "mdd": float(dd.min()), "mdd_date": str(dd.idxmin().date()),
            "calmar": float(cagr / -dd.min()), "avg_dd": float(dd.mean()), "uw_days": int(uw), "uw_end": str(uw_end.date()) if uw_end is not None else None,
            "pos_months": int((mon > 0).sum()), "n_months": int(len(mon)), "best_month": float(mon.max()), "best_month_name": str(mon.idxmax()),
            "worst_month": float(mon.min()), "worst_month_name": str(mon.idxmin()), "best_day": float(r.max()), "best_day_date": str(r.idxmax().date()),
            "worst_day": float(r.min()), "worst_day_date": str(r.idxmin().date()), "peak": float(eq.max()), "trough": float(eq.min())}


def monthly(eq):
    r = rets(eq)
    return (1 + r).groupby(r.index.to_period("M")).prod() - 1


def yearly(eq):
    r = rets(eq)
    return (1 + r).groupby(r.index.year).prod() - 1


def usd(x, _=None):
    return f"{x:,.0f}"


def save(fig, name):
    fig.savefig(os.path.join(CH, name), dpi=130, bbox_inches="tight", facecolor=SURF)
    plt.close(fig)
    print("chart", name)


def label_end(ax, s, color, text, dy=0, bold=False):
    ax.annotate(text, (s.index[-1], s.iloc[-1]), xytext=(6, dy), textcoords="offset points", color=color, va="center",
                fontsize=9, fontweight="bold" if bold else "normal", annotation_clip=False)


# ------------------------------------------------------------------ angka
for tag, df in (("oos", oos), ("is", ist)):
    R[tag] = {col: met(df[col]) for col in ["rnt", "rs", "tr", "cost2x", "late1d", "filter_off", "btc", "ew20"] + (["v10"] if tag == "oos" else [])}
    R[tag]["yearly"] = {c: {str(k): float(v) for k, v in yearly(df[c]).items()} for c in ["rnt", "rs", "tr", "btc"]}
    R[tag]["monthly"] = {str(k): float(v) for k, v in monthly(df["rnt"]).items()}
    R[tag]["monthly_rs"] = {str(k): float(v) for k, v in monthly(df["rs"]).items()}
    R[tag]["monthly_tr"] = {str(k): float(v) for k, v in monthly(df["tr"]).items()}
    r = rets(df["rnt"]); b = df["btc"].pct_change().fillna(0)
    beta = np.cov(r, b)[0, 1] / b.var()
    R[tag]["beta_btc"] = float(beta)
    R[tag]["corr_btc"] = float(np.corrcoef(r, b)[0, 1])
    R[tag]["corr_engines"] = float(np.corrcoef(rets(df["rs"]), rets(df["tr"]))[0, 1])
    R[tag]["gross_avg"] = float(df["gross_lev"].mean()); R[tag]["gross_max"] = float(df["gross_lev"].max())
    R[tag]["net_avg"] = float(df["net_lev"].mean()); R[tag]["net_max"] = float(df["net_lev"].max()); R[tag]["net_min"] = float(df["net_lev"].min())
    R[tag]["days"] = int(len(df))

# rolling window statistik gabungan IS+OOS (seri return berurutan; dua venue berbeda tapi seri v1.1 yang sama)
comb = pd.concat([rets(ist["rnt"]), rets(oos["rnt"])])
eqc = (1 + comb).cumprod() * 200
for w in (90, 180, 365, 730):
    roll = eqc / eqc.shift(w) - 1
    roll = roll.dropna()
    R[f"roll_{w}"] = {"n": int(len(roll)), "pos": float((roll > 0).mean()), "median": float(roll.median()), "p10": float(roll.quantile(0.1)),
                      "p90": float(roll.quantile(0.9)), "min": float(roll.min()), "max": float(roll.max())}


def trip_stats(t):
    c = t[t["exit"].notna()].copy()
    c["days"] = (c["exit"] - c["entry"]).dt.days
    w, l = c[c.pnl > 0], c[c.pnl <= 0]
    out = {"n": int(len(c)), "open": int(t["exit"].isna().sum()), "win_rate": float((c.pnl > 0).mean()), "avg_win": float(w.pnl.mean()),
           "avg_loss": float(l.pnl.mean()), "pf": float(w.pnl.sum() / -l.pnl.sum()), "hold_med": float(c.days.median()), "hold_mean": float(c.days.mean()),
           "hold_p90": float(c.days.quantile(0.9)), "pnl_closed": float(c.pnl.sum()), "pnl_open": float(t[t["exit"].isna()].pnl.sum())}
    for nm, s in (("long", 1), ("short", -1)):
        x = c[c.side == s]
        out[nm] = {"n": int(len(x)), "win_rate": float((x.pnl > 0).mean()), "pnl": float(x.pnl.sum()), "avg": float(x.pnl.mean()),
                   "pnl_with_open": float(t[t.side == s].pnl.sum())}
    srt = t.pnl.sort_values(ascending=False)  # semua posisi incl. terbuka (sama dengan r04)
    out["top5_share"] = float(srt.head(5).sum() / t.pnl.sum()); out["top10_share"] = float(srt.head(10).sum() / t.pnl.sum())
    out["top20_sum"] = float(srt.head(20).sum()); out["total_all"] = float(t.pnl.sum())
    out["minus_top20"] = float(t.pnl.sum() - srt.head(20).sum())
    out["minus_top_bottom20"] = float(t.pnl.sum() - srt.head(20).sum() - srt.tail(20).sum())
    out["best"] = c.sort_values("pnl", ascending=False).head(5)[["entry", "exit", "coin", "side", "pnl"]].astype(str).values.tolist()
    out["worst"] = c.sort_values("pnl").head(5)[["entry", "exit", "coin", "side", "pnl"]].astype(str).values.tolist()
    return out


R["trips_oos"] = trip_stats(trips_oos)
R["trips_is"] = trip_stats(trips_is)
R["open_oos"] = trips_oos[trips_oos["exit"].isna()].sort_values("pnl", ascending=False)[["coin", "side", "pnl", "notional"]].round(2).values.tolist()
cp_oos = pd.read_csv(os.path.join(RES, "v11_coin_pnl_oos.csv"), index_col=0)
cp_is = pd.read_csv(os.path.join(RES, "v11_coin_pnl_is.csv"), index_col=0)
R["coin_oos_top"] = cp_oos.sort_values("pnl", ascending=False).head(10).round(1).to_dict("index")
R["coin_oos_bottom"] = cp_oos.sort_values("pnl").head(10).round(1).to_dict("index")
R["coin_is_top"] = cp_is.sort_values("pnl", ascending=False).head(10).round(1).to_dict("index")
R["coin_is_bottom"] = cp_is.sort_values("pnl").head(10).round(1).to_dict("index")

# ================================================================== C1 ekuitas OOS
fig, ax = plt.subplots(3, 1, figsize=(10.5, 9.6), sharex=True, gridspec_kw={"height_ratios": [3, 1.2, 1.1]})
a = ax[0]
a.plot(oos.index, oos["v10"], color=AQUA, lw=1.3, ls="--", label="RNT v1.0 (sebelum audit, 522 USD)")
a.plot(oos.index, oos["rnt"], color=BLUE, lw=2.4, label="RNT v1.1 (berlaku, 440 USD)", zorder=3)
a.plot(oos.index, oos["btc"], color=ORANGE, lw=1.5, label="Beli & tahan BTC")
a.plot(oos.index, oos["ew20"], color=GREY, lw=1.4, label="Basket rata 20 koin")
a.axhline(200, color=INK2, lw=0.8, ls=":")
a.axvline(pd.Timestamp("2026-07-31"), color=INK2, lw=0.8, ls=":")
a.annotate("31 Jul 2026: 299 USD\n(Agu–Sep +47%)", (pd.Timestamp("2026-07-31"), 299), xytext=(-125, 38), textcoords="offset points",
           fontsize=9, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
label_end(a, oos["v10"], AQUA, f"v1.0: {oos['v10'].iloc[-1]:,.0f}", dy=8)
label_end(a, oos["rnt"], BLUE, f"v1.1: {oos['rnt'].iloc[-1]:,.0f}", dy=-4, bold=True)
label_end(a, oos["btc"], ORANGE, f"BTC: {oos['btc'].iloc[-1]:,.0f}")
label_end(a, oos["ew20"], GREY, f"Basket: {oos['ew20'].iloc[-1]:,.0f}")
a.set_ylabel("Ekuitas (USD)"); a.set_title("Modal 200 USD, Jan 2025 → 30 Sep 2026 (harga HYPE, aturan v1.1)")
a.legend(loc="upper left", frameon=False, fontsize=9)
ddr = dd_of(oos["rnt"]) * 100
ax[1].fill_between(ddr.index, ddr.values, 0, color=RED, alpha=0.25); ax[1].plot(ddr.index, ddr.values, color=RED, lw=1.0)
ddb = dd_of(oos["btc"]) * 100
ax[1].plot(ddb.index, ddb.values, color=ORANGE, lw=1.0, alpha=0.8, label="BTC")
ax[1].set_ylabel("Drawdown (%)"); ax[1].legend(loc="lower left", frameon=False, fontsize=8)
ax[1].annotate(f"RNT maks {ddr.min():.1f}% ({ddr.idxmin():%d %b %Y})", (ddr.idxmin(), ddr.min()), xytext=(8, -2), textcoords="offset points", fontsize=8.5)
vol = rets(oos["rnt"]).rolling(30).std() * np.sqrt(365) * 100
volb = oos["btc"].pct_change().rolling(30).std() * np.sqrt(365) * 100
ax[2].plot(vol.index, vol.values, color=BLUE, label="RNT"); ax[2].plot(volb.index, volb.values, color=ORANGE, lw=1.4, label="BTC")
ax[2].set_ylabel("Volatilitas 30h\n(% tahunan)"); ax[2].legend(loc="upper left", frameon=False, ncol=2, fontsize=8.5)
ax[2].xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
fig.align_ylabels(ax)
save(fig, "v11_oos_equity.png")

# ================================================================== C2 bulanan OOS
mo = monthly(oos["rnt"]) * 100
fig, ax = plt.subplots(figsize=(10.5, 4.3))
cols = [BLUE if v >= 0 else RED for v in mo.values]
ax.bar([str(p) for p in mo.index], mo.values, color=cols, width=0.72)
for i, v in enumerate(mo.values):
    ax.text(i, v + (0.8 if v >= 0 else -0.8), f"{v:+.1f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=8)
ax.axhline(0, color=INK2, lw=0.8)
ax.set_title(f"Return bulanan OOS v1.1 (13 dari 21 bulan positif; 4 bulan terbaik = {mo.sort_values().tail(4).sum():+.0f} poin)")
ax.set_ylabel("%"); plt.setp(ax.get_xticklabels(), rotation=60, ha="right", fontsize=8.5)
ax.set_ylim(mo.min() - 5, mo.max() + 5)
save(fig, "v11_oos_monthly.png")

# ================================================================== C3 mesin OOS
fig, ax = plt.subplots(2, 1, figsize=(10.5, 7.2), sharex=True, gridspec_kw={"height_ratios": [2.6, 1]})
ax[0].plot(oos.index, oos["rnt"], color=BLUE, lw=2.4, label="RNT gabungan")
ax[0].plot(oos.index, oos["rs"], color=AQUA, label="Mesin 1 saja (RS-Neutral)")
ax[0].plot(oos.index, oos["tr"], color=ORANGE, label="Mesin 2 saja (Trend)")
ax[0].axhline(200, color=INK2, lw=0.8, ls=":")
label_end(ax[0], oos["rnt"], BLUE, f"{oos['rnt'].iloc[-1]:,.0f}", bold=True); label_end(ax[0], oos["rs"], AQUA, f"{oos['rs'].iloc[-1]:,.0f}")
label_end(ax[0], oos["tr"], ORANGE, f"{oos['tr'].iloc[-1]:,.0f}")
ax[0].set_ylabel("Ekuitas (USD), masing-masing akun 200 USD"); ax[0].legend(frameon=False, loc="upper left"); ax[0].set_title("OOS v1.1: kontribusi tiap mesin")
for col, c in (("rs", AQUA), ("tr", ORANGE)):
    d = dd_of(oos[col]) * 100
    ax[1].plot(d.index, d.values, color=c, lw=1.1)
ax[1].set_ylabel("Drawdown (%)"); ax[1].xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
save(fig, "v11_oos_engines.png")

# ================================================================== C4 ekuitas IS (log)
fig, ax = plt.subplots(2, 1, figsize=(10.5, 7.6), sharex=True, gridspec_kw={"height_ratios": [2.6, 1.2]})
a = ax[0]
a.semilogy(ist.index, ist["rnt"], color=BLUE, lw=2.2, label="RNT v1.1")
a.semilogy(ist.index, ist["btc"], color=ORANGE, lw=1.4, label="Beli & tahan BTC")
a.semilogy(ist.index, ist["ew20"], color=GREY, lw=1.3, label="Basket rata 20 koin")
a.axhline(200, color=INK2, lw=0.8, ls=":")
a.set_yticks([200, 400, 700, 1000, 2000, 3500]); a.yaxis.set_major_formatter(FuncFormatter(usd)); a.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
label_end(a, ist["rnt"], BLUE, f"{ist['rnt'].iloc[-1]:,.0f}", bold=True); label_end(a, ist["btc"], ORANGE, f"{ist['btc'].iloc[-1]:,.0f}")
label_end(a, ist["ew20"], GREY, f"{ist['ew20'].iloc[-1]:,.0f}")
uw, uw_end = underwater_days(ist["rnt"])
uw_start = uw_end - pd.Timedelta(days=uw)
a.axvspan(uw_start, uw_end, color=RED, alpha=0.07)
a.text(uw_start + (uw_end - uw_start) / 2, 214, f"Underwater terlama: {uw} hari\n({uw_start:%d %b %Y} → {uw_end:%d %b %Y})",
       ha="center", va="bottom", fontsize=9, color=RED, fontweight="bold")
a.set_ylabel("Ekuitas (USD, skala log)"); a.legend(frameon=False, loc="upper left")
a.set_title("IS v1.1: Jul 2020 → Des 2024, Binance + koin mati + funding riil, akun 200 USD")
d = dd_of(ist["rnt"]) * 100
ax[1].fill_between(d.index, d.values, 0, color=RED, alpha=0.25); ax[1].plot(d.index, d.values, color=RED, lw=1)
ax[1].set_ylabel("Drawdown (%)"); ax[1].annotate(f"maks {d.min():.1f}% ({d.idxmin():%b %Y})", (d.idxmin(), d.min()), xytext=(8, 0), textcoords="offset points", fontsize=9)
ax[1].xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
save(fig, "v11_is_equity.png")

# ================================================================== C5 tahunan
yrs = sorted(set(R["is"]["yearly"]["rnt"]) | set(R["oos"]["yearly"]["rnt"]))
fig, ax = plt.subplots(figsize=(10.5, 4.6))
x = np.arange(len(yrs)); w = 0.2
for i, (c, col, nm) in enumerate([("rnt", BLUE, "RNT"), ("rs", AQUA, "Mesin 1"), ("tr", ORANGE, "Mesin 2"), ("btc", GREY, "BTC")]):
    vals = []
    for y in yrs:
        src = R["is"] if y in R["is"]["yearly"]["rnt"] else R["oos"]
        vals.append(src["yearly"][c][y] * 100)
    ax.bar(x + (i - 1.5) * w, vals, w, color=col, label=nm)
    for xi, v in zip(x + (i - 1.5) * w, vals):
        if c == "rnt":
            ax.text(xi, v + (3 if v >= 0 else -3), f"{v:+.0f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=8.5, fontweight="bold")
ax.set_xticks(x); ax.set_xticklabels([y + ("*" if y == "2026" else "") + (" (OOS)" if y in ("2025", "2026") else " (IS)") for y in yrs])
ax.axhline(0, color=INK2, lw=0.8); ax.set_ylabel("Return tahunan (%)"); ax.legend(frameon=False, ncol=4, loc="upper left")
ax.set_title("Return per tahun kalender. 2020 mulai Juli, 2026 sampai September (*)")
save(fig, "v11_yearly.png")

# ================================================================== C6 heatmap bulanan IS+OOS
allm = pd.concat([monthly(ist["rnt"]), monthly(oos["rnt"])]) * 100
tab = pd.DataFrame({"y": allm.index.year, "m": allm.index.month, "v": allm.values}).pivot(index="y", columns="m", values="v")
fig, ax = plt.subplots(figsize=(10.5, 4.2))
im = ax.imshow(tab.values, cmap="RdBu", vmin=-30, vmax=30, aspect="auto")
ax.set_xticks(range(12)); ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"])
ax.set_yticks(range(len(tab))); ax.set_yticklabels(tab.index)
ax.grid(False)
for i in range(tab.shape[0]):
    for j in range(tab.shape[1]):
        v = tab.values[i, j]
        if not np.isnan(v):
            ax.text(j, i, f"{v:+.0f}", ha="center", va="center", fontsize=8.5, color="white" if abs(v) > 18 else INK)
ax.set_title("Return bulanan RNT v1.1 (%), 2020 – 2026 (IS 2020–2024 digabung OOS 2025–2026)")
save(fig, "v11_monthly_heatmap.png")

# ================================================================== C7 rezim
rg = pd.read_csv(os.path.join(AUD, "r02_regime.csv"))
fig, axs = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
for a, st, ttl in zip(axs, ["v1.1 IS Binance+mati", "v1.1 OOS HYPE"], ["IS 2020–2024 (+koin mati)", "OOS 2025–2026 (HYPE)"]):
    s = rg[rg["set"] == st].set_index("regime")
    order = ["BTC 90h naik", "BTC 90h turun", "dispersi tinggi", "dispersi rendah", "turun & dispersi tinggi"]
    short = ["BTC 90h\nnaik", "BTC 90h\nturun", "dispersi\ntinggi", "dispersi\nrendah", "turun &\ndispersi tinggi"]
    s = s.loc[order]
    xx = np.arange(len(order)); w = 0.26
    a.bar(xx - w, s["m1_ann"] * 100, w, color=AQUA, label="Mesin 1")
    a.bar(xx, s["m2_ann"] * 100, w, color=ORANGE, label="Mesin 2")
    a.bar(xx + w, s["duet_ann"] * 100, w, color=BLUE, label="RNT")
    a.set_xticks(xx); a.set_xticklabels([f"{o}\n({sh*100:.0f}% hari)" for o, sh in zip(short, s["share_days"])], fontsize=7.5)
    a.axhline(0, color=INK2, lw=0.8); a.set_title(ttl)
axs[0].set_ylabel("Return tahunan (%)"); axs[0].legend(frameon=False, fontsize=8.5)
fig.suptitle("Alpha pro-siklus: untung terutama saat BTC 90 hari naik", x=0.06, ha="left", fontsize=12, fontweight="bold", y=1.0)
save(fig, "v11_regime.png")

# ================================================================== C8 konsentrasi
fig, axs = plt.subplots(1, 3, figsize=(13, 4.4))
for a, t, ttl in ((axs[0], trips_oos, "OOS"), (axs[1], trips_is, "IS")):
    c = t.pnl.sort_values(ascending=False).values
    cum = np.cumsum(c)
    a.plot(np.arange(1, len(c) + 1), cum, color=BLUE)
    a.axhline(c.sum(), color=INK2, lw=0.8, ls=":"); a.text(0.97, 0.06, f"garis titik-titik = total {c.sum():+,.0f} USD\n(termasuk posisi terbuka)", transform=a.transAxes, ha="right", fontsize=8.5, color=INK2)
    a.axhline(0, color=INK2, lw=0.6)
    a.set_title(f"{ttl}: PnL kumulatif (terbaik → terburuk)", fontsize=10.5)
    a.set_xlabel("jumlah posisi (terbaik → terburuk)"); a.set_ylabel("USD")
    for n in (10, 20):
        a.axvline(n, color=GREY, lw=0.7, ls="--")
        a.text(len(c) * 0.12, cum.max() * (0.30 if n == 10 else 0.20), f"{n} terbaik: {cum[n-1]:+,.0f} USD", fontsize=8.5, color=INK2)
a = axs[2]
cc = cp_oos.sort_values("pnl")
sel = pd.concat([cc.head(8), cc.tail(8)])
a.barh(sel.index, sel["pnl"], color=[RED if v < 0 else BLUE for v in sel["pnl"]])
a.set_title("OOS: PnL per koin (8 terburuk & 8 terbaik)", fontsize=10.5); a.set_xlabel("USD"); a.tick_params(axis="y", labelsize=8)
save(fig, "v11_concentration.png")

# ================================================================== C9 distribusi posisi
fig, axs = plt.subplots(1, 3, figsize=(13, 4.0))
c = trips_oos[trips_oos["exit"].notna()].copy(); c["days"] = (c["exit"] - c["entry"]).dt.days
axs[0].hist(c.pnl.clip(-8, 12), bins=50, color=BLUE)
axs[0].axvline(0, color=INK2, lw=0.8); axs[0].set_title("OOS: PnL per posisi (USD)"); axs[0].set_xlabel("USD")
axs[1].hist(c.days.clip(0, 60), bins=np.arange(0, 62, 2), color=AQUA)
axs[1].axvline(c.days.median(), color=INK, lw=1, ls="--"); axs[1].text(c.days.median() + 1, axs[1].get_ylim()[1] * 0.85, f"median {c.days.median():.0f} hari", fontsize=9)
axs[1].set_title("OOS: lama pegang (hari)"); axs[1].set_xlabel("hari")
ls = c.groupby("side").pnl.agg(["sum", "count"])
bars = axs[2].bar(["Long", "Short"], [ls.loc[1, "sum"], ls.loc[-1, "sum"]], color=[BLUE, ORANGE], width=0.5)
for b, v, n in zip(bars, [ls.loc[1, "sum"], ls.loc[-1, "sum"]], [ls.loc[1, "count"], ls.loc[-1, "count"]]):
    axs[2].text(b.get_x() + b.get_width() / 2, v + 2, f"{v:+.0f} USD\n({n} posisi)", ha="center", fontsize=9)
axs[2].set_title("OOS: PnL per sisi (selesai)"); axs[2].set_ylabel("USD"); axs[2].set_ylim(0, max(ls["sum"]) * 1.25)
save(fig, "v11_trips.png")

# ================================================================== C10 stres
fig, axs = plt.subplots(1, 2, figsize=(12, 4.4))
for a, df, ttl in ((axs[0], oos, "OOS (HYPE)"), (axs[1], ist, "IS (Binance + koin mati)")):
    items = [("Dasar v1.1", df["rnt"].iloc[-1], BLUE), ("Biaya 2×", df["cost2x"].iloc[-1], VIOLET), ("Telat 1 hari", df["late1d"].iloc[-1], ORANGE),
             ("Mesin 1 saja", df["rs"].iloc[-1], AQUA), ("Mesin 2 saja", df["tr"].iloc[-1], GREY), ("Filter rezim*", df["filter_off"].iloc[-1], "#c8c7c2"),
             ("BTC beli-tahan", df["btc"].iloc[-1], "#d9a38a")]
    lbl, val, col = zip(*items)
    a.barh(lbl[::-1], val[::-1], color=col[::-1])
    for i, v in enumerate(val[::-1]):
        a.text(v + max(val) * 0.01, i, f"{v:,.0f}", va="center", fontsize=9)
    a.axvline(200, color=INK2, lw=0.8, ls=":"); a.set_title(f"{ttl}: nilai akhir dari 200 USD"); a.set_xlim(0, max(val) * 1.15)
fig.text(0.01, -0.02, "* Mesin 1 dimatikan saat BTC 90 hari turun. Opsi pasca-audit, TIDAK diadopsi (hanya dicatat di buku bayangan paper).", fontsize=8.5, color=INK2)
save(fig, "v11_stress.png")

# ================================================================== C11 tetangga parameter
g = pd.DataFrame(json.load(open(os.path.join(AUD, "r05_v11.json")))["grid"]).sort_values("oos_end")
fig, ax = plt.subplots(figsize=(10, 5.4))
cols = [BLUE if v == "dasar" else GREY for v in g["variant"]]
ax.barh(g["variant"], g["oos_end"], color=cols)
for i, (e, s, m) in enumerate(zip(g["oos_end"], g["oos_sharpe"], g["oos_mdd"])):
    ax.text(e + 4, i, f"{e:,.0f}  (Sharpe {s:.2f}, DD {m*100:.0f}%)", va="center", fontsize=8.5)
ax.axvline(200, color=INK2, lw=0.8, ls=":"); ax.axvline(g["oos_end"].median(), color=RED, lw=1, ls="--")
ax.text(g["oos_end"].median() + 3, -0.9, f"median {g['oos_end'].median():.0f}", color=RED, fontsize=9)
ax.set_xlim(0, g["oos_end"].max() * 1.35); ax.set_xlabel("USD akhir (OOS, dari 200 USD)")
ax.set_title("Tetangga parameter v1.1 di OOS: semua 16 varian untung (hanya dilaporkan, tidak dipakai memilih)")
save(fig, "v11_param_grid.png")

# ================================================================== C12 alarm
al = pd.read_csv(os.path.join(AUD, "r06_alarm.csv")).set_index("aturan")
rules = ["DD>35", "DD>25", "DD>20", "ret120<-10", "CUSUM"]
names = ["DD > 35%\n(aturan lama)", "DD > 25%", "DD > 20%", "Return 120h\n< −10%", "CUSUM"]
fig, ax = plt.subplots(figsize=(10.5, 4.6))
x = np.arange(len(rules)); w = 0.26
ax.bar(x - w, al.loc[rules, "H0 tanpa edge | 12bln"] * 100, w, color=GREEN if False else AQUA, label="Strategi TANPA edge: tertangkap dalam 12 bln (tinggi = bagus)")
ax.bar(x, al.loc[rules, "H1/2 edge separuh | 12bln"] * 100, w, color=ORANGE, label="Edge tinggal separuh: alarm dalam 12 bln")
ax.bar(x + w, al.loc[rules, "H1 edge spt backtest | 12bln"] * 100, w, color=RED, label="Strategi SEHAT: alarm palsu dalam 12 bln (rendah = bagus)")
for xi, col in zip(x, rules):
    for off, k in ((-w, "H0 tanpa edge | 12bln"), (0, "H1/2 edge separuh | 12bln"), (w, "H1 edge spt backtest | 12bln")):
        ax.text(xi + off, al.loc[col, k] * 100 + 1.2, f"{al.loc[col, k]*100:.0f}", ha="center", fontsize=8)
ax.set_xticks(x); ax.set_xticklabels(names); ax.set_ylabel("% jalur bootstrap"); ax.set_ylim(0, 135)
ax.legend(frameon=False, fontsize=8.5, loc="upper left")
ax.set_title("Studi alarm (blok bootstrap 30 hari, 4.000 jalur 12 bulan)")
save(fig, "v11_alarm.png")

# ================================================================== C13 ekspektasi 12 bulan
ex = pd.read_csv(os.path.join(AUD, "r07_expectation.csv"))
fig, ax = plt.subplots(figsize=(10, 3.9))
for i, row in ex.iloc[::-1].reset_index(drop=True).iterrows():
    ax.plot([row.p10, row.p90], [i, i], color=GREY, lw=2)
    ax.plot([row.p25, row.p75], [i, i], color=BLUE, lw=9, solid_capstyle="butt")
    ax.plot(row["median"], i, "o", color="white", mec=INK, ms=7, zorder=5)
    ax.text(row.p90 + 3, i, f"median {row['median']:+.0f}%  |  peluang rugi {row.p_rugi:.0f}%  |  DD buruk {row.dd_buruk10:.0f}%", va="center", fontsize=8.5)
ax.axvline(0, color=INK2, lw=0.8); ax.set_yticks(range(len(ex))); ax.set_yticklabels(ex["dunia"].iloc[::-1])
ax.set_xlim(-50, 300); ax.set_xlabel("Return 12 bulan (%): garis abu p10–p90, kotak biru p25–p75")
ax.set_title("Ekspektasi 12 bulan menurut seberapa banyak edge yang bertahan"); ax.grid(axis="y", visible=False)
save(fig, "v11_expectation.png")

# ================================================================== C14 return bergulir 12 bulan
roll = (eqc / eqc.shift(365) - 1).dropna() * 100
fig, ax = plt.subplots(2, 1, figsize=(10.5, 6.2), gridspec_kw={"height_ratios": [2, 1.2]})
ax[0].plot(roll.index, roll.values, color=BLUE); ax[0].axhline(0, color=INK2, lw=0.8)
ax[0].fill_between(roll.index, roll.values, 0, where=roll.values < 0, color=RED, alpha=0.25)
ax[0].axvline(pd.Timestamp("2025-01-01"), color=INK2, lw=0.8, ls=":"); ax[0].text(pd.Timestamp("2025-01-15"), roll.max() * 0.9, "OOS →", fontsize=9)
ax[0].set_title(f"Return bergulir 12 bulan: positif di {R['roll_365']['pos']*100:.0f}% jendela, median {R['roll_365']['median']*100:+.0f}%"); ax[0].set_ylabel("%")
ax[1].hist(roll.values, bins=40, color=BLUE); ax[1].axvline(0, color=INK2, lw=0.8)
ax[1].set_xlabel("Return 12 bulan (%)"); ax[1].set_ylabel("jumlah hari")
save(fig, "v11_rolling12m.png")

# ================================================================== C15 leverage OOS
fig, ax = plt.subplots(figsize=(10.5, 3.8))
ax.plot(oos.index, oos["gross_lev"], color=BLUE, label=f"Gross (rata-rata {oos['gross_lev'].mean():.2f}×, maks {oos['gross_lev'].max():.2f}×)")
ax.plot(oos.index, oos["net_lev"], color=ORANGE, lw=1.3, label=f"Net (rata-rata {oos['net_lev'].mean():+.2f}×)")
ax.axhline(0, color=INK2, lw=0.8); ax.set_ylabel("× ekuitas"); ax.legend(frameon=False, ncol=2, loc="upper left")
ax.set_title("Eksposur OOS v1.1"); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
save(fig, "v11_leverage.png")

# ================================================================== C16 nilai per tanggal akhir
ed = json.load(open(os.path.join(AUD, "r05_v11.json")))
dates = list(ed["end_date"].keys()); v11 = list(ed["end_date"].values()); v10 = list(ed["v10_end_date"].values())
fig, ax = plt.subplots(figsize=(10, 4.0)); x = np.arange(len(dates)); w = 0.38
ax.bar(x - w / 2, v10, w, color=AQUA, label="v1.0"); ax.bar(x + w / 2, v11, w, color=BLUE, label="v1.1")
for xi, a_, b_ in zip(x, v10, v11):
    ax.text(xi - w / 2, a_ + 6, f"{a_:.0f}", ha="center", fontsize=8.5); ax.text(xi + w / 2, b_ + 6, f"{b_:.0f}", ha="center", fontsize=8.5, fontweight="bold")
ax.set_xticks(x); ax.set_xticklabels([pd.Timestamp(d).strftime("%d %b %y") for d in dates]); ax.axhline(200, color=INK2, lw=0.8, ls=":")
ax.legend(frameon=False); ax.set_ylabel("USD"); ax.set_title("Hasil bergantung tanggal akhir: nilai akun 200 USD per akhir periode")
save(fig, "v11_end_dates.png")

json.dump(R, open(os.path.join(RES, "v11_report_stats.json"), "w"), indent=1, default=float)
print("stats saved")
