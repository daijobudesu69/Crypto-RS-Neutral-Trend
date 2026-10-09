"""Paritas bot vs riset di data NYATA (butuh data lake lokal; tidak jalan di CI).

    python tools/parity_check.py            # ±5 menit

1. Bobot: rntbot.strategy.compute (riwayat penuh) == research rnt.build v1.1.
2. Jendela: bobot dari jendela fetch_days (450 hari, seperti bot live) vs riwayat
   penuh di 25 tanggal OOS: selisih harus kecil.
3. Akun: buku paper bot + perencana order, didorong hari demi hari dengan harga
   close, fee 0,07%, tanpa slippage, funding harian riset -> harus sama dengan
   research account.simulate (OOS v1.1 = 440,5 USD).
"""
from __future__ import annotations

import copy
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "research", "code"))

import account as R_account  # noqa: E402  (riset)
import lab as R_lab  # noqa: E402
import rnt as R_rnt  # noqa: E402

from rntbot import book as bk  # noqa: E402
from rntbot import config, plan, strategy  # noqa: E402

S0, S1 = "2025-01-01", "2026-09-30"


class Costs:
    taker_fee = 0.0007
    paper_slippage = 0.0


def candles_from_panel(H) -> dict:
    """Panel riset -> candle per koin, dengan quote_volume bot == qv riset."""
    out = {}
    for c in H["close"].columns:
        cl = H["close"][c].dropna()
        q = H["qv"][c].reindex(cl.index).fillna(0.0)
        out[c] = pd.DataFrame({"ts": pd.to_datetime(cl.index).tz_localize("UTC"), "open": cl.values,
                               "high": cl.values, "low": cl.values, "close": cl.values,
                               "volume": (q / cl).values})
    return out


def main() -> int:
    cfg = config.load()
    s = cfg.strategy
    H = R_lab.load_panel_ext("hl")
    sp = copy.deepcopy(R_rnt.SPEC); sp.update(age_mode="real", pct_scope="traded")
    Dr = R_rnt.build(H, sp)
    cand = candles_from_panel(H)
    last = H["close"].index[-1]
    P = strategy.build_panel(cand, last)
    Wb = strategy.compute(P, s)

    # 1. riwayat penuh
    A = Dr["W"].reindex(index=P["close"].index, columns=P["close"].columns).fillna(0)
    d1 = (Wb.W - A).abs().max().max()
    print(f"[1] bobot riwayat penuh: selisih maks {d1:.2e}")

    # 2. jendela 450 hari
    days = pd.date_range(S0, S1, periods=25).normalize()
    worst = 0.0
    for d in days:
        v = strategy.make_view(cand, d + pd.Timedelta(days=1), s)
        a = Dr["W"].loc[d]
        a = a[a.abs() > 1e-12]
        keys = set(v.targets) | set(a.index)
        diff = max(abs(v.targets.get(k, 0.0) - float(a.get(k, 0.0))) for k in keys) if keys else 0.0
        worst = max(worst, diff)
    print(f"[2] jendela {cfg.universe.fetch_days} hari vs riwayat penuh, 25 tanggal: selisih bobot maks {worst:.2e}")

    # 3. akun paper bot vs research account.simulate
    dR, tR, oR = R_account.simulate(Dr["W"], H, 200, 10, 0.40, 0.0007, start=S0, end=S1)
    C, F = H["close"], H["fund"]
    b = bk.new_book(200.0)
    meta = {c: {"szDecimals": 10} for c in C.columns}
    idx = C.index[(C.index >= S0) & (C.index <= S1)]
    eqs = []
    n_orders = 0
    for t in idx:
        mids = C.loc[t].dropna().to_dict()
        prev = C.index[C.index.get_loc(t) - 1]
        for coin, p in list(b["positions"].items()):        # funding hari t atas notional close t-1
            px0 = C.at[prev, coin]
            if pd.notna(px0):
                bk.charge_funding(b, coin, p["qty"] * px0 * float(F.at[t, coin]))
        cur = {c: p["qty"] * mids[c] for c, p in b["positions"].items() if c in mids}
        cur.update({c: p["qty"] * p["last_px"] for c, p in b["positions"].items() if c not in mids})
        eq = bk.equity(b, mids)
        w = Wb.W.loc[t]
        steps = plan.plan(w[w.abs() > 0].to_dict(), eq, cur, set(mids), 10, 0.40)
        fills = bk.apply_plan(b, steps, mids, meta, Costs, 10, str(t.date()), floor_buffer=1.0)
        n_orders += len(fills)
        bk.mark(b, mids)
        eqs.append(bk.equity(b, mids))
    e_bot = pd.Series(eqs, index=idx)
    e_res = dR["equity"].reindex(idx)
    d3 = (e_bot - e_res).abs().max()
    print(f"[3] akun 200 USD: bot {e_bot.iloc[-1]:.2f} vs riset {e_res.iloc[-1]:.2f} | selisih maks harian {d3:.4f} USD"
          f" | order bot {n_orders} vs riset {len(oR)}")
    ok = d1 < 1e-9 and worst < 1e-3 and d3 < 0.05
    print("PARITAS OK" if ok else "PARITAS GAGAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
