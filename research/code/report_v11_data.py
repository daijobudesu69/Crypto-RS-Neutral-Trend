"""Seri harian RNT v1.1 untuk laporan: OOS (HYPE) dan IS (Binance + koin mati + funding riil).

Menjalankan spesifikasi v1.1 (age_mode="real", pct_scope="traded") dan menyimpan, per periode:
  RNT, Mesin 1, Mesin 2, BTC beli-tahan, basket rata 20 koin, v1.0 (OOS saja), filter rezim (tidak diadopsi),
  biaya 2x, telat 1 hari. Plus posisi selesai IS dan agregat PnL per koin.
Butuh data lake + cache panel (research/results/cache), jadi hanya jalan di PC riset. Grafik dibuat oleh
report_v11_charts.py dari CSV yang dihasilkan di sini (jalan di mana saja).
"""
import os, sys, copy, json
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lab, rnt, account

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
V11 = dict(age_mode="real", pct_scope="traded")
IS = ("2020-07-01", "2024-12-31")
OOS = ("2025-01-01", "2026-09-30")


def spec(**kw):
    s = copy.deepcopy(rnt.SPEC); s.update(V11); s.update(kw); return s


def sim(W, P, a, b, cost=0.0007):
    d, t, o = account.simulate(W, P, 200, 10, 0.40, cost, start=a, end=b)
    return d, t, o


def run(P, a, b, tag):
    D = rnt.build(P, spec())
    d, t, o = sim(D["W"], P, a, b)
    out = pd.DataFrame({"rnt": d["equity"]})
    out["rs"] = sim(D["W_rs"], P, a, b)[0]["equity"]
    out["tr"] = sim(D["W_tr"], P, a, b)[0]["equity"]
    out["cost2x"] = sim(D["W"], P, a, b, 0.0015)[0]["equity"]
    out["late1d"] = sim(D["W"].shift(1).fillna(0), P, a, b)[0]["equity"]
    btc = P["close"]["BTC"]
    up = (btc / btc.shift(90) - 1 > 0).astype(float)
    Wf = D["W_rs"].mul(up, axis=0).add(D["W_tr"], fill_value=0)
    out["filter_off"] = sim(Wf, P, a, b)[0]["equity"]
    r = P["close"].pct_change(fill_method=None)
    sl = slice(a, b)
    out["btc"] = (1 + r["BTC"].loc[sl].fillna(0)).cumprod() * 200
    out["ew20"] = (1 + r.where(D["U_rs"].shift(1)).mean(axis=1).loc[sl].fillna(0)).cumprod() * 200
    out["btc_up90"] = up.reindex(out.index)
    out["gross_lev"] = d["gross_lev"]
    out["net_lev"] = d["net_lev"]
    out["orders"] = d["orders"]
    out["fees"] = d["fees"]
    out["pnl_funding"] = d["pnl_funding"]
    out.index.name = "date"
    return out, t, o


oos, t_oos, o_oos = run(lab.load_panel_ext("hl"), *OOS, "oos")
v10 = pd.read_csv(os.path.join(RES, "oos_daily_hype.csv"), index_col=0, parse_dates=True)["equity"]
oos["v10"] = v10.reindex(oos.index)
oos.to_csv(os.path.join(RES, "v11_series_oos.csv"))
print("OOS", oos["rnt"].iloc[-1])

BXf = pd.read_pickle(os.path.join(lab.CACHE, "panel_binance_1d_ext_realfund.pkl"))
is_, t_is, o_is = run(BXf, *IS, "is")
is_.to_csv(os.path.join(RES, "v11_series_is.csv"))
t_is.to_csv(os.path.join(RES, "v11_is_trips.csv"), index=False)
print("IS", is_["rnt"].iloc[-1])

for name, t in (("oos", t_oos), ("is", t_is)):
    c = t  # semua posisi, termasuk yang masih terbuka (mark-to-market), sama dengan r04
    c.groupby("coin").pnl.agg(["sum", "count"]).rename(columns={"sum": "pnl", "count": "n"}).sort_values("pnl").to_csv(
        os.path.join(RES, f"v11_coin_pnl_{name}.csv"))
