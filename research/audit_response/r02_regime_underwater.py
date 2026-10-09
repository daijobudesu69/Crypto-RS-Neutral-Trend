"""Audit response r02 — (a) does RNT / engine 1 earn in falling markets? (b) longest underwater spell in IS."""
import os, sys, copy, itertools
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "code"))
import lab, rnt, account

V11 = dict(age_mode="real", pct_scope="traded")
IS = ("2020-07-01", "2024-12-31"); OOS = ("2025-01-01", "2026-09-30")


def sr(x):
    return x.mean() / x.std() * np.sqrt(365) if len(x) > 40 and x.std() > 0 else np.nan


def regime(P, a, b, label, spec_changes, btc_close):
    sp = copy.deepcopy(rnt.SPEC); sp.update(spec_changes)
    D = rnt.build(P, sp)
    get = lambda W: lab.backtest(W, P, start=a, end=b)["net"]
    df = pd.DataFrame({"rnt": get(D["W"]), "m1": get(D["W_rs"]), "m1L": get(D["W_rs"].clip(lower=0)),
                       "m1S": get(D["W_rs"].clip(upper=0)), "m2": get(D["W_tr"])})
    btc = btc_close.reindex(P["close"].index)
    df["tr90"] = (btc / btc.shift(90) - 1).shift(1).reindex(df.index)
    C = P["close"]
    disp = (C / C.shift(28) - 1).where(D["U_rs"]).std(axis=1).shift(1)
    df["disp"] = disp.reindex(df.index)
    df = df.dropna()
    med = df["disp"].median()
    print(f"\n{label} ({len(df)} hari) | Sharpe RNT {sr(df.rnt):.2f}  M1 {sr(df.m1):.2f}  M2 {sr(df.m2):.2f}")
    out = []
    for nm, mk in [("BTC 90h naik", df.tr90 > 0), ("BTC 90h turun", df.tr90 <= 0),
                   ("dispersi tinggi", df.disp > med), ("dispersi rendah", df.disp <= med),
                   ("turun & dispersi tinggi", (df.tr90 <= 0) & (df.disp > med))]:
        x = df[mk]
        row = {"set": label, "regime": nm, "share_days": len(x) / len(df)}
        for c in ["rnt", "m1", "m1L", "m1S", "m2"]:
            row[c + "_ann"] = x[c].mean() * 365; row[c + "_sr"] = sr(x[c])
        out.append(row)
        print(f"  {nm:<24} {len(x)/len(df)*100:3.0f}% hari | RNT {row['rnt_ann']*100:6.1f}%/th SR {row['rnt_sr']:5.2f} | "
              f"M1 {row['m1_ann']*100:6.1f}%/th SR {row['m1_sr']:5.2f} (long {row['m1L_ann']*100:6.1f}, short {row['m1S_ann']*100:6.1f}) | "
              f"M2 {row['m2_ann']*100:6.1f}%/th SR {row['m2_sr']:5.2f}")
    return out


def underwater(eq):
    dd = eq / eq.cummax() - 1
    best, cur, st = (0, None, None), 0, None
    for d, v in dd.items():
        if v < 0:
            st = d if cur == 0 else st
            cur += 1
            if cur > best[0]:
                best = (cur, st, d)
        else:
            cur = 0
    return best


B = lab.load_panel("binance", "1d"); BX = lab.load_panel_ext("binance"); H = lab.load_panel_ext("hl")
btc_bn = B["close"]["BTC"]
rows = []
for ver, ch in [("v1.0", {}), ("v1.1", V11)]:
    print(f"\n######## {ver}")
    rows += regime(BX, *IS, f"{ver} IS Binance+mati", ch, btc_bn)
    rows += regime(B, *IS, f"{ver} IS Binance hidup", ch, btc_bn)
    rows += regime(H, *OOS, f"{ver} OOS HYPE", ch, btc_bn)
pd.DataFrame(rows).to_csv(os.path.join(os.path.dirname(__file__), "r02_regime.csv"), index=False)

print("\n######## underwater terlama (akun 200 USD, IS)")
for ver, ch in [("v1.0", {}), ("v1.1", V11)]:
    for nm, P in [("hidup", B), ("+mati", BX)]:
        sp = copy.deepcopy(rnt.SPEC); sp.update(ch)
        D = rnt.build(P, sp)
        d, _, _ = account.simulate(D["W"], P, 200, 10, 0.40, 0.0007, start=IS[0], end=IS[1])
        n, a, b = underwater(d["equity"])
        y = d["equity"].groupby(d.index.year).last()
        print(f"  {ver} {nm:<6}: {n} hari ({a.date()} -> {b.date()}), DD maks {(d['equity']/d['equity'].cummax()-1).min()*100:.1f}%, akhir {d['equity'].iloc[-1]:.0f}")
