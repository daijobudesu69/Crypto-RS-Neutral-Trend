"""Realistic small-account simulation (e.g. 200 USDC on HYPE).

Each day after the close: target notional = W * equity. Rules:
- |target| < min_order: rounded to +-min_order if |target| >= min_order/2, else 0.
- an existing position on the same side is left alone unless |target - current| > max(min_order, band * |target|).
- every order pays `cost` (fee + slippage) on its notional; positions pay/receive daily funding (cost only).
- an order that would be smaller than min_order is skipped unless it closes the position completely.
Positions are marked to market daily (close to close). Equity can go to zero (no negative balance).
"""
import numpy as np, pandas as pd


def simulate(W, P, equity0=200.0, min_order=10.0, band=0.40, cost=0.0007, start=None, end=None):
    C = P["close"]
    W = W.reindex(index=C.index, columns=C.columns).fillna(0.0)
    if start is not None:
        idx = C.index[(C.index >= pd.Timestamp(start)) & (C.index <= pd.Timestamp(end))]
    else:
        idx = C.index
    cols = list(C.columns)
    px = C.loc[:, cols].values
    fund = P["fund"].reindex(index=C.index, columns=cols).fillna(0.0).values
    w = W.loc[:, cols].values
    pos = np.zeros(len(cols))           # notional (signed) at the last close
    eq = equity0
    rows, orders, trips = [], [], []
    open_info = {}                      # j -> [entry_date, side, cum_pnl]
    loc = {d: i for i, d in enumerate(C.index)}
    for d in idx:
        t = loc[d]
        # 1) mark to market over day t (positions decided at close t-1)
        if t > 0:
            ret = px[t] / px[t - 1] - 1
            ret = np.where(np.isfinite(ret), ret, 0.0)
            pnl_px = pos * ret
            pnl_f = -pos * fund[t]
            pnl = pnl_px + pnl_f
            for j in np.nonzero(pos)[0]:
                if j in open_info:
                    open_info[j][2] += pnl[j]
            eq += pnl.sum()
            pos = pos * (1 + ret)
            day_px, day_f = pnl_px.sum(), pnl_f.sum()
        else:
            day_px = day_f = 0.0
        if eq <= 0:
            rows.append((d, 0.0, day_px, day_f, 0.0, 0, 0.0, 0.0)); pos[:] = 0; break
        # 2) rebalance at close t (coins without a price today cannot trade -> keep / force close if delisted)
        tgt = w[t] * eq
        tgt = np.where(np.isfinite(px[t]), tgt, 0.0)
        small = np.abs(tgt) < min_order
        tgt = np.where(small, np.where(np.abs(tgt) >= min_order / 2, np.sign(tgt) * min_order, 0.0), tgt)
        fee_day, n_ord = 0.0, 0
        for j in range(len(cols)):
            cur, tg = pos[j], tgt[j]
            if not np.isfinite(px[t, j]):
                if cur != 0:  # no price (delisted / missing): close at last known value
                    fee_day += abs(cur) * cost; n_ord += 1
                    orders.append((d, cols[j], -cur))
                    if j in open_info:
                        e = open_info.pop(j); trips.append((e[0], d, cols[j], e[1], e[2] - abs(cur) * cost, e[3]))
                    pos[j] = 0
                continue
            if cur == 0 and tg == 0:
                continue
            same_side = np.sign(cur) == np.sign(tg) and cur != 0
            if same_side and abs(tg - cur) <= max(min_order, band * abs(tg)):
                continue
            delta = tg - cur
            if abs(delta) < min_order and tg != 0:
                continue
            c = abs(delta) * cost
            fee_day += c; n_ord += 1
            orders.append((d, cols[j], delta))
            closing = cur != 0 and (tg == 0 or np.sign(tg) != np.sign(cur))
            opening = tg != 0 and (cur == 0 or np.sign(tg) != np.sign(cur))
            if closing:
                e = open_info.pop(j, None)
                if e is not None:
                    e[2] -= abs(cur) * cost
                    trips.append((e[0], d, cols[j], e[1], e[2], e[3]))
            elif j in open_info:            # resize of an open position
                open_info[j][2] -= c
                open_info[j][3] = max(open_info[j][3], abs(tg))
            if opening:
                open_info[j] = [d, int(np.sign(tg)), -abs(tg) * cost, abs(tg)]
            pos[j] = tg
        eq -= fee_day
        rows.append((d, eq, day_px, day_f, -fee_day, n_ord, np.abs(pos).sum() / eq if eq > 0 else 0, pos.sum() / eq if eq > 0 else 0))
    for j, e in open_info.items():
        trips.append((e[0], None, cols[j], e[1], e[2], e[3]))
    daily = pd.DataFrame(rows, columns=["date", "equity", "pnl_price", "pnl_funding", "fees", "orders", "gross_lev", "net_lev"]).set_index("date")
    trips = pd.DataFrame(trips, columns=["entry", "exit", "coin", "side", "pnl", "notional"])
    orders = pd.DataFrame(orders, columns=["date", "coin", "delta"])
    return daily, trips, orders
