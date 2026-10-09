import datetime as dt

import pytest

from fakes import FakeTrader
from rntbot import live

NOW = dt.datetime(2026, 10, 12, 0, 5, tzinfo=dt.timezone.utc)
MIDS = {"A": 10.0, "B": 20.0, "C": 5.0, "D": 2.0}


def run(cfg, trader, targets, mode="live", owned=(), **kw):
    return live.run(targets, "2026-10-12", cfg, trader, mode, NOW, owned=frozenset(owned), **kw)


def test_opens_long_and_short(live_cfg):
    t = FakeTrader(MIDS, equity=200.0)
    r = run(live_cfg, t, {"A": 0.25, "B": -0.25})
    assert not r["errors"]
    assert t.pos["A"] == pytest.approx(5.0) and t.pos["B"] == pytest.approx(-2.5)
    assert all(not o["reduce_only"] for o in t.orders)
    assert t.leverage["A"] == (3, True)
    assert all(o["cloid"].startswith(live.BOT_PREFIX) for o in t.orders)


def test_flip_closes_reduce_only_then_opens(live_cfg):
    t = FakeTrader(MIDS, positions={"A": 5.0}, equity=200.0)
    r = run(live_cfg, t, {"A": -0.25}, owned={"A"})
    assert [(o["is_buy"], o["reduce_only"]) for o in t.orders] == [(False, True), (False, False)]
    assert t.pos["A"] == pytest.approx(-5.0) and not r["errors"]


def test_flip_does_not_open_when_close_fails(live_cfg):
    t = FakeTrader(MIDS, positions={"A": 5.0}, equity=200.0, fail_coins={"A"})
    r = run(live_cfg, t, {"A": -0.25}, owned={"A"})
    assert len(t.orders) == 1 and r["errors"]


def test_reduce_and_close_are_reduce_only(live_cfg):
    t = FakeTrader(MIDS, positions={"A": 10.0, "C": -6.0}, equity=200.0)
    run(live_cfg, t, {"A": 0.25}, owned={"A", "C"})      # A 100 -> 50 USD, C ditutup
    assert all(o["reduce_only"] for o in t.orders)
    assert t.pos["A"] == pytest.approx(5.0) and "C" not in t.pos


def test_foreign_position_halts_without_orders(live_cfg):
    t = FakeTrader(MIDS, positions={"D": 10.0}, equity=200.0)
    with pytest.raises(live.Halt):
        run(live_cfg, t, {"A": 0.25})
    assert t.orders == []


def test_flatten_closes_only_owned(live_cfg):
    t = FakeTrader(MIDS, positions={"A": 5.0, "D": 10.0}, equity=200.0)
    r = run(live_cfg, t, {"A": 0.25}, mode="flatten", owned={"A"})
    assert "A" not in t.pos and t.pos["D"] == 10.0 and any("asing" in e for e in r["errors"])


def test_manage_and_red_alarm_only_reduce(live_cfg):
    for kw in ({"mode": "manage"}, {"reduce_only_mode": True, "block_reason": "alarm MERAH"}):
        t = FakeTrader(MIDS, positions={"A": 5.0}, equity=200.0)
        r = run(live_cfg, t, {"A": -0.25, "B": 0.25}, owned={"A"}, **kw)
        assert "A" not in t.pos and "B" not in t.pos       # flip -> hanya ditutup, B tidak dibuka
        assert all(o["reduce_only"] for o in t.orders) and r["skipped"]


def test_yellow_scale_halves_live_size(live_cfg):
    t = FakeTrader(MIDS, equity=200.0)
    run(live_cfg, t, {"A": 0.5}, scale=0.5)
    assert t.pos["A"] * MIDS["A"] == pytest.approx(50.0)


def test_untradable_coin_not_opened(live_cfg):
    t = FakeTrader(MIDS, equity=200.0)
    r = run(live_cfg, t, {"A": 0.25, "B": 0.25}, untradable=frozenset({"B"}))
    assert "B" not in t.pos and r["skipped"]


def test_journal_called_before_opening(live_cfg):
    t = FakeTrader(MIDS, equity=200.0)
    seen = []
    run(live_cfg, t, {"A": 0.25}, journal=lambda c: seen.append((c, len(t.orders))))
    assert seen == [("A", 0)]


def test_verify_agent(live_cfg):
    with pytest.raises(live.Halt):
        run(live_cfg, FakeTrader(MIDS, agent="0x" + "d" * 40), {"A": 0.1})
    with pytest.raises(live.Halt):
        run(live_cfg, FakeTrader(MIDS, agents=[]), {"A": 0.1})
    with pytest.raises(live.Halt):
        live.make_trader(live_cfg.__class__(), "0x" + "1" * 64)


def test_rerun_same_day_converges(live_cfg):
    t = FakeTrader(MIDS, equity=200.0)
    run(live_cfg, t, {"A": 0.25, "B": -0.25})
    n = len(t.orders)
    run(live_cfg, t, {"A": 0.25, "B": -0.25}, owned={"A", "B"})
    assert len(t.orders) == n                              # sudah sesuai target: tidak ada order baru


def test_round_px_tick_rules():
    assert live.round_px(123456.7, 0) == 123460.0
    assert live.round_px(0.000123456, 0) == 0.000123
