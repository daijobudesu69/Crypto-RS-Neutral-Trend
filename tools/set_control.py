"""Tulis ulang control/bot.yaml. Dipanggil tools/save_control.sh (workflow control.yml).

    python tools/set_control.py --mode live
    python tools/set_control.py --reset-breaker
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rntbot import control  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="tetap")
    ap.add_argument("--reset-breaker", action="store_true")
    a = ap.parse_args()
    cur = control.read((control.PATH,))
    m = cur.mode if a.mode == "tetap" else a.mode
    if m not in control.MODES:
        print(f"[control] mode tidak dikenal: {m}")
        return 2
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    reset = stamp if a.reset_breaker else cur.breaker_reset
    os.makedirs(os.path.dirname(control.PATH), exist_ok=True)
    with open(control.PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(control.render(m, reset))
    print(f"[control] mode={m}" + (" alarm direset" if a.reset_breaker else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
