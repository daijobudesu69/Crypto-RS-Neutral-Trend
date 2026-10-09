"""Canary: buktikan jalur order live RNT di akun HYPE sungguhan, dengan trade kecil.

RNT memegang long DAN short, jadi canary menguji keduanya (±10 USDC per kaki, biaya
±0,02 USDC fee + spread):
  1. API wallet terdaftar & belum kedaluwarsa (verify_agent, sama dengan live)
  2. koin tanpa posisi terbuka di akun
  3. ekuitas terbaca sebelum trade
  4. set leverage cross diterima (sama dengan live)
  5. LONG: beli IOC terisi -> posisi terlihat (cross) -> ekuitas saat posisi terbuka wajar
     -> jual reduce-only terisi penuh
  6. SHORT: jual IOC terisi -> posisi terlihat negatif -> beli reduce-only terisi penuh
  7. ekuitas setelah = sebelum - biaya kecil

Pembersihan selalu jalan: posisi canary yang tersisa ditutup reduce-only dan dilaporkan.
Tidak menulis state/, tidak menyentuh posisi lain.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from . import live
from . import plan as pl

KIND_CANARY = "0c"
EQUITY_TOL_USD = 1.0
MAX_COST_USD = 0.5


@dataclass
class Report:
    coin: str
    steps: list = field(default_factory=list)      # (nama, ok, detail)
    info: list = field(default_factory=list)

    def add(self, name, ok, detail=""):
        self.steps.append((name, bool(ok), str(detail)))
        print(f"  [{'OK' if ok else 'GAGAL'}] {name}" + (f" -- {detail}" if detail else ""))
        return bool(ok)

    @property
    def ok(self) -> bool:
        return bool(self.steps) and all(s[1] for s in self.steps)


_STEP = {"long_open": 1, "long_close": 2, "short_open": 3, "short_close": 4, "cleanup": 5}


def _cloid(coin: str, what: str, now: dt.datetime) -> str:
    return live.cloid(KIND_CANARY, now.isoformat(), coin, _STEP[what])


def _leg(trader, cfg, coin, rep, now, is_long: bool) -> None:
    ex = cfg.execution
    name = "LONG" if is_long else "SHORT"
    mid = trader.mids()[coin]
    sz = pl.order_size(cfg.rules.min_order_usdc, mid, trader.sz_decimals(coin), cfg.rules.min_order_usdc)
    st = trader.market(coin, is_long, sz, mid, ex.ioc_slippage,
                       cloid_hex=_cloid(coin, "long_open" if is_long else "short_open", now))
    filled, px = live._fill(st)
    if not rep.add(f"{name}: {'beli' if is_long else 'jual'} IOC {sz:g} {coin} (±{sz * mid:.2f} USDC) terisi",
                   filled > 0 and "error" not in st, st):
        return
    lim = mid * (1 + ex.ioc_slippage) if is_long else mid * (1 - ex.ioc_slippage)
    rep.add(f"{name}: harga fill {px:g} wajar (mid {mid:g})", (px <= lim) if is_long else (px >= lim), px)
    pos = trader.positions().get(coin)
    want = filled if is_long else -filled
    rep.add(f"{name}: posisi terlihat di akun ({want:+g} {coin}, cross)",
            pos is not None and abs(pos["szi"] - want) < 1e-9 and pos.get("cross", True), pos)
    if is_long:
        p1 = trader.equity_parts()
        eq1, how1 = live.equity_from_parts(p1)
        rep.info.append("posisi terbuka: " + _parts(p1))
        rep.equity_open = eq1
        rep.how_open = how1
    st = trader.market(coin, not is_long, filled, trader.mids()[coin], ex.ioc_slippage, reduce_only=True,
                       cloid_hex=_cloid(coin, "long_close" if is_long else "short_close", now))
    done, _ = live._fill(st)
    rep.add(f"{name}: tutup reduce-only {filled:g} {coin} terisi penuh", abs(done - filled) < 1e-9 and "error" not in st, st)


def run(trader, cfg, coin: str, now: dt.datetime) -> Report:
    rep = Report(coin)
    ex = cfg.execution
    try:
        live.verify_agent(trader, cfg, now)
        rep.add(f"API wallet {ex.agent_address[:10]}… terdaftar dan berlaku", True)
    except live.Halt as e:
        rep.add("API wallet terdaftar dan berlaku", False, e)
        return rep
    if coin in trader.positions():
        rep.add("koin tanpa posisi terbuka", False, f"ada posisi {coin}; canary tidak mau trading di koin ini")
        return rep
    rep.add("koin tanpa posisi terbuka", True)
    eq0 = None
    try:
        p0 = trader.equity_parts()
        eq0, how = live.equity_from_parts(p0)
        rep.add(f"ekuitas terbaca: {eq0:.2f} USDC ({how})", eq0 > cfg.rules.min_order_usdc * 2, p0)
        rep.info.append("sebelum: " + _parts(p0))
        lev = max(1, min(ex.leverage, trader.max_leverage(coin)))
        lv = trader.set_leverage(coin, lev, True)
        rep.add(f"set leverage cross {lev}x diterima", "error" not in lv, lv)
        _leg(trader, cfg, coin, rep, now, is_long=True)
        if getattr(rep, "equity_open", None) is not None:
            rep.add(f"ekuitas saat posisi terbuka {rep.equity_open:.2f} ≈ sebelum ({rep.how_open})",
                    abs(rep.equity_open - eq0) <= EQUITY_TOL_USD, f"selisih {rep.equity_open - eq0:+.4f}")
        _leg(trader, cfg, coin, rep, now, is_long=False)
    except Exception as e:  # noqa: BLE001
        rep.add("langkah canary berjalan tanpa error", False, f"{type(e).__name__}: {e}")
    finally:
        _cleanup(trader, cfg, coin, rep, now)
    try:
        p2 = trader.equity_parts()
        eq2, _ = live.equity_from_parts(p2)
        rep.info.append("sesudah: " + _parts(p2))
        if eq0 is not None:
            cost = eq0 - eq2
            rep.add(f"biaya canary {cost:.4f} USDC (fee + spread)", -EQUITY_TOL_USD <= cost <= MAX_COST_USD, cost)
    except Exception as e:  # noqa: BLE001
        rep.add("ekuitas terbaca setelah trade", False, f"{type(e).__name__}: {e}")
    return rep


def _parts(p: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in p.items())


def _cleanup(trader, cfg, coin, rep, now):
    try:
        p = trader.positions().get(coin)
        if p:
            st = trader.market(coin, p["szi"] < 0, abs(p["szi"]), trader.mids()[coin], cfg.execution.ioc_slippage,
                               reduce_only=True, cloid_hex=_cloid(coin, "cleanup", now))
            left = trader.positions().get(coin)
            rep.add("pembersihan: posisi canary tersisa ditutup", not left, f"{p['szi']:g} {coin}: {st}")
        else:
            rep.add("tidak ada posisi canary tersisa", True)
    except Exception as e:  # noqa: BLE001
        rep.add("cek posisi setelah canary", False, f"{type(e).__name__}: {e} -- CEK POSISI {coin} DI HYPE")


def message(rep: Report) -> str:
    from .notify import esc
    head = ("✅ <b>RNT CANARY OK</b>: jalur order long + short terbukti di akun HYPE"
            if rep.ok else "🚨 <b>RNT CANARY GAGAL</b>: jangan nyalakan live dulu")
    lines = [f"{'✅' if ok else '❌'} {esc(name)}" + ("" if ok else f"\n   <code>{esc(d[:300])}</code>")
             for name, ok, d in rep.steps]
    info = ("\n\n<b>Komponen ekuitas</b> (cocokkan dengan UI HYPE)\n"
            + "\n".join(f"<code>{esc(x)}</code>" for x in rep.info)) if rep.info else ""
    return f"{head} ({esc(rep.coin)})\n\n" + "\n".join(lines) + info
