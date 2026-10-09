"""Signal building blocks shared by research and the final strategy.
Every input is daily OHLCV (available from HYPE candles). No OI, no funding as a signal."""
import numpy as np, pandas as pd
from numba import njit
import lab


def ra_score(C, vol, Ls, scope=None):
    """risk-adjusted relative strength: mean cross-sectional percentile of (L-day return / (vol*sqrt(L/365))).
    scope (bool DataFrame, optional): only these coins form the cross-section for the percentile."""
    sc = 0
    for L in Ls:
        m = (C / C.shift(L) - 1) / (vol * np.sqrt(L / 365))
        if scope is not None:
            m = m.where(scope)
        sc = sc + m.rank(axis=1, pct=True)
    return sc / len(Ls)


@njit(cache=True)
def _hyst(rk, n_in, n_out, valid):
    T, N = rk.shape
    out = np.zeros((T, N))
    for t in range(T):
        for j in range(N):
            if not valid[t, j]:
                continue
            prev = out[t - 1, j] if t > 0 else 0.0
            x = rk[t, j]
            if prev > 0:
                if x <= n_out:
                    out[t, j] = 1.0
            elif x <= n_in:
                out[t, j] = 1.0
    return out


def hyst_book(score, U, n_in, n_out, gross=1.0):
    """long the n_in best (hold while rank <= n_out), short the n_in worst (same buffer); equal weight per leg."""
    s = score.where(U)
    valid = s.notna().values
    rl = s.rank(axis=1, ascending=False).fillna(9999).values
    rs = s.rank(axis=1, ascending=True).fillna(9999).values
    L = pd.DataFrame(_hyst(rl, n_in, n_out, valid), index=s.index, columns=s.columns)
    S = pd.DataFrame(_hyst(rs, n_in, n_out, valid), index=s.index, columns=s.columns)
    wl = L.div(L.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * gross / 2
    ws = S.div(S.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * gross / 2
    return wl, ws


def donch_pos(C, ns=(20, 55, 100)):
    """average position of close inside its n-day channel, scaled to [-1, 1]."""
    out = 0
    for n in ns:
        hi = C.rolling(n, min_periods=n).max(); lo = C.rolling(n, min_periods=n).min()
        out = out + ((C - lo) / (hi - lo) * 2 - 1)
    return out / len(ns)


def ema_trend(C, pairs=((8, 32), (16, 64), (32, 128))):
    return sum(np.sign(C.ewm(span=f, min_periods=s).mean() - C.ewm(span=s, min_periods=s).mean()) for f, s in pairs) / len(pairs)


def book_vol_scale(W, r, tv, lb=60, cap=2.0):
    """scale a weight book so its trailing realised vol ~ tv (uses only past returns of the current book)."""
    pr = (W.shift(1) * r).sum(axis=1)
    rv = pr.rolling(lb, min_periods=20).std() * np.sqrt(365)
    k = (tv / rv).clip(upper=cap).fillna(0)
    return W.mul(k, axis=0), k
