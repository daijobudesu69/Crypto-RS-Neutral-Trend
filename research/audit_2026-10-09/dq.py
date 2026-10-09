"""Audit DUET 2026-10-09 - implementasi INDEPENDEN dari SPEC_FROZEN.md.

Tidak meng-import kode penulis (lab/strat/duet/account). Semua dihitung ulang dari parquet mentah.
Konvensi waktu: candle harian tanggal d dibuka 00:00 UTC hari d dan ditutup 00:00 UTC hari d+1.
Sinyal dihitung dari close candle d, order dieksekusi setelah close itu, hasilnya dinikmati mulai candle d+1.
"""
import os, glob
import numpy as np, pandas as pd

BASE = os.environ.get("DUET_AUDIT_BASE", "/home/claude/w")  # folder berisi data/ dan "Edge Hypotesis 20261009"/
LAKE = os.path.join(BASE, "data")
EDGE = os.path.join(BASE, "Edge Hypotesis 20261009")
BN2HL = {"1000PEPE": "kPEPE", "1000SHIB": "kSHIB", "1000BONK": "kBONK", "1000FLOKI": "kFLOKI"}
PEGGED = {"USDC", "USDT", "USDE", "USDH", "FDUSD", "DAI", "PYUSD", "USD1", "PAXG", "XAUT", "USTC"}
FIELDS = ["open", "high", "low", "close", "qv"]


def _read(path):
    k = pd.read_parquet(path)
    k["d"] = pd.to_datetime(k["ts"], utc=True).dt.tz_localize(None).astype("datetime64[ns]")
    return k.drop_duplicates("d").sort_values("d")


def _fund_daily(path):
    """jumlah funding per jam yang dibayar selama candle d: cap waktu (d 00:00, d+1 00:00]."""
    f = pd.read_parquet(path)[["ts", "funding_rate"]].dropna()
    t = pd.to_datetime(f["ts"], utc=True).dt.tz_localize(None).astype("datetime64[ns]")
    day = (t - pd.Timedelta(seconds=1)).dt.floor("D")
    return f["funding_rate"].groupby(day.values).sum()


def load_hl(delisted=True, ghost="asis"):
    """ghost='asis' : pakai candle apa adanya (termasuk candle volume 0 sebelum listing)
       ghost='drop' : buang semua candle volume 0 SEBELUM candle pertama yang benar-benar ada transaksinya."""
    srcs = [(f, os.path.join(LAKE, "hyperliquid", "funding")) for f in sorted(glob.glob(os.path.join(LAKE, "hyperliquid", "candles", "1d", "*.parquet")))]
    seen = {os.path.basename(f)[:-8] for f, _ in srcs}
    if delisted:
        for f in sorted(glob.glob(os.path.join(EDGE, "data", "hl_delisted", "1d", "*.parquet"))):
            c = os.path.basename(f)[:-8]
            if c not in seen and c not in PEGGED:
                srcs.append((f, os.path.join(EDGE, "data", "hl_delisted", "funding")))
    cols = {x: {} for x in FIELDS}
    fund, first_real = {}, {}
    for f, fdir in srcs:
        c = os.path.basename(f)[:-8]
        if c in PEGGED:
            continue
        k = _read(f)
        real = k["quote_volume"] > 0
        if not real.any():
            continue
        first_real[c] = k.loc[real, "d"].iloc[0]
        if ghost == "drop":
            k = k[k["d"] >= first_real[c]]
        if len(k) < 30:
            continue
        for x, s in zip(FIELDS, ["open", "high", "low", "close", "quote_volume"]):
            cols[x][c] = pd.Series(k[s].values.astype(float), index=k["d"].values)
        fp = os.path.join(fdir, c + ".parquet")
        if os.path.exists(fp):
            fund[c] = _fund_daily(fp)
    P = {x: pd.DataFrame(v).sort_index() for x, v in cols.items()}
    idx, cc = P["close"].index, P["close"].columns
    F = pd.DataFrame(fund).reindex(index=idx, columns=cc).fillna(0.0)
    P["fund"] = F.where(P["close"].notna(), 0.0)
    P["first_real"] = pd.Series(first_real).reindex(cc)
    return P


def load_bn(dead=False, fund_penalty_dead=0.0):
    files = sorted(glob.glob(os.path.join(LAKE, "binance", "um", "klines", "1d", "*.parquet")))
    cols = {x: {} for x in FIELDS}
    fund, is_dead = {}, {}

    def nm(f):
        b = os.path.basename(f)[:-8]
        b = b[:-4] if b.endswith("USDT") else b
        return BN2HL.get(b, b)
    for f in files:
        k = _read(f)
        if "n_bars" in k:
            k = k[k["n_bars"] >= 0.8 * 1440]
        if len(k) < 30:
            continue
        c = nm(f)
        for x, s in zip(FIELDS, ["open", "high", "low", "close", "quote_volume"]):
            cols[x][c] = pd.Series(k[s].values.astype(float), index=k["d"].values)
        fp = os.path.join(LAKE, "binance", "um", "funding", os.path.basename(f))
        if os.path.exists(fp):
            fund[c] = _fund_daily(fp)
        is_dead[c] = False
    if dead:
        for f in sorted(glob.glob(os.path.join(EDGE, "data", "bn_dead", "1d", "*.parquet"))):
            c = nm(f)
            if c in cols["close"] or c in PEGGED:
                continue
            k = _read(f)
            if len(k) < 30:
                continue
            k = k.iloc[:-1]
            for x, s in zip(FIELDS, ["open", "high", "low", "close", "quote_volume"]):
                cols[x][c] = pd.Series(k[s].values.astype(float), index=k["d"].values)
            is_dead[c] = True
    P = {x: pd.DataFrame(v).sort_index() for x, v in cols.items()}
    idx, cc = P["close"].index, P["close"].columns
    F = pd.DataFrame(fund).reindex(index=idx, columns=cc).fillna(0.0)
    P["fund"] = F.where(P["close"].notna(), 0.0)
    P["is_dead"] = pd.Series(is_dead).reindex(cc)
    return P


SPEC = dict(vol_span=30, min_hist=200, liq_win=30, rs_top=20, rs_L=(7, 14, 28, 56), rs_in=4, rs_out=8,
            tr_top=5, tr_ch=(20, 55, 100), tr_coin_vol=0.40, sleeve_vol=0.20, vt_lb=60, vt_cap=2.0, gross_cap=2.5,
            pct_scope="all", channel="close", hist_mode="candles")


def _hyst(rank, valid, n_in, n_out):
    T, N = rank.shape
    held = np.zeros((T, N), dtype=bool)
    prev = np.zeros(N, dtype=bool)
    for t in range(T):
        now = valid[t] & (((prev) & (rank[t] <= n_out)) | ((~prev) & (rank[t] <= n_in)))
        held[t] = now
        prev = now
    return held


def _volscale(Wraw, R, tv, lb, cap):
    """faktor skala di hari t hanya memakai return buku s/d hari t (bobot kemarin x return hari ini)."""
    book = (Wraw.shift(1) * R).sum(axis=1)
    rv = book.rolling(lb, min_periods=20).std() * np.sqrt(365)
    k = (tv / rv).clip(upper=cap).fillna(0.0)
    return Wraw.mul(k, axis=0), k


def signals(P, spec=None, exclude=()):
    sp = dict(SPEC)
    if spec:
        sp.update(spec)
    keep = [c for c in P["close"].columns if c not in exclude]
    C, QV = P["close"][keep], P["qv"][keep]
    R = C.pct_change(fill_method=None)
    vol = R.ewm(span=sp["vol_span"], min_periods=sp["vol_span"] // 2).std() * np.sqrt(365)
    hist = C.notna().cumsum() if sp["hist_mode"] == "candles" else (QV > 0).cumsum()
    liq = QV.rolling(sp["liq_win"], min_periods=sp["liq_win"] // 2).mean().where(hist >= sp["min_hist"])
    lrank = liq.rank(axis=1, ascending=False)
    U20 = (lrank <= sp["rs_top"]) & C.notna()
    U5 = (lrank <= sp["tr_top"]) & C.notna()
    # --- Mesin 1
    score = 0
    for L in sp["rs_L"]:
        m = (C / C.shift(L) - 1) / (vol * np.sqrt(L / 365))
        if sp["pct_scope"] == "universe":
            m = m.where(U20)
        elif sp["pct_scope"] == "traded":      # hanya koin yang hari itu benar-benar ada transaksinya
            m = m.where(QV > 0)
        elif sp["pct_scope"] == "eligible":    # hanya koin yang sudah lolos syarat umur
            m = m.where(hist >= sp["min_hist"])
        score = score + m.rank(axis=1, pct=True)
    score = (score / len(sp["rs_L"])).where(U20)
    valid = score.notna().values
    rl = score.rank(axis=1, ascending=False).fillna(1e9).values
    rs = score.rank(axis=1, ascending=True).fillna(1e9).values
    Lh = pd.DataFrame(_hyst(rl, valid, sp["rs_in"], sp["rs_out"]), index=C.index, columns=C.columns).astype(float)
    Sh = pd.DataFrame(_hyst(rs, valid, sp["rs_in"], sp["rs_out"]), index=C.index, columns=C.columns).astype(float)
    wl = Lh.div(Lh.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * 0.5
    ws = Sh.div(Sh.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * 0.5
    W1raw = wl - ws
    W1, k1 = _volscale(W1raw, R, sp["sleeve_vol"], sp["vt_lb"], sp["vt_cap"])
    # --- Mesin 2
    dp = 0
    for n in sp["tr_ch"]:
        if sp["channel"] == "close":
            hi, lo = C.rolling(n, min_periods=n).max(), C.rolling(n, min_periods=n).min()
        else:
            hi, lo = P["high"][keep].rolling(n, min_periods=n).max(), P["low"][keep].rolling(n, min_periods=n).min()
        dp = dp + ((C - lo) / (hi - lo) * 2 - 1)
    dp = dp / len(sp["tr_ch"])
    W2raw = (dp.clip(lower=0) * (sp["tr_coin_vol"] / vol)).where(U5, 0).fillna(0).clip(upper=1.5) / sp["tr_top"]
    W2, k2 = _volscale(W2raw, R, sp["sleeve_vol"], sp["vt_lb"], sp["vt_cap"])
    W = W1.add(W2, fill_value=0).fillna(0)
    g = W.abs().sum(axis=1)
    W = W.mul((sp["gross_cap"] / g).clip(upper=1.0).fillna(1.0), axis=0)
    return dict(W=W, W1=W1, W2=W2, W1raw=W1raw, W2raw=W2raw, k1=k1, k2=k2, score=score, U20=U20, U5=U5, vol=vol, Lh=Lh, Sh=Sh)


def account(W, P, start, end, eq0=200.0, min_order=10.0, band=0.40, cost=0.0007, exec_px=None, skip_days=None,
            fund_extra=None, min_rule=True, abs_cost=None):
    """Simulasi akun berbasis JUMLAH KOIN (qty) + kas. Ekuitas = kas + sum(qty x harga close).
    exec_px : DataFrame harga eksekusi (kalau None, eksekusi di harga close hari itu, sama seperti penulis).
    skip_days: set tanggal di mana trader TIDAK menjalankan strategi (posisi dibiarkan apa adanya).
    fund_extra: DataFrame funding tambahan per hari (penalti), dibayar oleh short kalau negatif, dst."""
    C = P["close"]
    cols = list(C.columns)
    W = W.reindex(index=C.index, columns=cols).fillna(0.0)
    px = C.values
    F = P["fund"].reindex(index=C.index, columns=cols).fillna(0.0).values
    if fund_extra is not None:
        F = F + fund_extra.reindex(index=C.index, columns=cols).fillna(0.0).values
    AC = None if abs_cost is None else abs_cost.reindex(index=C.index, columns=cols).fillna(0.0).values
    EX = None if exec_px is None else exec_px.reindex(index=C.index, columns=cols).values
    w = W.values
    days = C.index[(C.index >= pd.Timestamp(start)) & (C.index <= pd.Timestamp(end))]
    pos0 = {d: i for i, d in enumerate(C.index)}
    N = len(cols)
    qty = np.zeros(N)
    last = np.full(N, np.nan)     # harga close terakhir yang diketahui per koin
    cash = eq0
    daily, orders, trips = [], [], []
    opened = {}                   # j -> dict(entry, side, pnl, maxnot)
    skip_days = skip_days or set()
    for d in days:
        t = pos0[d]
        p = px[t]
        pnl_px = pnl_f = 0.0
        held = np.nonzero(qty)[0]
        for j in held:
            newp = p[j] if np.isfinite(p[j]) else last[j]
            dpx = qty[j] * (newp - last[j])
            dfu = -qty[j] * last[j] * F[t, j]
            if AC is not None:
                dfu -= abs(qty[j] * last[j]) * AC[t, j]
            pnl_px += dpx; pnl_f += dfu
            if j in opened:
                opened[j]["pnl"] += dpx + dfu
        cash += pnl_f
        ok = np.isfinite(p)
        last = np.where(ok, p, last)
        eq = cash + float(np.nansum(qty * last))
        if eq <= 0:
            daily.append((d, 0.0, pnl_px, pnl_f, 0.0, 0, 0.0, 0.0)); break
        fee_day, n_ord = 0.0, 0
        for j in range(N):
            cur = qty[j] * last[j] if qty[j] != 0 else 0.0
            if not ok[j]:
                if cur != 0:   # koin tidak punya harga lagi (delisting): ditutup di harga terakhir
                    fee = abs(cur) * cost; fee_day += fee; n_ord += 1
                    orders.append((d, cols[j], -cur, last[j]))
                    cash += qty[j] * last[j]; qty[j] = 0.0
                    e = opened.pop(j, None)
                    if e:
                        trips.append((e["entry"], d, cols[j], e["side"], e["pnl"] - fee, e["maxnot"]))
                continue
            if d in skip_days:
                continue
            tg = w[t, j] * eq
            if abs(tg) < min_order:
                tg = np.sign(tg) * min_order if (min_rule and abs(tg) >= min_order / 2) else (0.0 if min_rule else tg)
            if cur == 0 and tg == 0:
                continue
            same = cur != 0 and np.sign(cur) == np.sign(tg)
            if same and abs(tg - cur) <= max(min_order, band * abs(tg)):
                continue
            delta = tg - cur
            if abs(delta) < min_order and tg != 0:
                continue
            pe = p[j]
            if EX is not None and np.isfinite(EX[t, j]) and EX[t, j] > 0:
                pe = EX[t, j]
            fee = abs(delta) * cost
            fee_day += fee; n_ord += 1
            orders.append((d, cols[j], delta, pe))
            dq_ = delta / pe
            if tg == 0:
                dq_ = -qty[j]            # tutup penuh
            slip = dq_ * (p[j] - pe)     # untung/rugi langsung karena harga eksekusi beda dari close
            cash -= dq_ * pe
            closing = cur != 0 and (tg == 0 or np.sign(tg) != np.sign(cur))
            opening = tg != 0 and (cur == 0 or np.sign(tg) != np.sign(cur))
            if closing:
                e = opened.pop(j, None)
                if e:
                    trips.append((e["entry"], d, cols[j], e["side"], e["pnl"] - abs(cur) * cost + (slip if not opening else 0.0), e["maxnot"]))
            elif j in opened:
                opened[j]["pnl"] += slip - fee
                opened[j]["maxnot"] = max(opened[j]["maxnot"], abs(tg))
            if opening:
                opened[j] = dict(entry=d, side=int(np.sign(tg)), pnl=-abs(tg) * cost + slip, maxnot=abs(tg))
            qty[j] += dq_
            if tg == 0:
                qty[j] = 0.0
        cash -= fee_day
        eq = cash + float(np.nansum(qty * last))
        notional = qty * last
        g = float(np.nansum(np.abs(notional))); n = float(np.nansum(notional))
        daily.append((d, eq, pnl_px, pnl_f, -fee_day, n_ord, g / eq if eq > 0 else 0, n / eq if eq > 0 else 0))
    for j, e in opened.items():
        trips.append((e["entry"], None, cols[j], e["side"], e["pnl"], e["maxnot"]))
    D = pd.DataFrame(daily, columns=["date", "equity", "pnl_price", "pnl_funding", "fees", "orders", "gross_lev", "net_lev"]).set_index("date")
    T = pd.DataFrame(trips, columns=["entry", "exit", "coin", "side", "pnl", "notional"])
    O = pd.DataFrame(orders, columns=["date", "coin", "delta", "px"])
    return D, T, O


def stats(eq, eq0=200.0):
    r = eq.pct_change()
    r.iloc[0] = eq.iloc[0] / eq0 - 1
    n = len(r)
    tot = eq.iloc[-1] / eq0
    dd = eq / np.maximum.accumulate(np.maximum(eq.values, eq0)) - 1 if False else eq / eq.cummax() - 1
    sd = r.std()
    return dict(end=float(eq.iloc[-1]), total=float(tot - 1), cagr=float(tot ** (365.0 / n) - 1), vol=float(sd * np.sqrt(365)),
                sharpe=float(r.mean() / sd * np.sqrt(365)), t=float(r.mean() / sd * np.sqrt(n)), mdd=float(dd.min()),
                sortino=float(r.mean() / np.sqrt((np.minimum(r, 0) ** 2).mean()) * np.sqrt(365)), days=n)


def weights_bt(W, P, start, end, cost=0.0007, lag=1):
    C = P["close"]
    W = W.reindex(index=C.index, columns=C.columns).fillna(0.0)
    R = C.pct_change(fill_method=None).fillna(0.0)
    Wh = W.shift(lag).fillna(0.0)
    turn = (W - W.shift(1).fillna(0.0)).abs().sum(axis=1).shift(lag - 1).fillna(0.0)
    net = (Wh * R).sum(axis=1) - (Wh * P["fund"]).sum(axis=1) - turn * cost
    return net[(net.index >= pd.Timestamp(start)) & (net.index <= pd.Timestamp(end))]


def rstats(r):
    eq = (1 + r).cumprod()
    return dict(total=float(eq.iloc[-1] - 1), cagr=float(eq.iloc[-1] ** (365 / len(r)) - 1), vol=float(r.std() * np.sqrt(365)),
                sharpe=float(r.mean() / r.std() * np.sqrt(365)), t=float(r.mean() / r.std() * np.sqrt(len(r))), mdd=float((eq / eq.cummax() - 1).min()))


S0, S1 = "2025-01-01", "2026-09-30"
