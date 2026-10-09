"""Lihat keputusan RNT HARI INI tanpa mengubah state apa pun.

    python run_status.py

Mengambil candle 1d semua perp HYPE (±5–7 menit karena rate limit), lalu mencetak
target bobot, universe, dan rencana order buku paper untuk hari ini.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from rntbot import book as bk
from rntbot import config, control, hype, jobs, notify, plan, store


def main():
    cfg = config.load()
    now = dt.datetime.now(dt.timezone.utc)
    ctx = jobs.Ctx(cfg=cfg, info=hype.InfoClient(cfg.hype.info_url, cfg.hype.weight_per_minute),
                   ctrl=control.read(), outbox=notify.Outbox(now), now=now)
    v = jobs.fetch_view(ctx, jobs.utc_day(now))
    print(f"Hari eksekusi {v.exec_day} (candle {v.last_close_day}) · koin {v.n_coins} · aktif {v.n_traded}")
    print(f"BTC {v.btc_close:,.0f} · 90 hari {'naik' if v.btc_up90 else 'turun'} · skala RS {v.k_rs:.2f} Trend {v.k_tr:.2f}")
    df = pd.DataFrame({"w": v.targets, "w_rs": v.w_rs, "w_tr": v.w_tr, "w_rf": v.targets_rf}).fillna(0.0)
    df["rs_rank"] = pd.Series(v.rs_rank)
    print(df.sort_values("w").round(4).to_string())
    print(f"gross {v.gross:.2f}x  net {v.net:+.2f}x")
    p = store.load_json("paper.json") or {}
    b = p.get("paper") or bk.new_book(cfg.capital_usdc)
    mids = ctx.info.all_mids()
    steps = plan.plan(v.targets, bk.equity(b, mids), bk.notional(b, mids), set(mids),
                      cfg.rules.min_order_usdc, cfg.rules.band)
    print(f"\nBuku paper: ekuitas {bk.equity(b, mids):.2f} USDC, {len(b['positions'])} posisi")
    for s in steps:
        print(f"  {s.kind:<8} {s.coin:<8} {s.current:>9.2f} -> {s.target:>9.2f} USD  ({s.reason})")
    if not steps:
        print("  tidak ada order")


if __name__ == "__main__":
    main()
