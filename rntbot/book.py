"""Buku paper: posisi perp long DAN short, disimpan sebagai dict JSON.

Akuntansi: kas bergerak saat trade (kas -= qty x harga + fee), jadi
ekuitas = kas + sum(qty x harga). Ini setara dengan akuntansi perp (PnL masuk
ke kas) dan dengan research/code/account.py.
Harga fill paper = mid x (1 +- slippage); fee = |notional| x taker fee.
Funding (biaya saja): long membayar saat rate > 0, short menerima.
"""
from __future__ import annotations

from . import plan as pl


def new_book(capital: float) -> dict:
    return {"cash": float(capital), "start_capital": float(capital), "positions": {},
            "fees": 0.0, "funding": 0.0, "peak_equity": float(capital)}


def px_of(book: dict, coin: str, mids: dict) -> float:
    p = book["positions"].get(coin, {})
    return float(mids.get(coin) or p.get("last_px") or 0.0)


def notional(book: dict, mids: dict) -> dict:
    return {c: p["qty"] * px_of(book, c, mids) for c, p in book["positions"].items()}


def equity(book: dict, mids: dict) -> float:
    return book["cash"] + sum(notional(book, mids).values())


def gross(book: dict, mids: dict) -> float:
    return sum(abs(v) for v in notional(book, mids).values())


def net(book: dict, mids: dict) -> float:
    return sum(notional(book, mids).values())


def mark(book: dict, mids: dict) -> None:
    for coin, p in book["positions"].items():
        if mids.get(coin):
            p["last_px"] = float(mids[coin])
    eq = equity(book, mids)
    book["peak_equity"] = max(float(book.get("peak_equity", eq)), eq)


def trade(book: dict, coin: str, dqty: float, mid: float, costs, when: str) -> dict:
    """Ubah posisi sebesar dqty (bertanda). Return fill + PnL bersih posisi yang tertutup."""
    px = mid * (1 + costs.paper_slippage if dqty > 0 else 1 - costs.paper_slippage)
    fee = abs(dqty) * px * costs.taker_fee
    book["cash"] -= dqty * px + fee
    book["fees"] += fee
    p = book["positions"].get(coin)
    closed = None
    if p is None:
        p = book["positions"][coin] = {"qty": 0.0, "cost": 0.0, "entry_time": when, "last_px": mid,
                                       "fees": 0.0, "funding": 0.0, "side": 1 if dqty > 0 else -1}
    old = p["qty"]
    new = old + dqty
    if old != 0 and (new == 0 or (new > 0) != (old > 0)):
        # posisi lama tertutup (penuh atau berbalik): bagi fee/kas secara proporsional
        frac = abs(old) / abs(dqty)
        p["cost"] += -old * px + fee * frac              # menutup qty lama di harga px
        closed = {"coin": coin, "side": p["side"], "entry_time": p["entry_time"], "exit_time": when,
                  "pnl": -p["cost"], "fees": p["fees"] + fee * frac, "funding": p["funding"]}
        if new == 0:
            book["positions"].pop(coin)
        else:
            book["positions"][coin] = {"qty": new, "cost": new * px + fee * (1 - frac), "entry_time": when,
                                       "last_px": mid, "fees": fee * (1 - frac), "funding": 0.0,
                                       "side": 1 if new > 0 else -1}
    else:
        p["qty"] = new
        p["cost"] += dqty * px + fee
        p["fees"] += fee
        p["last_px"] = mid
    return {"coin": coin, "side": "BUY" if dqty > 0 else "SELL", "qty": abs(dqty), "px": px,
            "notional": abs(dqty) * px, "fee": fee, "closed": closed}


def apply_plan(book: dict, steps: list, mids: dict, meta: dict, costs, min_order: float, when: str,
               floor_buffer: float = 1.005) -> list:
    """Eksekusi rencana di buku paper. Ukuran dibulatkan ke szDecimals HYPE seperti live."""
    fills = []
    for s in steps:
        mid = mids.get(s.coin) or (book["positions"].get(s.coin) or {}).get("last_px")
        if not mid:
            continue
        cur_qty = (book["positions"].get(s.coin) or {}).get("qty", 0.0)
        d = int((meta.get(s.coin) or {}).get("szDecimals", 4))
        if s.target == 0:
            dq = -cur_qty
        else:
            tq = pl.order_size(s.target, mid, d, min_order, floor_buffer) * (1 if s.target > 0 else -1)
            dq = tq - cur_qty
        if dq == 0:
            continue
        f = trade(book, s.coin, dq, mid, costs, when)
        f.update(reason=s.reason, kind=s.kind)
        fills.append(f)
    return fills


def charge_funding(book: dict, coin: str, amount: float) -> None:
    """amount > 0 = dibayar."""
    p = book["positions"].get(coin)
    if p is not None:
        p["funding"] = p.get("funding", 0.0) + amount
        p["cost"] = p.get("cost", 0.0) + amount
    book["cash"] -= amount
    book["funding"] += amount


def funding_amount(qty: float, px: float, rates: list) -> float:
    """qty bertanda: long (qty > 0) membayar sum(rate) x notional; short menerima."""
    return qty * px * sum(r for _, r in rates)
