"""Target bobot -> rencana order. Dipakai buku paper DAN live, jadi keduanya
mengikuti aturan yang sama dengan backtest (research/code/account.py):

  * target USD = bobot x ekuitas
  * |target| < min_order: dibulatkan ke +-min_order kalau |target| >= min_order/2, selain itu 0
  * posisi searah tidak disentuh selama |target - posisi| <= max(min_order, band x |target|)
  * perubahan < min_order dilewati, kecuali menutup posisi (target 0)
  * koin tanpa harga hari ini (delist / data hilang): posisi ditutup

Semua angka dalam USD notional bertanda (+ long, - short) pada harga saat ini.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Step:
    coin: str
    current: float          # notional sekarang (bertanda)
    target: float           # notional tujuan (bertanda)
    reason: str

    @property
    def delta(self) -> float:
        return self.target - self.current

    @property
    def kind(self) -> str:
        """open | close | flip | increase | reduce"""
        if self.current == 0:
            return "open"
        if self.target == 0:
            return "close"
        if math.copysign(1, self.current) != math.copysign(1, self.target):
            return "flip"
        return "increase" if abs(self.target) > abs(self.current) else "reduce"


def round_target(t: float, min_order: float) -> float:
    if abs(t) < min_order:
        return math.copysign(min_order, t) if abs(t) >= min_order / 2 else 0.0
    return t


def plan(weights: dict, equity: float, current: dict, priced: set, min_order: float, band: float,
         scale: float = 1.0) -> list[Step]:
    """weights {coin: bobot}, current {coin: notional bertanda}, priced = koin yang punya harga hari ini.
    scale < 1 = alarm kuning (ukuran dipotong)."""
    steps = []
    for coin in sorted(set(weights) | set(current)):
        cur = float(current.get(coin, 0.0))
        if coin not in priced:
            if cur != 0:
                steps.append(Step(coin, cur, 0.0, "tidak ada harga (delist/data hilang)"))
            continue
        tg = round_target(float(weights.get(coin, 0.0)) * equity * scale, min_order)
        if cur == 0 and tg == 0:
            continue
        same_side = cur != 0 and math.copysign(1, cur) == math.copysign(1, tg) and tg != 0
        if same_side and abs(tg - cur) <= max(min_order, band * abs(tg)):
            continue
        if abs(tg - cur) < min_order and tg != 0:
            continue
        why = "keluar dari buku" if tg == 0 else ("masuk" if cur == 0 else "rebalance")
        steps.append(Step(coin, cur, tg, why))
    return steps


def order_size(usd: float, px: float, sz_decimals: int, min_usd: float, floor_buffer: float = 1.005) -> float:
    """Ukuran koin dibulatkan ke szDecimals; notional order baru tidak pernah < minimum
    (+0,5% buffer untuk pergerakan harga sampai order masuk)."""
    if px <= 0:
        raise ValueError("harga harus > 0")
    q = 10 ** sz_decimals
    sz = round(abs(usd) / px * q) / q
    floor_usd = min_usd * floor_buffer
    if sz * px < floor_usd:
        sz = math.ceil(floor_usd / px * q - 1e-9) / q
    return sz


def round_sz_down(sz: float, d: int) -> float:
    q = 10 ** d
    return math.floor(abs(sz) * q + 1e-9) / q
