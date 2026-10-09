"""Audit response r03 — replace the 'funding = 0' assumption for dead/small Binance coins in IS with REAL funding
from the data.binance.vision archive (futures/um/monthly/fundingRate), then re-run IS v1.0 and v1.1."""
import os, sys, io, zipfile, copy
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "code"))
sys.path.insert(0, r"C:\Crypto data\backtest data and more\scripts")
import lab, rnt, account
import bv_list as BV

IS = dict(start="2020-07-01", end="2024-12-31")
OUT = os.path.join(lab.EXT, "bn_dead", "funding")
os.makedirs(OUT, exist_ok=True)
B = lab.load_panel("binance", "1d")
BX = lab.load_panel_ext("binance")
alive = set(B["close"].columns)

# which non-alive coins were ever held (any version) in IS
held = set()
for ch in [{}, {"age_mode": "real", "pct_scope": "traded"}]:
    sp = copy.deepcopy(rnt.SPEC); sp.update(ch)
    D = rnt.build(BX, sp)
    W = D["W"].loc[IS["start"]:IS["end"]]
    held |= {c for c in W.columns if c not in alive and (W[c].abs() > 0).any()}
held = sorted(held)
inv = {v: k for k, v in lab.BN2HL.items()}
print(len(held), "dead/small coins held in IS:", held, flush=True)


def fetch(coin):
    sym = inv.get(coin, coin) + "USDT"
    p = os.path.join(OUT, f"{sym}.parquet")
    if os.path.exists(p):
        return coin, "cached"
    _, keys = BV._list(f"data/futures/um/monthly/fundingRate/{sym}/")
    frames = []
    for k, _ in keys:
        if not k.endswith(".zip"):
            continue
        r = BV.get("https://data.binance.vision/" + k)
        if r.status_code != 200:
            continue
        z = zipfile.ZipFile(io.BytesIO(r.content))
        d = pd.read_csv(z.open(z.namelist()[0]))
        frames.append(d)
    if not frames:
        return coin, "none"
    d = pd.concat(frames)
    tcol = [c for c in d.columns if "time" in c.lower()][0]
    rcol = [c for c in d.columns if "rate" in c.lower()][0]
    out = pd.DataFrame({"ts": pd.to_datetime(d[tcol], unit="ms", utc=True), "funding_rate": d[rcol].astype(float)})
    out.drop_duplicates("ts").sort_values("ts").to_parquet(p, index=False)
    return coin, len(out)


with ThreadPoolExecutor(12) as ex:
    res = list(ex.map(fetch, held))
print(res, flush=True)

# rebuild the extended panel's funding with the real archive data
dates = BX["close"].index
F = BX["fund"].copy()
got = 0
for coin in held:
    p = os.path.join(OUT, f"{inv.get(coin, coin)}USDT.parquet")
    if os.path.exists(p):
        F[coin] = lab._daily_funding(p, dates).reindex(dates).fillna(0.0)
        got += 1
BXf = dict(BX); BXf["fund"] = F.where(BX["close"].notna(), 0.0)
print(f"real funding loaded for {got}/{len(held)} coins", flush=True)

for ver, ch in [("v1.0", {}), ("v1.1", {"age_mode": "real", "pct_scope": "traded"})]:
    sp = copy.deepcopy(rnt.SPEC); sp.update(ch)
    for nm, P in [("funding mati = 0", BX), ("funding mati = RIIL", BXf)]:
        D = rnt.build(P, sp)
        d, _, _ = account.simulate(D["W"], P, 200, 10, 0.40, 0.0007, **IS)
        r = d["equity"].pct_change().fillna(d["equity"].iloc[0] / 200 - 1); m = lab.metrics(r)
        bt = lab.backtest(D["W"], P, **IS)
        dead_cols = [c for c in held if c in D["W"].columns]
        Wh = D["W"][dead_cols].shift(1).loc[IS["start"]:IS["end"]]
        fpay = (Wh * P["fund"][dead_cols].loc[IS["start"]:IS["end"]]).sum(axis=1)
        print(f"{ver} {nm:<20} akun 200 -> {d['equity'].iloc[-1]:6.0f}  SR {m['sharpe']:.2f}  DD {m['mdd']*100:5.1f}% | "
              f"funding koin mati (bobot) {-fpay.sum()*100:+.1f}% total, {-fpay.mean()*36500:+.2f}%/th", flush=True)
pd.to_pickle(BXf, os.path.join(lab.CACHE, "panel_binance_1d_ext_realfund.pkl"))
