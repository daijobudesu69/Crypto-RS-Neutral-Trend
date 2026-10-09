"""RNT — frozen strategy (spec locked 2026-10-09 BEFORE any OOS run).

Engine 1  RS-NEUTRAL : market-neutral, risk-adjusted relative strength (long strongest / short weakest)
Engine 2  TREND      : long-only Donchian channel position on the most liquid coins
Each engine is scaled to 20% annualised vol; the two books are added (risk parity).

Inputs: daily OHLCV only (HYPE candles). No OI, no funding, no order book, no taker flow.
Run once a day right after the 00:00 UTC daily close (07:00 WIB).
"""
import numpy as np, pandas as pd
import lab, strat as S

SPEC = dict(
    vol_span=30,                 # EWM span (days) for coin volatility
    min_hist=200,                # days of history before a coin is eligible
    liq_win=30,                  # days for average quote volume ranking
    rs_top=20,                   # RS universe: 20 most liquid
    rs_lookbacks=(7, 14, 28, 56),
    rs_in=4, rs_out=8,           # enter rank<=4, hold while rank<=8 (both legs)
    tr_top=5,                    # trend universe: 5 most liquid
    tr_channels=(20, 55, 100),
    tr_coin_vol=0.40,            # per-coin vol budget before sleeve scaling
    sleeve_vol=0.20,             # each engine scaled to 20% annual vol
    vt_lookback=60, vt_cap=2.0,  # trailing window and max scaling factor
    gross_cap=2.5,               # hard cap on total gross exposure (x equity)
    age_mode="candles",          # v1.0: any daily candle counts toward min_hist ("real": only days with volume > 0)
    pct_scope="all",             # v1.0: percentile across every coin with a price ("traded": volume > 0 today; "universe": top-N only)
)


def build(P, spec=SPEC, exclude=()):
    C = P["close"].drop(columns=[c for c in exclude if c in P["close"].columns])
    PP = {k: v[C.columns] for k, v in P.items()}
    r = C.pct_change(fill_method=None)
    vol = lab.ewm_vol(PP, spec["vol_span"])
    U_rs = lab.universe_mask(PP, top=spec["rs_top"], min_hist=spec["min_hist"], liq_win=spec["liq_win"], age_mode=spec.get("age_mode", "candles"))
    U_tr = lab.universe_mask(PP, top=spec["tr_top"], min_hist=spec["min_hist"], liq_win=spec["liq_win"], age_mode=spec.get("age_mode", "candles"))

    scope = {"all": None, "traded": (PP["qv"] > 0) & C.notna(), "universe": U_rs}[spec.get("pct_scope", "all")]
    score = S.ra_score(C, vol, spec["rs_lookbacks"], scope=scope)
    wl, ws = S.hyst_book(score, U_rs, spec["rs_in"], spec["rs_out"])
    W_rs_raw = wl - ws
    W_rs, k_rs = S.book_vol_scale(W_rs_raw, r, spec["sleeve_vol"], spec["vt_lookback"], spec["vt_cap"])

    dp = S.donch_pos(C, spec["tr_channels"])
    W_tr_raw = (dp.clip(lower=0) * (spec["tr_coin_vol"] / vol)).where(U_tr, 0).fillna(0).clip(upper=1.5) / spec["tr_top"]
    W_tr, k_tr = S.book_vol_scale(W_tr_raw, r, spec["sleeve_vol"], spec["vt_lookback"], spec["vt_cap"])

    W = W_rs.add(W_tr, fill_value=0).fillna(0)
    g = W.abs().sum(axis=1)
    W = W.mul((spec["gross_cap"] / g).clip(upper=1.0).fillna(1.0), axis=0)
    return {"W": W, "W_rs": W_rs, "W_tr": W_tr, "W_rs_raw": W_rs_raw, "W_tr_raw": W_tr_raw,
            "k_rs": k_rs, "k_tr": k_tr, "score": score, "U_rs": U_rs, "U_tr": U_tr, "vol": vol}
