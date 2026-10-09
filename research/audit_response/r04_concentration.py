"""Audit response r04 — profit concentration in a few positions: asymmetric vs symmetric trimming, OOS and IS,
plus the same statistic for a simple benchmark with the same holding style (positive skew is structural?)."""
import os, sys, copy
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "code"))
import lab, rnt, account

V11 = dict(age_mode="real", pct_scope="traded")


def trim_table(trips, label):
    p = trips["pnl"].sort_values(ascending=False).values
    tot = p.sum()
    out = {"set": label, "n": len(p), "total": tot, "top5_share": p[:5].sum() / tot, "top10_share": p[:10].sum() / tot}
    for k in [5, 10, 20]:
        out[f"minus_top{k}"] = tot - p[:k].sum()
        out[f"minus_top_bottom{k}"] = tot - p[:k].sum() - p[-k:].sum()
        out[f"minus_top{k}_pct"] = (tot - p[:k].sum()) / abs(tot)
    q = int(len(p) * 0.03)
    out["trimmed_mean_3pct"] = p[q:len(p) - q].mean()
    out["mean"] = p.mean()
    out["skew"] = pd.Series(p).skew()
    print(f"{label:<34} n {len(p):4d} total {tot:8.1f} | top5 {out['top5_share']*100:5.0f}% top10 {out['top10_share']*100:5.0f}% | "
          f"-top20 {out['minus_top20']:8.1f} | -top20 & -bottom20 {out['minus_top_bottom20']:8.1f} | trimmed mean 3% {out['trimmed_mean_3pct']:+.3f} vs mean {out['mean']:+.3f} | skew {out['skew']:.1f}")
    return out


rows = []
H = lab.load_panel_ext("hl")
BXf = pd.read_pickle(os.path.join(lab.CACHE, "panel_binance_1d_ext_realfund.pkl"))
for ver, ch in [("v1.0", {}), ("v1.1", V11)]:
    sp = copy.deepcopy(rnt.SPEC); sp.update(ch)
    D = rnt.build(H, sp)
    _, t, _ = account.simulate(D["W"], H, 200, 10, 0.40, 0.0007, start="2025-01-01", end="2026-09-30")
    rows.append(trim_table(t, f"{ver} OOS HYPE (USD)"))
    D = rnt.build(BXf, sp)
    _, t, _ = account.simulate(D["W"], BXf, 200, 10, 0.40, 0.0007, start="2020-07-01", end="2024-12-31")
    rows.append(trim_table(t, f"{ver} IS Binance+mati (USD)"))
    # IS in % of notional to remove compounding size effects
    t2 = t.assign(pnl=t["pnl"] / t["notional"])
    rows.append(trim_table(t2, f"{ver} IS (return per posisi)"))
pd.DataFrame(rows).to_csv(os.path.join(os.path.dirname(__file__), "r04_concentration.csv"), index=False)
