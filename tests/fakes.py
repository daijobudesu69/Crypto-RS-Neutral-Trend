"""Data dan bursa tiruan untuk tes offline."""
from __future__ import annotations

import numpy as np
import pandas as pd


def synthetic_candles(end_day="2026-10-09", n_coins=32, days=520, seed=1, ghosts=6, late=3) -> dict:
    """BTC + n koin random walk dengan drift berbeda, volume berbeda.

    ghosts: koin yang punya candle pra-listing (harga ada, volume 0) seperti API HYPE.
    late:   koin yang baru listing di tengah periode (tanpa candle hantu)."""
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(end_day, tz="UTC")
    out = {}

    def frame(close, vol):
        ts = pd.date_range(end=end, periods=len(close), freq="D")
        o = np.r_[close[0], close[:-1]]
        return pd.DataFrame({"ts": ts, "open": o, "high": np.maximum(o, close) * 1.01,
                             "low": np.minimum(o, close) * 0.99, "close": close, "volume": vol})

    btc = 60_000 * np.exp(np.cumsum(rng.normal(0.0005, 0.03, days)))
    out["BTC"] = frame(btc, np.full(days, 5e4))
    for i in range(n_coins):
        mu = rng.normal(0, 0.003)
        sd = rng.uniform(0.03, 0.08)
        close = 10 * np.exp(np.cumsum(rng.normal(mu, sd, days)))
        vol = rng.uniform(0.5, 2.0, days) * (1e6 / (i + 1)) / close
        name = f"C{i:02d}"
        if i < ghosts:                              # candle hantu: volume 0 sebelum listing nyata
            vol[: rng.integers(250, 400)] = 0.0
        df = frame(close, vol)
        if ghosts <= i < ghosts + late:             # listing baru: candle mulai belakangan
            df = df.iloc[rng.integers(150, 350):].reset_index(drop=True)
        out[name] = df
    return out


def meta_for(candles: dict, delisted=(), only_iso=(), sz=4) -> dict:
    return {c: {"szDecimals": sz, "maxLeverage": 5, "isDelisted": c in delisted, "onlyIsolated": c in only_iso,
                "markPx": float(df["close"].iloc[-1]), "midPx": float(df["close"].iloc[-1]), "dayNtlVlm": 1.0}
            for c, df in candles.items()}


class FakeInfo:
    """Pengganti rntbot.hype.InfoClient."""

    def __init__(self, candles_1d: dict, meta=None, mids=None, funding=0.0, fail=()):
        self.c1d = candles_1d
        self._meta = meta or meta_for(candles_1d)
        self._mids = mids or {c: float(df["close"].iloc[-1]) for c, df in candles_1d.items()}
        self.funding_rate = funding
        self.fail = set(fail)
        self.calls = {"candles": 0, "funding": 0}

    def meta(self):
        return self._meta

    def all_mids(self):
        return dict(self._mids)

    def post(self, body, weight=20, per_items=None, retries=6):
        return []

    def candles(self, coin, interval, start_ms, end_ms=None, include_open=False):
        self.calls["candles"] += 1
        if coin in self.fail:
            raise RuntimeError("net down")
        df = self.c1d.get(coin)
        if df is None:
            return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
        return df[df["ts"] >= pd.Timestamp(start_ms, unit="ms", tz="UTC")].reset_index(drop=True)

    def funding_history(self, coin, start_ms, end_ms=None):
        self.calls["funding"] += 1
        end = end_ms or start_ms
        first = -(-start_ms // 3_600_000) * 3_600_000
        return [(t, self.funding_rate) for t in range(first, end + 1, 3_600_000)]


class FakeTrader:
    """Bursa tiruan: order IOC langsung terisi di mid; reduce-only tidak boleh membesarkan posisi."""

    def __init__(self, mids: dict, positions=None, equity=200.0, agent="0x" + "c" * 40, sz=4,
                 agents=None, fail_coins=()):
        self.agent_address = agent
        self._mids = dict(mids)
        self.pos = {c: float(q) for c, q in (positions or {}).items()}
        self.cash = equity - sum(q * self._mids[c] for c, q in self.pos.items())
        self.sz = sz
        self._agents = agents if agents is not None else [{"address": agent, "validUntil": None}]
        self.fail_coins = set(fail_coins)
        self.orders = []
        self.leverage = {}

    def agents(self):
        return self._agents

    def sz_decimals(self, coin):
        return self.sz

    def max_leverage(self, coin):
        return 5

    def mids(self):
        return dict(self._mids)

    def positions(self):
        return {c: {"szi": q, "entry_px": self._mids[c], "unrealized": 0.0, "cross": True}
                for c, q in self.pos.items() if q}

    def equity(self):
        return self.cash + sum(q * self._mids[c] for c, q in self.pos.items()), "tiruan"

    def equity_parts(self):
        eq, _ = self.equity()
        return {"abstraction": "default", "perp_account_value": eq, "spot_usdc": 0.0, "spot_usdc_hold": 0.0,
                "upnl": 0.0}

    def set_leverage(self, coin, leverage, cross):
        self.leverage[coin] = (leverage, cross)
        return {"ok": True}

    def market(self, coin, is_buy, sz, mid, slippage, reduce_only=False, cloid_hex=None):
        self.orders.append({"coin": coin, "is_buy": is_buy, "sz": sz, "reduce_only": reduce_only, "cloid": cloid_hex})
        if coin in self.fail_coins:
            return {"error": "tiruan: ditolak"}
        cur = self.pos.get(coin, 0.0)
        d = sz if is_buy else -sz
        if reduce_only:
            if cur == 0 or (cur > 0) == (d > 0):
                return {"error": "reduce only would increase"}
            d = max(-abs(cur), min(abs(cur), d)) if cur > 0 else min(abs(cur), max(-abs(cur), d))
        px = self._mids[coin]
        self.pos[coin] = round(cur + d, 10)
        if self.pos[coin] == 0:
            self.pos.pop(coin)
        self.cash -= d * px
        return {"filled": {"totalSz": str(abs(d)), "avgPx": str(px)}}
