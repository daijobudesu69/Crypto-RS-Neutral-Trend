"""Muat config.yaml menjadi dataclass yang divalidasi.

Kunci yang tidak dikenal DITOLAK: salah ketik (mis. `rs_ot: 8`) tidak boleh diam-diam
diabaikan sementara bot jalan dengan nilai default.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, "config.yaml")
PEGGED = ("USDC", "USDT", "USDE", "USDH", "FDUSD", "DAI", "PYUSD", "USD1", "PAXG", "XAUT", "USTC")


@dataclass(frozen=True)
class Universe:
    exclude: tuple = PEGGED
    fetch_days: int = 450


@dataclass(frozen=True)
class Strategy:
    vol_span: int = 30
    min_hist: int = 200
    liq_win: int = 30
    rs_top: int = 20
    rs_lookbacks: tuple = (7, 14, 28, 56)
    rs_in: int = 4
    rs_out: int = 8
    tr_top: int = 5
    tr_channels: tuple = (20, 55, 100)
    tr_coin_vol: float = 0.40
    sleeve_vol: float = 0.20
    vt_lookback: int = 60
    vt_cap: float = 2.0
    gross_cap: float = 2.5
    age_mode: str = "real"
    pct_scope: str = "traded"
    regime_symbol: str = "BTC"
    regime_lookback: int = 90
    run_after_minutes: int = 2


@dataclass(frozen=True)
class Rules:
    min_order_usdc: float = 10.0
    band: float = 0.40


@dataclass(frozen=True)
class Costs:
    taker_fee: float = 0.00045
    paper_slippage: float = 0.00025


@dataclass(frozen=True)
class Alarms:
    yellow_dd_pct: float = 20
    red_dd_pct: float = 25
    cusum_k_annual: float = 0.314
    cusum_h: float = 0.45
    yellow_scale: float = 0.5
    tracking_max_pct: float = 3


@dataclass(frozen=True)
class Hype:
    info_url: str = "https://api.hyperliquid.xyz/info"
    weight_per_minute: int = 1000


@dataclass(frozen=True)
class Execution:
    master_address: str = ""
    account_address: str = ""
    agent_address: str = ""
    agent_secret: str = "HYPE_RNT_AGENT_KEY_66_CHAR"
    agent_valid_until: str = ""
    margin_mode: str = "cross"
    leverage: int = 3
    ioc_slippage: float = 0.01
    max_live_attempts_per_day: int = 6
    blocked_agents: tuple = ()


@dataclass(frozen=True)
class Config:
    capital_usdc: float = 200.0
    forward_start: str = ""
    universe: Universe = field(default_factory=Universe)
    strategy: Strategy = field(default_factory=Strategy)
    rules: Rules = field(default_factory=Rules)
    costs: Costs = field(default_factory=Costs)
    alarms: Alarms = field(default_factory=Alarms)
    hype: Hype = field(default_factory=Hype)
    execution: Execution = field(default_factory=Execution)


_SECTIONS = {"universe": Universe, "strategy": Strategy, "rules": Rules, "costs": Costs, "alarms": Alarms,
             "hype": Hype, "execution": Execution}


def _build(cls, data: dict, where: str):
    data = data or {}
    if not isinstance(data, dict):
        raise ValueError(f"{where}: harus berupa pasangan kunci: nilai")
    known = {f.name for f in fields(cls)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ValueError(f"{where}: kunci tidak dikenal {unknown} (pilih dari {sorted(known)})")
    kw = {}
    for k, v in data.items():
        default = getattr(cls(), k)
        if isinstance(default, tuple) and isinstance(v, list):
            v = tuple(v)
        elif isinstance(default, bool):
            v = bool(v)
        elif isinstance(default, int) and not isinstance(default, bool):
            v = int(v)
        elif isinstance(default, float):
            v = float(v)
        elif isinstance(default, str):
            v = "" if v is None else str(v)
        kw[k] = v
    return cls(**kw)


def from_dict(doc: dict) -> Config:
    doc = dict(doc or {})
    top = {name: _build(cls, doc.pop(name, None), name) for name, cls in _SECTIONS.items()}
    if "capital_usdc" in doc:
        top["capital_usdc"] = float(doc.pop("capital_usdc"))
    if "forward_start" in doc:
        top["forward_start"] = str(doc.pop("forward_start") or "")
    if doc:
        raise ValueError(f"config: kunci tidak dikenal {sorted(doc)}")
    cfg = Config(**top)
    validate(cfg)
    return cfg


def load(path: str | None = None) -> Config:
    path = path or os.environ.get("RNT_CONFIG") or DEFAULT_PATH
    with open(path, encoding="utf-8") as fh:
        return from_dict(yaml.safe_load(fh) or {})


def validate(cfg: Config) -> None:
    s, r, a, ex = cfg.strategy, cfg.rules, cfg.alarms, cfg.execution
    if s.rs_out < s.rs_in:
        raise ValueError("strategy.rs_out harus >= rs_in")
    if s.age_mode not in ("real", "candles"):
        raise ValueError("strategy.age_mode: real atau candles")
    if s.pct_scope not in ("traded", "all", "universe"):
        raise ValueError("strategy.pct_scope: traded, all, atau universe")
    need = s.min_hist + s.vt_lookback + max(s.rs_lookbacks) + 20
    if cfg.universe.fetch_days < need:
        raise ValueError(f"universe.fetch_days harus >= {need} (umur + penskalaan vol + lookback)")
    if not 0 <= r.band < 5 or r.min_order_usdc <= 0:
        raise ValueError("rules.band / min_order_usdc tidak masuk akal")
    if not 0 < a.yellow_dd_pct < a.red_dd_pct:
        raise ValueError("alarms: 0 < yellow_dd_pct < red_dd_pct")
    if not 0 < a.yellow_scale <= 1:
        raise ValueError("alarms.yellow_scale harus di (0, 1]")
    if ex.margin_mode != "cross":
        raise ValueError("execution.margin_mode harus cross (buku long + short dalam satu akun)")
    if not 1 <= ex.leverage <= 5:
        raise ValueError("execution.leverage di luar 1-5")
    if s.gross_cap > ex.leverage:
        raise ValueError("strategy.gross_cap > execution.leverage: margin tidak cukup saat gross maksimum")
    if cfg.capital_usdc <= 0:
        raise ValueError("capital_usdc harus > 0")


def path_in_repo(rel: str) -> str:
    return rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
