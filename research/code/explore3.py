"""Stage 3 — event / seasonality hypotheses on IS only (2020-07 .. 2024-12)."""
import os
import numpy as np, pandas as pd
import lab

P = lab.load_panel("binance", "1d")
C, H, L = P["close"], P["high"], P["low"]
r = C.pct_change(fill_method=None)
U30 = lab.universe_mask(P, top=30, min_hist=200)
U50 = lab.universe_mask(P, top=50, min_hist=120)
ISs, ISe = pd.Timestamp("2020-07-01"), pd.Timestamp("2024-12-31")
ew = r.where(U50.shift(1)).mean(axis=1)            # equal-weight basket return (eligible yesterday)
btc = r["BTC"]


def fwd(series, n):
    """forward n-day compounded return starting the day AFTER signal (signal at close t)."""
    lr = np.log1p(series.fillna(0))
    return np.expm1(lr[::-1].rolling(n, min_periods=n).sum()[::-1].shift(-1))


def event_table(name, ev, ret=ew, horizons=(1, 3, 5, 10, 20), dedup=5):
    ev = ev[(ev.index >= ISs) & (ev.index <= ISe)]
    t = ev[ev].index
    keep, last = [], None
    for x in t:  # de-duplicate clustered signals
        if last is None or (x - last).days >= dedup:
            keep.append(x); last = x
    out = {"name": name, "n": len(keep)}
    base = {}
    for h in horizons:
        f = fwd(ret, h)
        v = f.reindex(keep).dropna()
        allv = f[(f.index >= ISs) & (f.index <= ISe)].dropna()
        out[f"h{h}"] = v.mean(); out[f"h{h}_ex"] = v.mean() - allv.mean()
        out[f"h{h}_hit"] = (v > 0).mean()
        out[f"h{h}_t"] = (v.mean() - allv.mean()) / (v.std() / np.sqrt(len(v))) if len(v) > 2 else np.nan
    print(f"{name:<48} n {out['n']:3d} | " + " ".join(
        f"h{h}: {out[f'h{h}']*100:6.2f}% ex {out[f'h{h}_ex']*100:6.2f} t {out[f'h{h}_t']:5.2f} hit {out[f'h{h}_hit']*100:3.0f}" for h in horizons), flush=True)
    return out


rows = []
print("=== (a) capitulation breadth: share of top-50 coins closing at a 20d low")
low20 = (C <= C.rolling(20).min()).where(U50)
sh_low = low20.sum(axis=1) / U50.sum(axis=1).replace(0, np.nan)
for th in [0.3, 0.5, 0.7]:
    rows.append(event_table(f"share at 20d low >= {th}", sh_low >= th))
dd30 = (C / C.rolling(30).max() - 1).where(U50).median(axis=1)
for th in [-0.3, -0.4, -0.5]:
    rows.append(event_table(f"median coin dd from 30d high <= {th}", dd30 <= th))

print("=== (b) breadth thrust: share above SMA20 jumps from <25% to >65% within 10d")
ab20 = (C > C.rolling(20).mean()).where(U50)
sh = ab20.sum(axis=1) / U50.sum(axis=1).replace(0, np.nan)
for lo, hi in [(0.25, 0.65), (0.2, 0.7), (0.3, 0.6)]:
    ev = (sh > hi) & (sh.rolling(10).min() < lo)
    rows.append(event_table(f"thrust {lo}->{hi} 10d", ev))

print("=== (e) BTC volatility compression -> breakout direction (daily)")
rng = (H["BTC"] - L["BTC"]) / C["BTC"]
comp = rng.rolling(7).mean() / rng.rolling(60).mean()
up = C["BTC"] > C["BTC"].shift(1).rolling(20).max()
dn = C["BTC"] < C["BTC"].shift(1).rolling(20).min()
for th in [0.6, 0.7]:
    rows.append(event_table(f"BTC compress<{th} & 20d breakout UP", (comp.shift(1) < th) & up, ret=btc))
    rows.append(event_table(f"BTC compress<{th} & 20d breakout DOWN", (comp.shift(1) < th) & dn, ret=btc))
rows.append(event_table("BTC 20d breakout UP (any)", up, ret=btc))
rows.append(event_table("BTC 20d breakout DOWN (any)", dn, ret=btc))

print("=== big down day for basket (< -8%), next days")
for th in [-0.08, -0.12]:
    rows.append(event_table(f"EW basket day < {th}", ew < th))
    rows.append(event_table(f"EW basket day > {-th}", ew > -th))

pd.DataFrame(rows).to_csv(os.path.join(lab.RES, "stage3_events_is.csv"), index=False)

print("=== (c,d) hourly seasonality + CME weekend gap (BTC, ETH 1h, IS)")
for sym in ["BTCUSDT", "ETHUSDT"]:
    k = pd.read_parquet(os.path.join(lab.LAKE, "binance", "um", "klines", "1h", f"{sym}.parquet"))
    k["ts"] = pd.to_datetime(k["ts"], utc=True).dt.tz_localize(None)
    k = k.set_index("ts").loc[ISs:ISe]
    hr = k["close"].pct_change()
    g = hr.groupby(hr.index.hour)
    tab = pd.DataFrame({"mean_bp": g.mean() * 1e4, "t": g.mean() / (g.std() / np.sqrt(g.count()))})
    # split-half stability: 2020-22 vs 2023-24
    a = hr.loc[:"2022-12-31"]; b = hr.loc["2023-01-01":]
    tab["h1_bp"] = a.groupby(a.index.hour).mean() * 1e4
    tab["h2_bp"] = b.groupby(b.index.hour).mean() * 1e4
    print(sym); print(tab.round(2).T.to_string())
    tab.to_csv(os.path.join(lab.RES, f"stage3_hour_{sym}.csv"))
    # CME gap: Fri 21:00 UTC close vs Sun 23:00 UTC open (CME reopens ~22-23 UTC)
    c = k["close"]
    fri = c[(c.index.dayofweek == 4) & (c.index.hour == 20)]  # bar 20:00-21:00 close = 21:00
    rows2 = []
    for t0, px in fri.items():
        sun = t0 + pd.Timedelta(days=2, hours=2)  # Sunday 22:00 bar -> close 23:00
        if sun not in c.index:
            continue
        gap = c[sun] / px - 1
        t1 = sun + pd.Timedelta(hours=48)
        if t1 not in c.index:
            continue
        nxt = c[t1] / c[sun] - 1
        rows2.append((t0, gap, nxt))
    g2 = pd.DataFrame(rows2, columns=["fri", "gap", "next48h"])
    big = g2[g2.gap.abs() > 0.02]
    print(f"  CME gaps |gap|>2%: n={len(big)}, corr(gap,next48h)={big.gap.corr(big.next48h):.3f}, "
          f"fill-direction hit={(np.sign(big.gap) != np.sign(big.next48h)).mean():.2f}, "
          f"mean fade pnl={(-np.sign(big.gap) * big.next48h).mean()*100:.2f}%")
