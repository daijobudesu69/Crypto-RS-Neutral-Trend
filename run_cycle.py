"""Satu siklus bot RNT. Dipanggil watcher GitHub Actions tiap ~10 menit,
atau manual / Task Scheduler di PC:   python run_cycle.py

Setiap siklus:
  1. baca control/bot.yaml (mode)
  2. kalau hari UTC baru sudah mulai (>= 00:02 UTC) dan belum diproses: job harian
     (buku paper + alarm + live kalau mode live/manage/flatten)
  3. kirim pesan Telegram yang tertunda (outbox), catat state/runs.csv

Exit code 0 = sukses (termasuk "tidak ada yang perlu dikerjakan"), 1 = ada error.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import time
import traceback

from rntbot import config, control, hype, jobs, live, notify, store

QUIET_IDLE_MIN = 60     # baris "idle" di runs.csv paling sering 1x per jam
AGENT_WARN_DAYS = 14


def main(now: dt.datetime | None = None, info=None) -> int:
    t0 = time.time()
    now = now or dt.datetime.now(dt.timezone.utc)
    cfg = config.load()
    ctrl = control.read()
    outbox = notify.Outbox(now)
    errors = []

    seen = store.load_json("alerts.json", {}) or {}
    if ctrl.problem and seen.get("control_problem") != ctrl.problem:
        outbox.add(f"⚠️ <b>RNT — control/bot.yaml</b>\n{notify.esc(ctrl.problem)}")
    if seen.get("mode") and seen.get("mode") != ctrl.mode:
        outbox.add(f"🔧 <b>RNT — mode sekarang</b>: <b>{ctrl.mode}</b>")
    if seen.get("control_problem") != ctrl.problem or seen.get("mode") != ctrl.mode:
        seen.update(control_problem=ctrl.problem, mode=ctrl.mode)
        store.save_json("alerts.json", seen)

    key = jobs.agent_key()
    factory = (lambda: live.make_trader(cfg, key)) if key else None
    ctx = jobs.Ctx(cfg=cfg, info=info or hype.InfoClient(cfg.hype.info_url, cfg.hype.weight_per_minute),
                   ctrl=ctrl, outbox=outbox, now=now, trader_factory=factory)
    _account_checks(ctx)

    res = None
    try:
        res = jobs.run_daily(ctx)
    except jobs.DataIncomplete as e:
        print(f"[cycle] data belum lengkap: {e}")
        errors.append(f"daily: {e}"[:300])
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        msg = f"daily: {type(e).__name__}: {str(e)[:200]}"
        errors.append(msg)
        _alert_once(outbox, now, "err_daily", f"⚠️ <b>RNT — job harian gagal</b>\n<code>{notify.esc(msg)}</code>\n"
                    "<i>Dicoba ulang di siklus berikutnya.</i>")
    live_res = (res or {}).get("live") or {}
    errors += [f"live: {e}" for e in live_res.get("errors", [])]

    pending = outbox.flush()
    _log_run(now, ctrl, bool(res), live_res, errors, time.time() - t0)
    if pending:
        print(f"[cycle] {pending} pesan Telegram masih tertahan")
    print(f"[cycle] selesai: daily={bool(res)} errors={len(errors)}")
    return 1 if errors else 0


def _account_checks(ctx) -> None:
    """Sekali per hari UTC, hanya baca: masa berlaku API wallet dan API wallet bot lain
    yang terdaftar di akun utama. Gagal membaca tidak pernah menggagalkan siklus."""
    ex, now = ctx.cfg.execution, ctx.now
    seen = store.load_json("alerts.json", {}) or {}
    today = now.date().isoformat()
    if seen.get("account_check_day") == today:
        return
    seen["account_check_day"] = today
    store.save_json("alerts.json", seen)
    if ex.agent_valid_until:
        left = (dt.date.fromisoformat(ex.agent_valid_until) - now.date()).days
        if left <= AGENT_WARN_DAYS:
            ctx.outbox.add(f"⏳ <b>RNT — API wallet {'SUDAH kedaluwarsa' if left < 0 else f'kedaluwarsa {left} hari lagi'}</b>"
                           f" ({ex.agent_valid_until})\nLive berhenti setelah tanggal itu. Buat API wallet baru di HYPE, "
                           f"ganti secret {notify.esc(ex.agent_secret)}, perbarui agent_address + "
                           "agent_valid_until di config.yaml.")
    if ex.blocked_agents and ex.master_address and ctx.ctrl.live:
        try:
            agents = ctx.info.post({"type": "extraAgents", "user": ex.master_address}, weight=2) or []
        except Exception as e:  # noqa: BLE001
            print(f"[cycle] cek API wallet akun gagal ({type(e).__name__})")
            return
        blocked = {a.lower() for a in ex.blocked_agents}
        bad = [a for a in agents if str(a.get("address", "")).lower() in blocked]
        if bad:
            names = ", ".join(f"{a.get('name', '-')} ({str(a.get('address'))[:10]}…)" for a in bad)
            ctx.outbox.add(f"ℹ️ <b>RNT — API wallet bot lain terdaftar di akun utama</b>\n{notify.esc(names)}\n"
                           "Wajar kalau MEX/RMF memakai akun utama yang sama. Pastikan subaccount RNT tidak "
                           "dipakai bot lain: RNT berhenti kalau ada posisi yang bukan miliknya.")


def _alert_once(outbox, now, key, text, hours=6):
    seen = store.load_json("alerts.json", {}) or {}
    last = seen.get(key)
    if last and (now - dt.datetime.fromisoformat(last)).total_seconds() < hours * 3600:
        return
    outbox.add(text)
    seen[key] = now.isoformat()
    store.save_json("alerts.json", seen)


def _log_run(now, ctrl, did, live_res, errors, dur):
    busy = did or errors
    if not busy and os.environ.get("RNT_QUIET_IDLE") == "1":
        rows = store.read("runs")
        if rows:
            last = dt.datetime.fromisoformat(rows[-1]["time_utc"])
            if (now - last).total_seconds() < QUIET_IDLE_MIN * 60:
                return
    store.append("runs", {"time_utc": now.isoformat(timespec="seconds"),
                          "commit": (os.environ.get("GITHUB_SHA") or "")[:10], "mode": ctrl.mode,
                          "daily": did, "live": bool(live_res), "errors": " | ".join(errors)[:500],
                          "duration_s": round(dur, 1)}, mirror=False)


if __name__ == "__main__":
    sys.exit(main())
