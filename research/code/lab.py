"""Research library for Crypto-RS-Neutral & Trend.

Daily panels (index = UTC date of the candle open, columns = coin base name), funding as a COST only,
a weights-based backtest engine and performance metrics.

Timing convention: a signal computed from the candle of day t (closes at 00:00 UTC of t+1) sets the
target weight W[t]. That weight earns the return of day t+1 (close t -> close t+1) and pays the funding
settled during day t+1. Trading cost is charged on |W[t] - W[t-1]| at the close of t.
"""
import os, glob
import numpy as np, pandas as pd

LAKE = r"C:\Crypto data\backtest data and more\data"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RES = os.path.join(ROOT, "results")
CH = os.path.join(ROOT, "charts")
CACHE = os.path.join(RES, "cache")
os.makedirs(CACHE, exist_ok=True)

BN2HL = {"1000PEPE": "kPEPE", "1000SHIB": "kSHIB", "1000BONK": "kBONK", "1000FLOKI": "kFLOKI"}
IS_START, IS_END = pd.Timestamp("2020-01-01"), pd.Timestamp("2024-12-31")
OOS_START, OOS_END = pd.Timestamp("2025-01-01"), pd.Timestamp("2026-09-30")


def _base(sym):
    b = sym[:-4] if sym.endswith("USDT") else sym
    return BN2HL.get(b, b)


def _daily_funding(path, dates):
    """sum of funding settled in (d 00:00, d+1 00:00] -> paid by a position held over day d."""
    if not os.path.exists(path):
        return pd.Series(0.0, index=dates)
    f = pd.read_parquet(path)[["ts", "funding_rate"]].dropna()
    t = pd.to_datetime(f["ts"], utc=True).dt.tz_localize(None)
    day = (t - pd.Timedelta("1ns")).dt.floor("D")  # settlement exactly at 00:00 belongs to previous day
    s = f["funding_rate"].groupby(day.values).sum()
    return s.reindex(dates).fillna(0.0)


def load_panel(venue="binance", tf="1d", refresh=False):
    """dict of DataFrames: open high low close qv fund (+ trades for hl)."""
    cp = os.path.join(CACHE, f"panel_{venue}_{tf}.pkl")
    if os.path.exists(cp) and not refresh:
        return pd.read_pickle(cp)
    if venue == "binance":
        files = glob.glob(os.path.join(LAKE, "binance", "um", "klines", tf, "*.parquet"))
    else:
        files = glob.glob(os.path.join(LAKE, "hyperliquid", "candles", tf, "*.parquet"))
    cols = {c: {} for c in ["open", "high", "low", "close", "qv"]}
    full = {"1d": 1440, "4h": 240, "1h": 60}[tf]
    for f in files:
        k = pd.read_parquet(f)
        if "n_bars" in k:
            k = k[k["n_bars"] >= 0.8 * full]
        if len(k) < 30:
            continue
        name = os.path.basename(f)[:-8]
        coin = _base(name) if venue == "binance" else name
        idx = pd.to_datetime(k["ts"], utc=True).dt.tz_localize(None)
        for c, src in [("open", "open"), ("high", "high"), ("low", "low"), ("close", "close"), ("qv", "quote_volume")]:
            cols[c][coin] = pd.Series(k[src].values.astype(float), index=idx.values)
    P = {c: pd.DataFrame(v).sort_index() for c, v in cols.items()}
    dates = P["close"].index
    fund = {}
    for coin in P["close"].columns:
        if venue == "binance":
            rev = {v: k for k, v in BN2HL.items()}
            fp = os.path.join(LAKE, "binance", "um", "funding", f"{rev.get(coin, coin)}USDT.parquet")
        else:
            fp = os.path.join(LAKE, "hyperliquid", "funding", f"{coin}.parquet")
        fund[coin] = _daily_funding(fp, dates) if tf == "1d" else pd.Series(0.0, index=dates)
    P["fund"] = pd.DataFrame(fund).reindex(index=dates, columns=P["close"].columns).fillna(0.0)
    # a coin's daily funding only counts where it has a price
    P["fund"] = P["fund"].where(P["close"].notna(), 0.0)
    pd.to_pickle(P, cp)
    return P


# ------------------------------------------------------------------ engine
def backtest(W, P, cost=0.0007, fund=True, start=None, end=None, lag=1):
    """W = target weights decided at close of day t (DataFrame dates x coins, fraction of equity).
    lag=1: earns return of t+1 (normal). lag=2: one extra day of execution delay (stress).
    Returns daily DataFrame with gross, cost, funding and net returns."""
    C = P["close"]
    W = W.reindex(index=C.index, columns=C.columns).fillna(0.0)
    r = C.pct_change(fill_method=None).fillna(0.0)
    Wh = W.shift(lag).fillna(0.0)                     # weight held during day t
    gross = (Wh * r).sum(axis=1)
    fpay = (Wh * P["fund"]).sum(axis=1) if fund else gross * 0
    turn = (W - W.shift(1).fillna(0.0)).abs().sum(axis=1).shift(lag - 1).fillna(0.0)
    tcost = turn * cost
    net = gross - fpay - tcost
    out = pd.DataFrame({"gross": gross, "fund": -fpay, "cost": -tcost, "net": net, "turn": turn,
                        "gross_exp": Wh.abs().sum(axis=1), "net_exp": Wh.sum(axis=1),
                        "n_pos": (Wh.abs() > 1e-9).sum(axis=1)})
    if start is not None:
        out = out[out.index >= pd.Timestamp(start)]
    if end is not None:
        out = out[out.index <= pd.Timestamp(end)]
    return out


def metrics(ret, name=""):
    """ret = daily net return series."""
    ret = ret.dropna()
    if len(ret) < 20:
        return {}
    eq = (1 + ret).cumprod()
    yrs = len(ret) / 365.0
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    vol = ret.std() * np.sqrt(365)
    sharpe = ret.mean() / ret.std() * np.sqrt(365) if ret.std() > 0 else np.nan
    dn = ret[ret < 0]
    sortino = ret.mean() / np.sqrt((np.minimum(ret, 0) ** 2).mean()) * np.sqrt(365) if len(dn) else np.nan
    dd = eq / eq.cummax() - 1
    mdd = dd.min()
    # average drawdown = mean of the trough of each distinct drawdown episode (>1%)
    ep, cur = [], 0.0
    for v in dd.values:
        if v < 0:
            cur = min(cur, v)
        elif cur < 0:
            ep.append(cur); cur = 0.0
    if cur < 0:
        ep.append(cur)
    ep = [e for e in ep if e < -0.01]
    m = (1 + ret).groupby(ret.index.to_period("M")).prod() - 1
    return {"name": name, "days": len(ret), "total": eq.iloc[-1] - 1, "cagr": cagr, "vol": vol, "sharpe": sharpe,
            "sortino": sortino, "mdd": mdd, "avg_dd": np.mean(ep) if ep else 0.0, "n_dd": len(ep),
            "calmar": cagr / abs(mdd) if mdd < 0 else np.nan, "pos_months": (m > 0).mean(),
            "worst_m": m.min(), "best_m": m.max(), "avg_dd_daily": dd.mean()}


def yearly(ret):
    return (1 + ret).groupby(ret.index.year).prod() - 1


def tstat_daily(ret):
    ret = ret.dropna()
    return ret.mean() / ret.std() * np.sqrt(len(ret))


def fmt(d):
    if not d:
        return ""
    return (f"{d['name']:<34} tot {d['total']*100:8.1f}%  cagr {d['cagr']*100:6.1f}%  vol {d['vol']*100:5.1f}%  "
            f"SR {d['sharpe']:5.2f}  So {d['sortino']:5.2f}  mdd {d['mdd']*100:6.1f}%  calmar {d['calmar']:5.2f}")


# ------------------------------------------------------------------ helpers
def universe_mask(P, top=30, min_hist=200, liq_win=30, age_mode="candles"):
    """eligible at close of day t: listed >= min_hist days and in top-N by trailing quote volume.
    age_mode "candles": every daily candle counts; "real": only days the coin actually traded (volume > 0)."""
    C = P["close"]
    hist = C.notna().cumsum() if age_mode == "candles" else ((P["qv"] > 0) & C.notna()).cumsum()
    liq = P["qv"].rolling(liq_win, min_periods=liq_win // 2).mean()
    liq = liq.where(hist >= min_hist)
    rank = liq.rank(axis=1, ascending=False)
    return (rank <= top) & C.notna()


def ewm_vol(P, span=30):
    r = P["close"].pct_change(fill_method=None)
    return r.ewm(span=span, min_periods=span // 2).std() * np.sqrt(365)


# ------------------------------------------------------------------ survivorship-extended panels
EXT = os.path.join(ROOT, "data")
PEGGED = {"USDC", "USDT", "USDE", "USDH", "FDUSD", "DAI", "PYUSD", "USD1", "PAXG", "XAUT", "USTC"}


def load_panel_ext(venue="hl", refresh=False):
    """alive panel + coins that are delisted today (HYPE: data/hl_delisted, Binance: data/bn_dead)."""
    cp = os.path.join(CACHE, f"panel_{venue}_1d_ext.pkl")
    if os.path.exists(cp) and not refresh:
        return pd.read_pickle(cp)
    P = load_panel("binance" if venue == "binance" else "hl", "1d")
    sub = "hl_delisted" if venue == "hl" else "bn_dead"
    files = glob.glob(os.path.join(EXT, sub, "1d", "*.parquet"))
    add = {c: {} for c in ["open", "high", "low", "close", "qv"]}
    for f in files:
        k = pd.read_parquet(f)
        name = os.path.basename(f)[:-8]
        coin = _base(name) if venue == "binance" else name
        if coin in P["close"].columns or len(k) < 30:
            continue
        idx = pd.to_datetime(k["ts"], utc=True).dt.tz_localize(None)
        if venue == "binance":   # drop the partial last bar of a delisted contract
            k = k.iloc[:-1]; idx = idx.iloc[:-1]
        for c, src in [("open", "open"), ("high", "high"), ("low", "low"), ("close", "close"), ("qv", "quote_volume")]:
            add[c][coin] = pd.Series(k[src].values.astype(float), index=idx.values)
    out = {}
    for c in ["open", "high", "low", "close", "qv"]:
        out[c] = pd.concat([P[c], pd.DataFrame(add[c])], axis=1).sort_index()
    dates = out["close"].index
    fund = P["fund"].reindex(index=dates).copy()
    for coin in add["close"]:
        fp = os.path.join(EXT, sub, "funding", f"{coin}.parquet")
        fund[coin] = _daily_funding(fp, dates) if os.path.exists(fp) else 0.0
    out["fund"] = fund.reindex(columns=out["close"].columns).fillna(0.0).where(out["close"].notna(), 0.0)
    drop = [c for c in out["close"].columns if c in PEGGED]
    out = {k: v.drop(columns=drop) for k, v in out.items()}
    pd.to_pickle(out, cp)
    return out
