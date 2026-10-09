from rntbot import book as bk
from rntbot import plan


class C0:
    taker_fee, paper_slippage = 0.0, 0.0


def kinds(steps):
    return {s.coin: s.kind for s in steps}


def test_small_targets_round_to_min_or_zero():
    assert plan.round_target(6.0, 10) == 10
    assert plan.round_target(-6.0, 10) == -10
    assert plan.round_target(4.9, 10) == 0
    assert plan.round_target(-23.0, 10) == -23


def test_band_keeps_same_side_positions():
    eq = 200.0
    # target 40 USD, posisi 30: selisih 10 <= max(10, 16) -> tidak disentuh
    assert plan.plan({"A": 0.2}, eq, {"A": 30.0}, {"A"}, 10, 0.40) == []
    # posisi 20: selisih 20 > 16 -> rebalance (increase)
    assert kinds(plan.plan({"A": 0.2}, eq, {"A": 20.0}, {"A"}, 10, 0.40)) == {"A": "increase"}


def test_open_close_flip_and_missing_price():
    st = plan.plan({"A": 0.1, "B": -0.1, "D": 0.1}, 200.0, {"B": 30.0, "C": -15.0, "D": 50.0}, {"A", "B", "C", "D"},
                   10, 0.40)
    assert kinds(st) == {"A": "open", "B": "flip", "C": "close", "D": "reduce"}
    st = plan.plan({}, 200.0, {"X": 25.0}, set(), 10, 0.40)
    assert kinds(st) == {"X": "close"} and "harga" in st[0].reason


def test_yellow_scale_halves_targets():
    st = plan.plan({"A": 0.5}, 200.0, {}, {"A"}, 10, 0.40, scale=0.5)
    assert st[0].target == 50.0


def test_order_size_respects_minimum():
    assert plan.order_size(10, 3.0, 2, 10) * 3.0 >= 10.05
    assert plan.order_size(-50, 2.0, 1, 10) == 25.0


def test_book_long_short_flip_accounting():
    b = bk.new_book(100.0)
    mids = {"A": 10.0}
    bk.trade(b, "A", 2.0, 10.0, C0, "t0")                # long 2 @ 10
    assert bk.equity(b, mids) == 100.0
    mids["A"] = 12.0
    assert bk.equity(b, mids) == 104.0
    f = bk.trade(b, "A", -5.0, 12.0, C0, "t1")           # tutup long (+4) lalu short 3 @ 12
    assert f["closed"]["pnl"] == 4.0 and b["positions"]["A"]["qty"] == -3.0
    mids["A"] = 10.0
    assert bk.equity(b, mids) == 110.0                   # short untung 6
    f = bk.trade(b, "A", 3.0, 10.0, C0, "t2")
    assert f["closed"]["pnl"] == 6.0 and "A" not in b["positions"] and b["cash"] == 110.0


def test_short_receives_positive_funding():
    b = bk.new_book(100.0)
    bk.trade(b, "A", -2.0, 10.0, C0, "t0")
    amt = bk.funding_amount(-2.0, 10.0, [(0, 0.001), (1, 0.001)])
    bk.charge_funding(b, "A", amt)
    assert amt < 0 and bk.equity(b, {"A": 10.0}) > 100.0
