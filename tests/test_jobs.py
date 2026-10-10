"""Job harian end-to-end dengan data dan bursa tiruan."""
import dataclasses
import datetime as dt

import pandas as pd
import pytest

from fakes import FakeInfo, FakeTrader, synthetic_candles
from rntbot import control, jobs, notify, store

DAY1 = dt.datetime(2026, 10, 10, 0, 5, tzinfo=dt.timezone.utc)


@pytest.fixture(scope="module")
def cand():
    return synthetic_candles(end_day="2026-10-11")


def upto(cand, day):
    """Candle sampai `day` (inklusif), seperti API pada pagi hari berikutnya."""
    d = pd.Timestamp(day, tz="UTC")
    return {c: df[df["ts"] <= d].reset_index(drop=True) for c, df in cand.items()}


def ctx_for(cfg, info, now, mode="paper", trader=None):
    return jobs.Ctx(cfg=cfg, info=info, ctrl=control.Control(mode=mode), outbox=notify.Outbox(now), now=now,
                    trader_factory=(lambda: trader) if trader else None)


def test_first_day_paper(state_dir, cfg, cand):
    info = FakeInfo(upto(cand, "2026-10-09"))
    ctx = ctx_for(cfg, info, DAY1)
    out = jobs.run_daily(ctx)
    assert out and out["exec_day"] == "2026-10-10"
    v = out["view"]
    assert v.last_close_day == "2026-10-09" and v.targets
    p = store.load_json("paper.json")
    assert set(p) >= {"paper", "rf", "last_day"} and "pending_record" not in p
    assert p["paper"]["positions"] and p["paper"]["fees"] > 0
    assert len(store.read("equity")) == 1 and store.read("targets") and store.read("orders")
    assert any("RNT forward test" in m["text"] for m in ctx.outbox.sent + ctx.outbox.items)
    txt = next(m["text"] for m in ctx.outbox.sent + ctx.outbox.items if "RNT forward test" in m["text"])
    assert "Paper" in txt and "PnL:" in txt and "Relative Strength Report" in txt and "Trend Report" in txt
    print(notify.plain(txt))
    # sekali per hari
    assert jobs.run_daily(ctx_for(cfg, info, DAY1 + dt.timedelta(minutes=10))) is None


def test_not_before_close_delay_or_start(state_dir, cfg, cand):
    info = FakeInfo(upto(cand, "2026-10-09"))
    assert jobs.run_daily(ctx_for(cfg, info, DAY1.replace(minute=1))) is None
    later = dataclasses.replace(cfg, forward_start="2026-10-20")
    assert jobs.run_daily(ctx_for(later, info, DAY1)) is None
    assert jobs.run_daily(ctx_for(cfg, info, DAY1, mode="off")) is None


def test_retry_until_data_complete(state_dir, cfg, cand):
    with pytest.raises(jobs.DataIncomplete):
        jobs.run_daily(ctx_for(cfg, FakeInfo(upto(cand, "2026-10-08")), DAY1))      # candle 10-09 belum ada
    info = FakeInfo(upto(cand, "2026-10-09"), fail={"C05"})
    with pytest.raises(jobs.DataIncomplete):
        jobs.run_daily(ctx_for(cfg, info, DAY1))
    ctx = ctx_for(cfg, info, DAY1.replace(hour=3, minute=30))                        # sudah lewat batas
    assert jobs.run_daily(ctx) is not None
    assert any("tidak lengkap" in m["text"] for m in ctx.outbox.sent + ctx.outbox.items)


def test_second_day_funding_and_equity(state_dir, cfg, cand):
    jobs.run_daily(ctx_for(cfg, FakeInfo(upto(cand, "2026-10-09"), funding=0.0001), DAY1))
    info = FakeInfo(upto(cand, "2026-10-10"), funding=0.0001)
    out = jobs.run_daily(ctx_for(cfg, info, DAY1 + dt.timedelta(days=1)))
    assert out and info.calls["funding"] > 0
    rows = store.read("equity")
    assert [r["exec_day"] for r in rows] == ["2026-10-10", "2026-10-11"]
    assert rows[-1]["alarm_level"] == "ok"


def test_live_mode_trades_and_records(state_dir, live_cfg, cand):
    data = upto(cand, "2026-10-09")
    info = FakeInfo(data)
    trader = FakeTrader(info.all_mids(), equity=200.0, agent=live_cfg.execution.agent_address)
    out = jobs.run_daily(ctx_for(live_cfg, info, DAY1, mode="live", trader=trader))
    lv = out["live"]
    assert lv and not lv["errors"] and trader.orders
    ls = store.load_json("live.json")
    assert ls["last_day"] == "2026-10-10" and set(ls["positions"]) == set(trader.pos)
    assert any(r["book"] == "live" for r in store.read("orders"))
    # percobaan kedua di hari yang sama tidak mengirim order lagi
    n = len(trader.orders)
    assert jobs.run_daily(ctx_for(live_cfg, info, DAY1 + dt.timedelta(minutes=10), mode="live", trader=trader)) is None
    assert len(trader.orders) == n


def test_live_without_secret_halts_but_paper_runs(state_dir, live_cfg, cand):
    out = jobs.run_daily(ctx_for(live_cfg, FakeInfo(upto(cand, "2026-10-09")), DAY1, mode="live"))
    assert out["paper"]["paper"]["fills"] and any("HALT" in e for e in out["live"]["errors"])


def test_red_alarm_blocks_new_live_positions(state_dir, live_cfg, cand):
    data = upto(cand, "2026-10-09")
    for i, eq in enumerate([200, 300, 180]):                 # puncak 300, hari ini ±200: DD -33%
        store.append("equity", {"exec_day": f"2026-10-0{i + 1}", "paper_equity": eq}, mirror=False)
    info = FakeInfo(data)
    trader = FakeTrader(info.all_mids(), equity=200.0, agent=live_cfg.execution.agent_address)
    out = jobs.run_daily(ctx_for(live_cfg, info, DAY1, mode="live", trader=trader))
    assert out["alarm"].level == "merah"
    assert trader.orders == [] and out["live"]["skipped"]


def test_run_cycle_main(state_dir, cfg, cand, monkeypatch):
    import run_cycle
    from rntbot import config as C
    monkeypatch.setattr(C, "load", lambda path=None: cfg)
    monkeypatch.setattr(control, "read", lambda paths=None: control.Control(mode="paper"))
    rc = run_cycle.main(now=DAY1, info=FakeInfo(upto(cand, "2026-10-09")))
    assert rc == 0 and store.read("runs")[-1]["daily"] in ("1", "True")


def test_agent_expiry_warns_only_on_schedule(state_dir, cfg):
    import run_cycle
    ex = dataclasses.replace(cfg.execution, agent_valid_until="2026-12-01")
    c2 = dataclasses.replace(cfg, execution=ex)
    sent = []
    for left in range(20, -3, -1):
        now = dt.datetime(2026, 12, 1, 6, tzinfo=dt.timezone.utc) - dt.timedelta(days=left)
        ctx = ctx_for(c2, None, now)
        store.save_json("alerts.json", {k: v for k, v in (store.load_json("alerts.json", {}) or {}).items() if k != "account_check_day"})
        run_cycle._account_checks(ctx)
        sent += [(left, m["text"]) for m in ctx.outbox.items]
    assert [x[0] for x in sent] == [14, 7, 3, 2, 1, 0, -1]
    assert all(len(t.splitlines()) == 1 for _, t in sent)
