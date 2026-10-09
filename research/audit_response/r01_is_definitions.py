"""Audit response r01 — which rule definitions does the IN-SAMPLE data support?

(1) Ghost history (age rule). On HYPE the API returns ~999 pre-listing daily candles (Binance prices, volume 0),
    so the v1.0 rule "200 daily candles" lets an old coin trade days after its HYPE listing. Binance perp data has
    no such candles, so this behaviour was never tested in IS. Emulate it in IS: before a perp's first day, fill its
    price with Binance SPOT prices (scaled at the junction) and volume 0. Then compare age_mode candles vs real.
(2) Percentile scope: all coins (v1.0 code) vs only the top-20 universe vs only coins trading today.
"""
import os, sys, glob, copy
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "code"))
import lab, rnt, account

IS = dict(start="2020-07-01", end="2024-12-31")
SPOT = os.path.join(lab.LAKE, "binance", "spot", "klines", "1d")


def with_spot_ghosts(P):
    P = {k: v.copy() for k, v in P.items()}
    C = P["close"]
    added, n_days = [], 0
    for coin in C.columns:
        sym = {"kPEPE": "PEPE", "kSHIB": "SHIB", "kBONK": "BONK", "kFLOKI": "FLOKI"}.get(coin, coin)
        f = os.path.join(SPOT, f"{sym}USDT.parquet")
        if not os.path.exists(f):
            continue
        s = pd.read_parquet(f)
        s.index = pd.to_datetime(s["ts"], utc=True).dt.tz_localize(None).values
        first = C[coin].first_valid_index()
        if first is None:
            continue
        ov = pd.concat([C[coin], s["close"]], axis=1, join="inner").dropna().iloc[:10]
        if len(ov) < 5:
            continue
        k = (ov.iloc[:, 0] / ov.iloc[:, 1]).median()
        pre = s.loc[s.index < first]
        pre = pre.loc[pre.index >= C.index[0]]
        if len(pre) == 0:
            continue
        for fld in ["open", "high", "low", "close"]:
            P[fld].loc[pre.index, coin] = pre[fld].values * k
        P["qv"].loc[pre.index, coin] = 0.0
        added.append(coin); n_days += len(pre)
    print(f"spot ghost history added to {len(added)} coins, {n_days} coin-days", flush=True)
    return P


def run(P, spec_changes, label):
    sp = copy.deepcopy(rnt.SPEC); sp.update(spec_changes)
    D = rnt.build(P, sp)
    bt = lab.backtest(D["W"], P, **IS)
    m = lab.metrics(bt["net"])
    btr = lab.backtest(D["W_rs"], P, **IS); mr = lab.metrics(btr["net"])
    d, _, _ = account.simulate(D["W"], P, 200, 10, 0.40, 0.0007, **IS)
    ra = d["equity"].pct_change().fillna(d["equity"].iloc[0] / 200 - 1); ma = lab.metrics(ra)
    print(f"{label:<58} RNT SR {m['sharpe']:.2f} mdd {m['mdd']*100:5.1f}% | Mesin1 SR {mr['sharpe']:.2f} | akun 200 -> {d['equity'].iloc[-1]:6.0f} SR {ma['sharpe']:.2f} DD {ma['mdd']*100:5.1f}%", flush=True)
    return {"label": label, "sr": m["sharpe"], "mdd": m["mdd"], "sr_m1": mr["sharpe"], "acct_end": d["equity"].iloc[-1], "acct_sr": ma["sharpe"], "acct_mdd": ma["mdd"]}


rows = []
for pname, P0 in [("Binance hidup", lab.load_panel("binance", "1d")), ("Binance + mati", lab.load_panel_ext("binance"))]:
    print(f"=== {pname}")
    rows.append(run(P0, {}, f"{pname}: v1.0 (pct all, tanpa hantu)") | {"panel": pname})
    rows.append(run(P0, {"pct_scope": "universe"}, f"{pname}: pct hanya top-20") | {"panel": pname})
    PG = with_spot_ghosts(P0)
    rows.append(run(PG, {}, f"{pname}+hantu spot: umur = semua candle (v1.0)") | {"panel": pname})
    rows.append(run(PG, {"age_mode": "real"}, f"{pname}+hantu spot: umur = hari nyata") | {"panel": pname})
    rows.append(run(PG, {"age_mode": "real", "pct_scope": "traded"}, f"{pname}+hantu spot: umur nyata + pct koin aktif") | {"panel": pname})
    rows.append(run(PG, {"pct_scope": "traded"}, f"{pname}+hantu spot: umur semua + pct koin aktif") | {"panel": pname})
pd.DataFrame(rows).to_csv(os.path.join(os.path.dirname(__file__), "r01_is_definitions.csv"), index=False)
