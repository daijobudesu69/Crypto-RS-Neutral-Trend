"""Eksekusi live RNT di subaccount HYPE (long + short, cross margin).

Hanya jalan kalau control/bot.yaml berisi mode live/manage/flatten DAN secret API
wallet tersedia. Yang menyalakan live adalah user sendiri.

Desain (pelajaran dari Crypto-MEX dan Crypto-RMF):
  * Executor tidak pernah memutuskan sendiri. Target bobot berasal dari View yang
    sama dengan buku paper; posisi dibaca dari bursa, jadi menjalankan ulang di hari
    yang sama aman (hasilnya konvergen, tidak dobel order).
  * Aturan order = rntbot/plan.py, sama dengan buku paper dan backtest.
  * Hanya posisi milik RNT (tercatat di state) yang disentuh. Posisi lain di akun =
    ASING: live/manage berhenti (Halt) tanpa order; flatten hanya menutup milik RNT.
  * Menutup / mengurangi / balik arah memakai reduce-only. Balik arah = tutup penuh
    dulu, baru buka arah baru.
  * SDK resmi diimpor malas: eth-account memuat DLL native, dan tes offline tidak
    boleh bergantung padanya.
  * Setiap order membawa cloid berawalan "RNT". Kunci tidak pernah dicetak; error
    dilaporkan dengan tipe saja.
"""
from __future__ import annotations

import datetime as dt
import hashlib

from . import plan as pl

MAINNET = "https://api.hyperliquid.xyz"
BOT_PREFIX = "0x524e54"          # "RNT"
KIND = {"open": "01", "increase": "02", "reduce": "03", "close": "04", "flip_close": "05", "flip_open": "06"}
HTTP_TIMEOUT = 20.0


class Halt(Exception):
    """Jangan sentuh akun sama sekali (kunci salah, agent kedaluwarsa, config kosong, posisi asing)."""


def cloid(kind: str, day: str, coin: str, attempt: int = 0) -> str:
    h = hashlib.sha256(f"{day}|{coin}|{kind}|{attempt}".encode()).hexdigest()
    return BOT_PREFIX + kind + h[:24]


def is_bot_cloid(c) -> bool:
    return isinstance(c, str) and c.lower().startswith(BOT_PREFIX)


def round_px(px: float, sz_decimals: int) -> float:
    """Aturan tick perp HYPE: <= 5 angka signifikan dan <= 6 - szDecimals desimal."""
    return round(float(f"{px:.5g}"), 6 - sz_decimals)


def ioc_px(mid: float, is_buy: bool, sz_decimals: int, slippage: float) -> float:
    return round_px(mid * (1 + slippage if is_buy else 1 - slippage), sz_decimals)


def order_status(resp) -> dict:
    """Status pertama dari respons order HYPE, atau {'error': ...}. HYPE menaruh
    kegagalan per order DI DALAM statuses walau status luar "ok"."""
    if not isinstance(resp, dict) or resp.get("status") != "ok":
        return {"error": f"respons ditolak: {str(resp)[:200]}"}
    st = (((resp.get("response") or {}).get("data") or {}).get("statuses")) or []
    if not st:
        return {"ok": True}
    return st[0] if isinstance(st[0], dict) else {"ok": st[0]}


# --------------------------------------------------------------------------- #
#  Adapter SDK — satu-satunya bagian yang berbicara dengan SDK Hyperliquid
# --------------------------------------------------------------------------- #
class HypeTrader:
    def __init__(self, agent_key: str, master: str, account: str, base_url: str = MAINNET,
                 timeout: float = HTTP_TIMEOUT):
        import eth_account
        from hyperliquid.exchange import Exchange
        from hyperliquid.info import Info

        wallet = eth_account.Account.from_key(agent_key)
        self.agent_address = wallet.address
        self.master, self.account = master, account
        self.info = Info(base_url, skip_ws=True, timeout=timeout)
        # vault_address = subaccount: order ditandatangani API wallet milik akun utama,
        # dieksekusi atas nama subaccount RNT.
        vault = account if account.lower() != master.lower() else None
        self.exchange = Exchange(wallet, base_url, account_address=master, vault_address=vault, timeout=timeout)
        uni = self.info.meta()["universe"]
        self._sz = {u["name"]: int(u["szDecimals"]) for u in uni}
        self._lev = {u["name"]: int(u.get("maxLeverage", 1)) for u in uni}

    def agents(self) -> list:
        return self.info.extra_agents(self.master)

    def sz_decimals(self, coin: str) -> int:
        return self._sz[coin]

    def max_leverage(self, coin: str) -> int:
        return self._lev.get(coin, 1)

    def mids(self) -> dict:
        return {k: float(v) for k, v in self.info.all_mids().items()}

    def positions(self) -> dict:
        out = {}
        for ap in self.info.user_state(self.account).get("assetPositions", []):
            p = ap["position"]
            szi = float(p["szi"])
            if szi:
                out[p["coin"]] = {"szi": szi, "entry_px": float(p["entryPx"]),
                                  "unrealized": float(p.get("unrealizedPnl") or 0),
                                  "cross": p["leverage"]["type"] == "cross"}
        return out

    def abstraction(self) -> str | None:
        try:
            r = self.info.post("/info", {"type": "userAbstraction", "user": self.account})
            return r if isinstance(r, str) else None
        except Exception:  # noqa: BLE001
            return None

    def equity_parts(self) -> dict:
        st = self.info.user_state(self.account)
        usdc = hold = 0.0
        for b in self.info.spot_user_state(self.account).get("balances", []):
            if b["coin"] == "USDC":
                usdc, hold = float(b["total"]), float(b.get("hold") or 0)
        return {"abstraction": self.abstraction(),
                "perp_account_value": float((st.get("marginSummary") or {}).get("accountValue") or 0),
                "spot_usdc": usdc, "spot_usdc_hold": hold,
                "upnl": sum(float(ap["position"].get("unrealizedPnl") or 0) for ap in st.get("assetPositions", []))}

    def equity(self) -> tuple[float, str]:
        return equity_from_parts(self.equity_parts())

    def set_leverage(self, coin: str, leverage: int, cross: bool) -> dict:
        return order_status(self.exchange.update_leverage(leverage, coin, is_cross=cross))

    def market(self, coin: str, is_buy: bool, sz: float, mid: float, slippage: float,
               reduce_only: bool = False, cloid_hex: str | None = None) -> dict:
        from hyperliquid.utils.types import Cloid
        px = ioc_px(mid, is_buy, self.sz_decimals(coin), slippage)
        return order_status(self.exchange.order(
            coin, is_buy, sz, px, {"limit": {"tif": "Ioc"}}, reduce_only=reduce_only,
            cloid=Cloid.from_str(cloid_hex) if cloid_hex else None))


UNIFIED = ("unifiedAccount", "portfolioMargin")


def equity_from_parts(p: dict) -> tuple[float, str]:
    """Ekuitas akun (dari RMF, diverifikasi dengan canary RMF 2026-10-05).

    Mode unified / portfolio margin: ekuitas = saldo USDC spot ("total"), yang SUDAH
    memuat uPnL. Mode biasa: perp accountValue (sudah termasuk uPnL)."""
    mode = p.get("abstraction")
    av = p["perp_account_value"]
    if mode in UNIFIED or (mode is None and av <= 0):
        return p["spot_usdc"], f"spot USDC, sudah termasuk uPnL ({mode or 'mode tidak terbaca'})"
    return av, f"perp accountValue ({mode or 'mode tidak terbaca'})"


def make_trader(cfg, agent_key: str):
    ex = cfg.execution
    if not (ex.master_address and ex.account_address and ex.agent_address):
        raise Halt("execution.master_address / account_address / agent_address di config.yaml belum diisi")
    if ex.account_address.lower() == ex.master_address.lower():
        raise Halt("execution.account_address harus SUBACCOUNT khusus RNT, bukan akun utama (dipakai RMF)")
    return HypeTrader(agent_key, ex.master_address, ex.account_address)


# --------------------------------------------------------------------------- #
#  Logika executor — diuji dengan trader tiruan (tests/test_live.py)
# --------------------------------------------------------------------------- #
def verify_agent(trader, cfg, now: dt.datetime) -> None:
    ex = cfg.execution
    if trader.agent_address.lower() != ex.agent_address.lower():
        raise Halt(f"kunci di secret menghasilkan {trader.agent_address}, bukan agent {ex.agent_address}")
    if ex.agent_valid_until:
        until = dt.date.fromisoformat(ex.agent_valid_until)
        if now.date() > until:
            raise Halt(f"API wallet kedaluwarsa sejak {until} — buat yang baru, ganti secret")
    now_ms = int(now.timestamp() * 1000)
    for a in trader.agents():
        if str(a.get("address", "")).lower() == ex.agent_address.lower():
            vu = a.get("validUntil")
            if vu and int(vu) < now_ms:
                raise Halt("API wallet terdaftar tapi sudah kedaluwarsa di HYPE")
            return
    raise Halt(f"API wallet {ex.agent_address} tidak terdaftar di akun {ex.master_address}")


def _fill(st: dict) -> tuple[float, float]:
    f = st.get("filled") if isinstance(st, dict) else None
    if not f:
        return 0.0, 0.0
    return float(f.get("totalSz", 0) or 0), float(f.get("avgPx", 0) or 0)


def run(targets: dict, exec_day: str, cfg, trader, mode: str, now: dt.datetime, scale: float = 1.0,
        reduce_only_mode: bool = False, attempt: int = 0, owned=frozenset(), untradable=frozenset(),
        journal=None, block_reason: str = "") -> dict:
    """Samakan posisi akun RNT dengan target bobot hari ini.

    mode: live | manage (hanya kurangi/tutup) | flatten (tutup semua milik RNT)
    scale: < 1 saat alarm kuning. reduce_only_mode: True saat alarm merah (seperti manage).
    owned: koin yang dibuka RNT sendiri (dari state). untradable: koin yang tidak boleh
    dibuka (onlyIsolated / tidak ada di meta) — posisi yang ada tetap boleh ditutup.
    journal(coin): dipanggil SEBELUM order pembuka/penambah, supaya koin tercatat milik RNT
    walaupun job mati sebelum state hasil order tersimpan.
    """
    verify_agent(trader, cfg, now)
    ex, rules = cfg.execution, cfg.rules
    res = {"orders": [], "errors": [], "skipped": []}
    pos = trader.positions()
    foreign = sorted(c for c in pos if c not in owned)
    if foreign and mode != "flatten":
        raise Halt(f"akun berisi posisi yang bukan dibuka RNT: {', '.join(foreign)}. Tutup/pindahkan dulu; "
                   "RNT butuh subaccount khusus")
    if foreign:
        res["errors"].append(f"posisi asing tidak disentuh: {', '.join(foreign)}")
    mids = trader.mids()
    eq, how = trader.equity()
    res.update(equity_before=eq, equity_method=how)
    pos = {c: p for c, p in pos.items() if c in owned}
    current = {c: p["szi"] * mids.get(c, p["entry_px"]) for c, p in pos.items()}

    if mode == "flatten":
        steps = [pl.Step(c, v, 0.0, "flatten") for c, v in current.items()]
    else:
        priced = {c for c in mids if c not in untradable or c in current}
        tg = {c: w for c, w in targets.items() if c not in untradable}
        for c in set(targets) - set(tg):
            res["skipped"].append((c, "tidak bisa dibuka di HYPE (onlyIsolated / tidak ada)"))
        steps = pl.plan(tg, eq, current, priced, rules.min_order_usdc, rules.band, scale)
        if mode == "manage" or reduce_only_mode:
            why = block_reason or f"mode {mode}"
            kept = []
            for s in steps:
                if s.kind in ("close", "reduce"):
                    kept.append(s)
                elif s.kind == "flip":
                    kept.append(pl.Step(s.coin, s.current, 0.0, f"{s.reason} (hanya tutup: {why})"))
                else:
                    res["skipped"].append((s.coin, why))
            steps = kept

    tried = set()
    for s in steps:
        coin = s.coin
        mid = mids.get(coin)
        if not mid:
            res["errors"].append(f"{coin}: mid tidak ada, order ditunda")
            continue
        try:
            d = trader.sz_decimals(coin)
            szi = pos[coin]["szi"] if coin in pos else 0.0
            legs = []
            if s.kind in ("close", "flip"):
                legs.append(("flip_close" if s.kind == "flip" else "close", szi < 0, abs(szi), True))
            if s.kind == "reduce":
                sz = pl.round_sz_down(abs(s.delta) / mid, d)
                if sz > 0:
                    legs.append(("reduce", s.delta > 0, sz, True))
            if s.kind in ("open", "flip"):
                legs.append(("flip_open" if s.kind == "flip" else "open", s.target > 0,
                             pl.order_size(s.target, mid, d, rules.min_order_usdc), False))
            if s.kind == "increase":
                legs.append(("increase", s.delta > 0, pl.order_size(s.delta, mid, d, rules.min_order_usdc), False))
            for kind, is_buy, sz, ro in legs:
                if not ro:
                    if journal:
                        journal(coin)
                    tried.add(coin)
                    if kind in ("open", "flip_open"):
                        lev = max(1, min(ex.leverage, trader.max_leverage(coin)))
                        lv = trader.set_leverage(coin, lev, True)
                        if "error" in lv:
                            res["errors"].append(f"{coin}: set leverage gagal ({str(lv['error'])[:120]})")
                            break
                st = trader.market(coin, is_buy, sz, mid, ex.ioc_slippage, reduce_only=ro,
                                   cloid_hex=cloid(KIND[kind], exec_day, coin, attempt))
                fsz, fpx = _fill(st)
                ok = "error" not in st and fsz > 0
                if not ok:
                    res["errors"].append(f"{coin}: {kind} tidak terisi ({str(st.get('error', st))[:120]})")
                res["orders"].append({"coin": coin, "side": "BUY" if is_buy else "SELL", "kind": kind, "qty": fsz,
                                      "px": fpx, "mid": mid, "reduce_only": ro, "reason": s.reason,
                                      "status": "filled" if ok else "failed"})
                if not ok:
                    break                   # flip: jangan buka arah baru kalau penutupan gagal
        except Exception as e:  # noqa: BLE001
            res["errors"].append(f"{coin}: order gagal ({type(e).__name__})")
    try:
        res["equity_after"], _ = trader.equity()
        after = {c: p for c, p in trader.positions().items() if c in owned or c in tried}
        m2 = trader.mids()
        res["positions_after"] = {c: p["szi"] for c, p in after.items()}
        res["gross_after"] = sum(abs(p["szi"]) * m2.get(c, p["entry_px"]) for c, p in after.items())
        res["net_after"] = sum(p["szi"] * m2.get(c, p["entry_px"]) for c, p in after.items())
    except Exception as e:  # noqa: BLE001
        res["errors"].append(f"baca akun setelah order gagal ({type(e).__name__})")
    return res
