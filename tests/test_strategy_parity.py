"""Bot == riset. Strategi bot (rntbot/strategy.py) dan aturan order (plan + book) harus
menghasilkan angka yang sama dengan kode riset (research/code) yang menghasilkan
OOS v1.1 = 440,5 USD. Di data nyata dicek tools/parity_check.py; di sini panel sintetis
(termasuk candle hantu volume 0 dan koin yang baru listing)."""
import copy
import os
import sys

import numpy as np
import pandas as pd
import pytest

from fakes import synthetic_candles
from rntbot import book as bk
from rntbot import plan, strategy

RESEARCH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "code")


@pytest.fixture(scope="module")
def research():
    pytest.importorskip("numba")
    sys.path.insert(0, RESEARCH)
    import account as R_account
    import rnt as R_rnt
    return R_rnt, R_account


@pytest.fixture(scope="module")
def data():
    cand = synthetic_candles()
    last = pd.Timestamp("2026-10-08")
    P = strategy.build_panel(cand, last)
    return cand, P


def research_spec(R_rnt):
    sp = copy.deepcopy(R_rnt.SPEC)
    sp.update(age_mode="real", pct_scope="traded")
    return sp


def test_weights_identical_to_research(research, data, cfg):
    R_rnt, _ = research
    cand, P = data
    Dr = R_rnt.build({"close": P["close"], "qv": P["qv"]}, research_spec(R_rnt))
    Wb = strategy.compute(P, cfg.strategy)
    assert (Wb.W - Dr["W"].reindex_like(Wb.W).fillna(0)).abs().max().max() < 1e-12
    assert (Wb.W_rs - Dr["W_rs"].reindex_like(Wb.W_rs).fillna(0)).abs().max().max() < 1e-12
    assert Wb.W.abs().sum(axis=1).max() > 0.3          # strategi benar-benar memegang posisi
    assert (Wb.W < 0).any().any() and (Wb.W > 0).any().any()


def test_window_view_equals_full_history(research, data, cfg):
    """Bot live hanya mengambil fetch_days candle; bobot harus sama dengan riwayat penuh."""
    R_rnt, _ = research
    cand, P = data
    Dr = R_rnt.build({"close": P["close"], "qv": P["qv"]}, research_spec(R_rnt))
    for d in pd.date_range("2026-07-01", "2026-10-08", periods=6).normalize():
        start = pd.Timestamp(d, tz="UTC") - pd.Timedelta(days=cfg.universe.fetch_days)
        sub = {c: df[df["ts"] >= start] for c, df in cand.items()}
        v = strategy.make_view(sub, d + pd.Timedelta(days=1), cfg.strategy)
        a = Dr["W"].loc[d]
        a = a[a.abs() > 1e-12]
        assert set(v.targets) == set(a.index)
        assert max(abs(v.targets[k] - a[k]) for k in a.index) < 1e-9


def test_ghost_candles_do_not_count_as_age(cfg):
    """v1.1: koin dengan candle volume 0 tidak eligible sampai punya 200 hari NYATA."""
    cand = synthetic_candles(ghosts=6, late=0)
    P = strategy.build_panel(cand, pd.Timestamp("2026-10-08"))
    w = strategy.compute(P, cfg.strategy)
    for c in [f"C{i:02d}" for i in range(6)]:
        real = (P["qv"][c] > 0).cumsum()
        assert not (w.U_rs[c] & (real < cfg.strategy.min_hist)).any(), c


def test_account_identical_to_research(research, data, cfg):
    """Buku paper + perencana order, tanpa slippage dan fee 0,07%, == account.simulate riset."""
    R_rnt, R_account = research
    cand, P = data
    Pr = {"close": P["close"], "qv": P["qv"], "fund": P["close"] * 0 + 0.0001}
    Pr["fund"] = Pr["fund"].where(P["close"].notna(), 0.0)
    Dr = R_rnt.build({"close": P["close"], "qv": P["qv"]}, research_spec(R_rnt))
    S0, S1 = "2026-01-01", "2026-10-08"
    dR, _, oR = R_account.simulate(Dr["W"], Pr, 200, 10, 0.40, 0.0007, start=S0, end=S1)

    class Costs:
        taker_fee, paper_slippage = 0.0007, 0.0

    C = P["close"]
    b = bk.new_book(200.0)
    meta = {c: {"szDecimals": 12} for c in C.columns}
    eqs, n = [], 0
    idx = C.index[(C.index >= S0) & (C.index <= S1)]
    for t in idx:
        mids = C.loc[t].dropna().to_dict()
        prev = C.index[C.index.get_loc(t) - 1]
        for coin, p in list(b["positions"].items()):
            if pd.notna(C.at[prev, coin]):
                bk.charge_funding(b, coin, p["qty"] * C.at[prev, coin] * float(Pr["fund"].at[t, coin]))
        cur = {c: p["qty"] * mids.get(c, p["last_px"]) for c, p in b["positions"].items()}
        w = Dr["W"].loc[t]
        steps = plan.plan(w[w.abs() > 0].to_dict(), bk.equity(b, mids), cur, set(mids), 10, 0.40)
        n += len(bk.apply_plan(b, steps, mids, meta, Costs, 10, str(t.date()), floor_buffer=1.0))
        bk.mark(b, mids)
        eqs.append(bk.equity(b, mids))
    e = pd.Series(eqs, index=idx)
    assert n == len(oR) and n > 20
    assert np.allclose(e.values, dR["equity"].reindex(idx).values, atol=1e-6)
