"""Strategi RNT v1.1, murni (tanpa jaringan, tanpa state). research/SPEC_v1.1.md.

Port langsung dari research/code/rnt.py + strat.py + lab.py dengan
age_mode="real" dan pct_scope="traded". Kesamaannya dengan kode riset dijaga
oleh tests/test_strategy_parity.py (panel sintetis) dan tools/parity_check.py
(data lake: OOS v1.1 harus tetap 440,5 USD).

Input: candle 1d per koin (termasuk ±999 candle pra-listing yang dikirim API
HYPE dengan volume 0; candle itu ikut sebagai harga tetapi TIDAK dihitung
sebagai umur). Keputusan untuk hari eksekusi E memakai candle sampai E-1
(close 00:00 UTC hari E), lalu order dikirim tepat setelah close itu.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Loader riset membuang koin yang FILE-nya < 30 candle (memakai panjang total, termasuk masa
# depan). Bot tidak bisa tahu itu, jadi semua koin ikut. Bedanya hanya koin yang delist
# sebelum punya 30 candle; tools/parity_check.py membuktikan bobot tetap identik.
MIN_CANDLES = 1


# --------------------------------------------------------------------------- #
#  Panel
# --------------------------------------------------------------------------- #
def quote_volume(df: pd.DataFrame) -> pd.Series:
    """Sama dengan data lake: volume x rata-rata OHLC."""
    return df["volume"] * (df["open"] + df["high"] + df["low"] + df["close"]) / 4


def build_panel(candles: dict, last_day: pd.Timestamp) -> dict:
    """{coin: DataFrame ts/open/high/low/close/volume} -> {"close", "qv"} (index = tanggal open candle, naive UTC).

    Hanya candle dengan tanggal <= last_day (candle terakhir yang sudah close)."""
    close, qv = {}, {}
    last_day = pd.Timestamp(last_day).normalize()
    for coin, df in candles.items():
        if df is None or len(df) == 0:
            continue
        idx = pd.DatetimeIndex(pd.to_datetime(df["ts"], utc=True)).tz_localize(None).normalize()
        d = df.set_axis(idx)
        d = d[~d.index.duplicated(keep="last")].sort_index()
        d = d[d.index <= last_day]
        if len(d) < MIN_CANDLES:
            continue
        close[coin] = d["close"].astype(float)
        qv[coin] = quote_volume(d).astype(float)
    C = pd.DataFrame(close).sort_index()
    if C.empty:
        return {"close": C, "qv": C.copy()}
    full = pd.date_range(C.index.min(), last_day, freq="D")
    C = C.reindex(full)
    Q = pd.DataFrame(qv).reindex(index=full, columns=C.columns)
    return {"close": C, "qv": Q}


# --------------------------------------------------------------------------- #
#  Blok sinyal (rumus = research/code/lab.py + strat.py)
# --------------------------------------------------------------------------- #
def ewm_vol(C: pd.DataFrame, span: int) -> pd.DataFrame:
    r = C.pct_change(fill_method=None)
    return r.ewm(span=span, min_periods=span // 2).std() * np.sqrt(365)


def universe_mask(C: pd.DataFrame, Q: pd.DataFrame, top: int, min_hist: int, liq_win: int,
                  age_mode: str = "real") -> pd.DataFrame:
    """Eligible di close hari t: umur >= min_hist dan masuk top-N rata-rata quote volume."""
    if age_mode == "candles":
        hist = C.notna().cumsum()
    else:
        hist = ((Q > 0) & C.notna()).cumsum()
    liq = Q.rolling(liq_win, min_periods=liq_win // 2).mean()
    liq = liq.where(hist >= min_hist)
    rank = liq.rank(axis=1, ascending=False)
    return (rank <= top) & C.notna()


def ra_score(C: pd.DataFrame, vol: pd.DataFrame, lookbacks, scope: pd.DataFrame | None) -> pd.DataFrame:
    sc = 0
    for L in lookbacks:
        m = (C / C.shift(L) - 1) / (vol * np.sqrt(L / 365))
        if scope is not None:
            m = m.where(scope)
        sc = sc + m.rank(axis=1, pct=True)
    return sc / len(lookbacks)


def _hyst(rk: np.ndarray, n_in: int, n_out: int, valid: np.ndarray) -> np.ndarray:
    """Masuk kalau peringkat <= n_in, tahan selama <= n_out. Sama dengan strat._hyst (numba)."""
    T, N = rk.shape
    out = np.zeros((T, N))
    prev = np.zeros(N)
    for t in range(T):
        row = rk[t]
        ok = valid[t]
        held = prev > 0
        new = np.where(held, row <= n_out, row <= n_in) & ok
        out[t] = new.astype(float)
        prev = out[t]
    return out


def hyst_book(score: pd.DataFrame, U: pd.DataFrame, n_in: int, n_out: int, gross: float = 1.0):
    s = score.where(U)
    valid = s.notna().values
    rl = s.rank(axis=1, ascending=False).fillna(9999).values
    rs = s.rank(axis=1, ascending=True).fillna(9999).values
    L = pd.DataFrame(_hyst(rl, n_in, n_out, valid), index=s.index, columns=s.columns)
    S = pd.DataFrame(_hyst(rs, n_in, n_out, valid), index=s.index, columns=s.columns)
    wl = L.div(L.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * gross / 2
    ws = S.div(S.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * gross / 2
    return wl, ws


def donch_pos(C: pd.DataFrame, ns) -> pd.DataFrame:
    out = 0
    for n in ns:
        hi = C.rolling(n, min_periods=n).max()
        lo = C.rolling(n, min_periods=n).min()
        out = out + ((C - lo) / (hi - lo) * 2 - 1)
    return out / len(ns)


def book_vol_scale(W: pd.DataFrame, r: pd.DataFrame, tv: float, lb: int, cap: float):
    pr = (W.shift(1) * r).sum(axis=1)
    rv = pr.rolling(lb, min_periods=20).std() * np.sqrt(365)
    k = (tv / rv).clip(upper=cap).fillna(0)
    return W.mul(k, axis=0), k


# --------------------------------------------------------------------------- #
#  Bobot
# --------------------------------------------------------------------------- #
@dataclass
class Weights:
    W: pd.DataFrame            # RNT v1.1 (dipakai paper utama + live)
    W_rs: pd.DataFrame         # mesin 1 (sudah diskala)
    W_tr: pd.DataFrame         # mesin 2 (sudah diskala)
    W_rf: pd.DataFrame         # bayangan: mesin 1 off saat BTC 90 hari turun (paper saja)
    score: pd.DataFrame
    U_rs: pd.DataFrame
    U_tr: pd.DataFrame
    k_rs: pd.Series
    k_tr: pd.Series
    btc_up: pd.Series


def compute(P: dict, s) -> Weights:
    """s = config.Strategy (atau objek dengan atribut yang sama)."""
    C, Q = P["close"], P["qv"]
    r = C.pct_change(fill_method=None)
    vol = ewm_vol(C, s.vol_span)
    U_rs = universe_mask(C, Q, s.rs_top, s.min_hist, s.liq_win, s.age_mode)
    U_tr = universe_mask(C, Q, s.tr_top, s.min_hist, s.liq_win, s.age_mode)
    scope = {"all": None, "traded": (Q > 0) & C.notna(), "universe": U_rs}[s.pct_scope]
    score = ra_score(C, vol, s.rs_lookbacks, scope)
    wl, ws = hyst_book(score, U_rs, s.rs_in, s.rs_out)
    W_rs, k_rs = book_vol_scale(wl - ws, r, s.sleeve_vol, s.vt_lookback, s.vt_cap)

    dp = donch_pos(C, s.tr_channels)
    W_tr_raw = (dp.clip(lower=0) * (s.tr_coin_vol / vol)).where(U_tr, 0).fillna(0).clip(upper=1.5) / s.tr_top
    W_tr, k_tr = book_vol_scale(W_tr_raw, r, s.sleeve_vol, s.vt_lookback, s.vt_cap)

    def cap(W):
        W = W.fillna(0)
        g = W.abs().sum(axis=1)
        return W.mul((s.gross_cap / g).clip(upper=1.0).fillna(1.0), axis=0)

    W = cap(W_rs.add(W_tr, fill_value=0))
    if s.regime_symbol in C.columns:
        btc = C[s.regime_symbol]
        up = (btc / btc.shift(s.regime_lookback) - 1 > 0).astype(float)
    else:
        up = pd.Series(1.0, index=C.index)
    W_rf = cap(W_rs.mul(up, axis=0).add(W_tr, fill_value=0))
    return Weights(W=W, W_rs=W_rs, W_tr=W_tr, W_rf=W_rf, score=score, U_rs=U_rs, U_tr=U_tr,
                   k_rs=k_rs, k_tr=k_tr, btc_up=up)


# --------------------------------------------------------------------------- #
#  View: keputusan satu hari (disimpan di state/view.json)
# --------------------------------------------------------------------------- #
@dataclass
class View:
    exec_day: str                      # hari UTC order dieksekusi (E)
    last_close_day: str                # candle terakhir yang dipakai (E-1)
    targets: dict                      # {coin: bobot} RNT v1.1 (bukan nol)
    targets_rf: dict                   # {coin: bobot} bayangan filter rezim
    w_rs: dict = field(default_factory=dict)
    w_tr: dict = field(default_factory=dict)
    rs_rank: dict = field(default_factory=dict)      # peringkat skor di universe RS (1 = terkuat)
    rs_universe: list = field(default_factory=list)
    tr_universe: list = field(default_factory=list)
    k_rs: float = 0.0
    k_tr: float = 0.0
    btc_close: float | None = None
    btc_up90: bool | None = None
    n_coins: int = 0
    n_traded: int = 0

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: dict) -> "View":
        return cls(**d)

    @property
    def gross(self) -> float:
        return float(sum(abs(v) for v in self.targets.values()))

    @property
    def net(self) -> float:
        return float(sum(self.targets.values()))


def _nz(row: pd.Series, eps: float = 1e-12) -> dict:
    return {str(k): float(v) for k, v in row.items() if pd.notna(v) and abs(v) > eps}


def make_view(candles: dict, exec_day: pd.Timestamp, s) -> View:
    last = pd.Timestamp(exec_day).normalize() - pd.Timedelta(days=1)
    P = build_panel(candles, last)
    if P["close"].empty or P["close"].index[-1] != last:
        raise ValueError(f"tidak ada candle untuk {last.date()}")
    w = compute(P, s)
    t = P["close"].index[-1]
    sc = w.score.loc[t].where(w.U_rs.loc[t]).dropna()
    rk = sc.rank(ascending=False).astype(int).sort_values()
    C, Q = P["close"], P["qv"]
    btc = C[s.regime_symbol].loc[t] if s.regime_symbol in C.columns else None
    return View(exec_day=str(pd.Timestamp(exec_day).date()), last_close_day=str(t.date()),
                targets=_nz(w.W.loc[t]), targets_rf=_nz(w.W_rf.loc[t]),
                w_rs=_nz(w.W_rs.loc[t]), w_tr=_nz(w.W_tr.loc[t]),
                rs_rank={str(k): int(v) for k, v in rk.items()},
                rs_universe=sorted(map(str, w.U_rs.columns[w.U_rs.loc[t].values])),
                tr_universe=sorted(map(str, w.U_tr.columns[w.U_tr.loc[t].values])),
                k_rs=float(w.k_rs.loc[t]), k_tr=float(w.k_tr.loc[t]),
                btc_close=None if btc is None or pd.isna(btc) else float(btc),
                btc_up90=bool(w.btc_up.loc[t] > 0),
                n_coins=int(C.loc[t].notna().sum()), n_traded=int(((Q.loc[t] > 0) & C.loc[t].notna()).sum()))
