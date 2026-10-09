"""Kendali mode bot, dibaca SETIAP siklus dari control/bot.yaml.

Diubah lewat workflow control.yml (atau edit file di main). Watcher menarik origin
tiap siklus (tools/refresh_state.sh menyalin versi origin ke CACHE), jadi perubahan
berlaku <= ~10 menit.

mode:
  off      tidak melakukan apa-apa (buku paper juga berhenti)
  paper    hanya buku paper (DEFAULT, aman)
  live     buku paper + eksekusi live di subaccount RNT
  manage   buku paper + live hanya MENGURANGI/menutup posisi (rem: tanpa posisi baru/tambahan)
  flatten  buku paper + tutup SEMUA posisi live milik RNT tiap siklus sampai mode diganti
breaker_reset: nilai BARU apa pun = puncak ekuitas & CUSUM alarm di-reset (alarm merah/kuning lepas).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import yaml

from .config import ROOT

MODES = ("off", "paper", "live", "manage", "flatten")
PATH = os.path.join(ROOT, "control", "bot.yaml")
CACHE = os.path.join(ROOT, ".rnt_control_origin.yaml")   # ditulis refresh_state.sh, di-gitignore
LIVE_MODES = ("live", "manage", "flatten")


@dataclass
class Control:
    mode: str = "paper"
    breaker_reset: str = ""
    problem: str | None = None

    @property
    def live(self) -> bool:
        return self.mode in LIVE_MODES


def _norm(v) -> str:
    # YAML 1.1 membaca `off` tanpa kutip sebagai boolean False.
    if v is False:
        return "off"
    return str(v or "").strip().lower()


def read(paths=None) -> Control:
    paths = paths or (CACHE, PATH)
    p = next((x for x in paths if os.path.exists(x)), None)
    if p is None:
        return Control(problem="control/bot.yaml tidak ada; dipakai paper")
    try:
        with open(p, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        if not isinstance(doc, dict):
            raise ValueError("bukan pasangan kunci: nilai")
    except Exception as e:  # noqa: BLE001
        # File rusak tidak boleh membuka posisi baru: fallback paper = akun live tidak disentuh.
        return Control(problem=f"control/bot.yaml tidak bisa dibaca ({type(e).__name__}); dipakai paper")
    c = Control(mode=_norm(doc.get("mode", "paper")), breaker_reset=str(doc.get("breaker_reset") or "").strip())
    if c.mode not in MODES:
        c.problem = f"mode '{c.mode}' tidak dikenal; dipakai paper"
        c.mode = "paper"
    return c


def render(mode: str, breaker_reset: str) -> str:
    if mode not in MODES:
        raise ValueError("mode tidak dikenal")
    return f"""\
# Kendali bot RNT. Dibaca watcher SETIAP siklus (~10 menit).
# Ubah lewat workflow (PowerShell / CMD / Git Bash):
#   gh workflow run control.yml -f mode=live
#   gh workflow run control.yml -f mode=manage       # rem: hanya kurangi/tutup posisi
#   gh workflow run control.yml -f mode=flatten      # tutup semua posisi live
#   gh workflow run control.yml -f reset_breaker=true
#
# mode: off | paper | live | manage | flatten
mode: "{mode}"
breaker_reset: "{breaker_reset}"
"""
