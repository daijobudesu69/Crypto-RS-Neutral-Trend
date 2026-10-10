"""Job harian RNT. Dipanggil run_cycle.py setiap siklus (~10 menit).

Idempoten: state mencatat hari terakhir yang sudah diproses, jadi watcher yang
mengecek tiap 10 menit hanya bekerja sekali per hari UTC (setelah 00:02 UTC =
07:02 WIB). Semua akses jaringan lewat objek `ctx`, supaya tes bisa memakai data tiruan.

Urutan satu hari:
  1. candle 1d semua perp HYPE (450 hari) -> View (target bobot, state/view.json)
  2. buku paper: "paper" (RNT v1.1) dan "rf" (bayangan filter rezim, tidak diadopsi)
  3. alarm (DD + CUSUM) dari riwayat ekuitas -> skala live
  4. live (kalau mode live/manage/flatten)
  5. pesan Telegram, lalu log equity/targets/alarms (+ Sheets)
"""
from __future__ import annotations

import datetime as dt
import os
import traceback
from dataclasses import dataclass, field

import pandas as pd

from . import alarms as al
from . import book as bk
from . import control as ctl
from . import live, notify, plan, store
from . import strategy as stg

DAY_MS = 86_400_000
# Kalau candle sebagian koin gagal diambil, siklus dibatalkan dan dicoba ulang (~10 menit)
# sampai jam ini (UTC). Tanpa ini koin yang gagal hilang dari cross-section dan posisinya
# dijual, hal yang tidak terjadi di backtest (pelajaran RMF audit 2026-10-05 F1).
FETCH_RETRY_UNTIL_H = 3          # 03:00 UTC = 10:00 WIB
BOOKS = {"paper": "targets", "rf": "targets_rf"}


class DataIncomplete(RuntimeError):
    """Data pasar belum lengkap; siklus berikutnya mencoba lagi."""


@dataclass
class Ctx:
    cfg: object
    info: object                       # rntbot.hype.InfoClient (atau tiruan)
    ctrl: ctl.Control
    outbox: notify.Outbox
    now: dt.datetime
    trader_factory: object = None      # () -> trader; None = live tidak tersedia
    _meta: dict | None = None
    log: list = field(default_factory=list)

    def meta(self) -> dict:
        if self._meta is None:
            self._meta = self.info.meta()
        return self._meta

    def say(self, msg: str) -> None:
        print(msg)
        self.log.append(msg)


def utc_day(now: dt.datetime) -> pd.Timestamp:
    return pd.Timestamp(now).tz_convert("UTC").tz_localize(None).normalize()


def naive(now: dt.datetime) -> pd.Timestamp:
    return pd.Timestamp(now).tz_convert("UTC").tz_localize(None)


def started(cfg, now: dt.datetime) -> bool:
    return not cfg.forward_start or utc_day(now) >= pd.Timestamp(cfg.forward_start)


def agent_key() -> str:
    return os.environ.get("RNT_AGENT_KEY", "").strip()


# =========================================================================== #
#  Data -> View
# =========================================================================== #
def tradable_coins(ctx: Ctx) -> list:
    ex = set(ctx.cfg.universe.exclude)
    return sorted(c for c, m in ctx.meta().items() if not m["isDelisted"] and c not in ex)


def fetch_view(ctx: Ctx, exec_day: pd.Timestamp) -> stg.View:
    cfg = ctx.cfg
    now_ms = int(ctx.now.timestamp() * 1000)
    start = now_ms - cfg.universe.fetch_days * DAY_MS
    candles, failed = {}, []
    for c in tradable_coins(ctx):
        try:
            candles[c] = ctx.info.candles(c, "1d", start)
        except Exception as e:  # noqa: BLE001
            if c == cfg.strategy.regime_symbol:
                raise DataIncomplete(f"candle {c} gagal ({type(e).__name__})") from e
            failed.append(f"{c} ({type(e).__name__})")
    if failed:
        names = ", ".join(failed[:20])
        give_up = exec_day + pd.Timedelta(hours=FETCH_RETRY_UNTIL_H)
        if naive(ctx.now) < give_up:
            raise DataIncomplete(f"candle 1d gagal untuk {len(failed)} koin ({names}); "
                                 f"dicoba ulang sampai {FETCH_RETRY_UNTIL_H:02d}:00 UTC")
        ctx.say(f"[daily] candle gagal diambil: {names}")
        ctx.outbox.add(f"🚨 <b>RNT — data candle tidak lengkap</b>\nMasih gagal setelah "
                       f"{FETCH_RETRY_UNTIL_H:02d}:00 UTC: {notify.esc(names)}\nSiklus tetap jalan tanpa koin itu "
                       "(posisinya ditutup kalau ada). Cek manual.")
    last = exec_day - pd.Timedelta(days=1)
    btc = candles.get(cfg.strategy.regime_symbol)
    if btc is None or btc.empty or pd.Timestamp(btc["ts"].iloc[-1]).tz_convert("UTC").tz_localize(None).normalize() != last:
        raise DataIncomplete(f"candle {last.date()} belum tersedia di API")
    return stg.make_view(candles, exec_day, cfg.strategy)


# =========================================================================== #
#  Jadwal
# =========================================================================== #
def daily_due(ctx: Ctx) -> tuple[bool, bool, str]:
    """(paper perlu jalan, live perlu jalan, exec_day)."""
    cfg, now = ctx.cfg, ctx.now
    day = utc_day(now)
    if ctx.ctrl.mode == "off" or not started(cfg, now):
        return False, False, str(day.date())
    if naive(now) < day + pd.Timedelta(minutes=cfg.strategy.run_after_minutes):
        return False, False, str(day.date())
    p = store.load_json("paper.json") or {}
    need_paper = p.get("last_day") != str(day.date()) or bool(p.get("pending_record"))
    need_live = False
    if ctx.ctrl.live:
        ls = store.load_json("live.json") or {}
        tries = (ls.get("attempts") or {}).get(str(day.date()), 0)
        if ctx.ctrl.mode == "flatten":
            need_live = bool(ls.get("positions")) or ls.get("flatten_day") != str(day.date())
        else:
            need_live = ls.get("last_day") != str(day.date()) and tries < cfg.execution.max_live_attempts_per_day
    return need_paper, need_live, str(day.date())


# =========================================================================== #
#  Job harian
# =========================================================================== #
def run_daily(ctx: Ctx) -> dict | None:
    need_paper, need_live, exec_day = daily_due(ctx)
    if not (need_paper or need_live):
        return None
    cfg = ctx.cfg
    _finish_stale_record(ctx, exec_day)
    vdoc = store.load_json("view.json")
    if vdoc and vdoc.get("exec_day") == exec_day:
        view = stg.View.from_dict(vdoc)
    else:
        view = fetch_view(ctx, pd.Timestamp(exec_day))
        store.save_json("view.json", view.to_dict())
    mids = ctx.info.all_mids()
    t = ctx.now.isoformat(timespec="seconds")
    delay = (naive(ctx.now) - pd.Timestamp(exec_day)).total_seconds() / 60
    out = {"exec_day": exec_day, "view": view, "delay_min": delay, "paper": {}, "live": None}

    p = store.load_json("paper.json") or {}
    trade_paper = need_paper and p.get("last_day") != exec_day
    if trade_paper:
        for name, attr in BOOKS.items():
            p.setdefault(name, bk.new_book(cfg.capital_usdc))
            out["paper"][name] = _paper_day(ctx, name, p[name], getattr(view, attr), mids, t, exec_day)
        p["last_day"] = exec_day
        p["pending_record"] = {"exec_day": exec_day, "time_utc": t, "delay_min": round(delay, 1),
                               **{f"{n}_equity": r["equity"] for n, r in out["paper"].items()},
                               "paper_gross": out["paper"]["paper"]["gross"], "paper_net": out["paper"]["paper"]["net"],
                               "paper_long": out["paper"]["paper"]["n_long"],
                               "paper_short": out["paper"]["paper"]["n_short"]}
        store.save_json("paper.json", p)

    alarm = _alarm_now(ctx, p, out)
    out["alarm"] = alarm
    if need_live:
        out["live"] = _live_day(ctx, view, exec_day, t, alarm)

    if trade_paper:
        # Urutan: order tercatat -> pesan dikirim SEKARANG -> baru log & cek bulanan.
        ctx.outbox.add(daily_message(ctx, view, out, p, mids))
        ctx.outbox.flush()
    if out["live"] is not None:
        ctx.outbox.add(_live_message(out["live"], ctx, _perf(ctx, p, out)[0]))
    if p.get("pending_record"):
        _record_day(ctx, p, view, out)
        store.save_json("paper.json", p)
    return out


def _finish_stale_record(ctx: Ctx, exec_day: str) -> None:
    """Pencatatan hari sebelumnya yang terputus diselesaikan SEBELUM hari baru."""
    p = store.load_json("paper.json") or {}
    rec = p.get("pending_record")
    if not rec or rec.get("exec_day") == exec_day:
        return
    vdoc = store.load_json("view.json")
    if not vdoc or vdoc.get("exec_day") != rec["exec_day"]:
        ctx.say(f"[daily] catatan {rec['exec_day']} tidak bisa diselesaikan (view hilang); dibuang")
        p.pop("pending_record", None)
        store.save_json("paper.json", p)
        return
    ctx.say(f"[daily] menyelesaikan catatan {rec['exec_day']} yang terputus")
    _record_day(ctx, p, stg.View.from_dict(vdoc), {"alarm": None})
    store.save_json("paper.json", p)


def _accrue_funding(ctx: Ctx, b: dict, mids: dict) -> float:
    """Funding riil HYPE untuk posisi paper sejak terakhir dihitung (long bayar, short terima)."""
    total = 0.0
    now_ms = int(ctx.now.timestamp() * 1000)
    for coin, pos in b["positions"].items():
        start = int(pos.get("funding_ms") or pd.Timestamp(pos["entry_time"]).value // 10**6)
        if now_ms - start < 3_600_000:
            continue
        try:
            rates = ctx.info.funding_history(coin, start + 1, now_ms)
        except Exception as e:  # noqa: BLE001
            ctx.say(f"[daily] funding {coin} gagal ({type(e).__name__}); dicoba besok")
            continue
        amt = bk.funding_amount(pos["qty"], bk.px_of(b, coin, mids), rates)
        bk.charge_funding(b, coin, amt)
        pos["funding_ms"] = max([tm for tm, _ in rates], default=start)
        total += amt
    return total


def _paper_day(ctx: Ctx, name: str, b: dict, targets: dict, mids: dict, t: str, exec_day: str) -> dict:
    cfg = ctx.cfg
    funding = _accrue_funding(ctx, b, mids)
    bk.mark(b, mids)
    eq0 = bk.equity(b, mids)
    cur = bk.notional(b, mids)
    priced = {c for c in mids if c in ctx.meta() and not ctx.meta()[c]["isDelisted"]}
    steps = plan.plan(targets, eq0, cur, priced, cfg.rules.min_order_usdc, cfg.rules.band)
    fills = bk.apply_plan(b, steps, mids, ctx.meta(), cfg.costs, cfg.rules.min_order_usdc, t)
    now_ms = int(ctx.now.timestamp() * 1000)
    for f in fills:
        pos = b["positions"].get(f["coin"])
        if pos is not None and not pos.get("funding_ms"):
            pos["funding_ms"] = now_ms
        store.append("orders", {"time_utc": t, "book": name, "exec_day": exec_day, "coin": f["coin"],
                                "side": f["side"], "kind": f["kind"], "qty": f["qty"], "px": f["px"],
                                "mid": mids.get(f["coin"]), "notional": f["notional"], "fee": f["fee"],
                                "reduce_only": "", "reason": f["reason"], "status": "paper"},
                     mirror=(name == "paper"))
        if f.get("closed"):
            c = f["closed"]
            store.append("positions", {"book": name, "coin": c["coin"], "side": "long" if c["side"] > 0 else "short",
                                       "entry_time": c["entry_time"], "exit_time": c["exit_time"], "pnl": c["pnl"],
                                       "fees": c["fees"], "funding": c["funding"]}, mirror=(name == "paper"))
    bk.mark(b, mids)
    longs = sorted(c for c, x in b["positions"].items() if x["qty"] > 0)
    shorts = sorted(c for c, x in b["positions"].items() if x["qty"] < 0)
    return {"equity_before": eq0, "equity": bk.equity(b, mids), "gross": bk.gross(b, mids), "net": bk.net(b, mids),
            "fills": fills, "funding": funding, "longs": longs, "shorts": shorts,
            "n_long": len(longs), "n_short": len(shorts)}


# =========================================================================== #
#  Alarm
# =========================================================================== #
def _equity_history(col: str) -> pd.Series:
    rows = store.read("equity")
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows)
    if col not in df:
        return pd.Series(dtype=float)
    df["exec_day"] = pd.to_datetime(df["exec_day"])
    df = df.drop_duplicates("exec_day", keep="last").set_index("exec_day").sort_index()
    return pd.to_numeric(df[col], errors="coerce").dropna()


def _alarm_now(ctx: Ctx, p: dict, out: dict) -> al.Status:
    """Level alarm SEBELUM live trading: riwayat equity.csv + ekuitas hari ini.
    Live memakai ekuitas live kalau sudah punya riwayat; selain itu paper."""
    cfg = ctx.cfg
    st = store.load_json("alarm_state.json", {}) or {}
    if ctx.ctrl.breaker_reset and ctx.ctrl.breaker_reset != st.get("reset_seen"):
        st.update(reset_seen=ctx.ctrl.breaker_reset, since=str(utc_day(ctx.now).date()))
        ctx.outbox.add("🔄 <b>RNT — alarm di-reset</b> (breaker_reset): puncak ekuitas dan CUSUM dihitung "
                       f"ulang mulai {st['since']}")
    since = st.get("since") or ctx.cfg.forward_start or None
    book, col = "paper", "paper_equity"
    hist_live = _equity_history("live_equity")
    if ctx.ctrl.live and len(hist_live):
        book, col = "live", "live_equity"
    s = _equity_history(col)
    today = (out.get("paper", {}).get("paper") or {}).get("equity") if book == "paper" else None
    if book == "live":
        ls = store.load_json("live.json") or {}
        today = ls.get("last_equity")
    if today is not None:
        s.loc[utc_day(ctx.now)] = float(today)
        s = s.sort_index()
    status = al.evaluate(s, cfg.alarms, since)
    status.book = book
    if st.get("level") != status.level:
        icon = {"ok": "✅", "kuning": "🟡", "merah": "🔴"}[status.level]
        act = {"ok": "ukuran normal", "kuning": f"ukuran live dikali {cfg.alarms.yellow_scale:g}",
               "merah": "live hanya mengurangi/menutup posisi. Keputusan berhenti di tanganmu: "
                        "gh workflow run control.yml -f mode=flatten"}[status.level]
        if st.get("level") or status.level != "ok":
            ctx.outbox.add(f"{icon} <b>RNT — alarm {status.level.upper()}</b> ({book})\n"
                           + ("\n".join(f"• {notify.esc(x)}" for x in status.reasons) or "• kembali normal")
                           + f"\nDD {status.dd_pct:.1f}% · CUSUM {status.cusum:.2f}/{cfg.alarms.cusum_h:g}\n"
                           f"<i>{notify.esc(act)}</i>")
        store.append("alarms", {"time_utc": ctx.now.isoformat(timespec="seconds"), "book": book,
                                "level": status.level, "dd_pct": status.dd_pct, "cusum": status.cusum,
                                "reason": "; ".join(status.reasons)})
        st["level"] = status.level
    store.save_json("alarm_state.json", st)
    return status


def _tracking_check(ctx: Ctx) -> None:
    """Sekali per bulan: return live vs paper bulan lalu (cek teknis, bukan cek edge)."""
    if not ctx.ctrl.live:
        return
    st = store.load_json("alarm_state.json", {}) or {}
    month = (utc_day(ctx.now).to_period("M") - 1).strftime("%Y-%m")
    if st.get("tracking_month") == month:
        return
    gap = al.tracking_gap(_equity_history("paper_equity"), _equity_history("live_equity"), month)
    st["tracking_month"] = month
    store.save_json("alarm_state.json", st)
    if gap is None:
        return
    lim = ctx.cfg.alarms.tracking_max_pct
    if abs(gap) > lim:
        ctx.outbox.add(f"🛠 <b>RNT — cek teknis {month}</b>: return live − paper = {gap:+.1f} poin "
                       f"(batas ±{lim:g}). Cari penyebab eksekusi (fill, order gagal, posisi di luar bot) "
                       "sebelum lanjut.")
    else:
        ctx.say(f"[daily] cek teknis {month}: live − paper {gap:+.1f} poin (OK)")


# =========================================================================== #
#  Live
# =========================================================================== #
def _live_day(ctx: Ctx, view: stg.View, exec_day: str, t: str, alarm: al.Status) -> dict:
    cfg = ctx.cfg
    ls = store.load_json("live.json") or {}
    attempts = {k: v for k, v in (ls.get("attempts") or {}).items() if k >= exec_day}
    n = attempts.get(exec_day, 0)
    attempts[exec_day] = n + 1
    ls["attempts"] = attempts
    res = {"mode": ctx.ctrl.mode, "errors": [], "orders": [], "alarm": alarm.level}
    try:
        if ctx.trader_factory is None:
            raise live.Halt(f"secret API wallet ({cfg.execution.agent_secret}) belum diisi; live tidak bisa jalan")
        trader = ctx.trader_factory()
        owned = set(ls.get("positions") or {}) | set(ls.get("pending") or [])
        # posisi milik RNT yang hilang tanpa order bot (likuidasi, ADL, manual, delist)
        actual = trader.positions()
        gone = sorted(c for c in (ls.get("positions") or {}) if c not in actual)
        if gone:
            ctx.outbox.add(f"⚠️ <b>RNT — posisi hilang di luar bot</b>: {notify.esc(', '.join(gone))}\n"
                           "Kemungkinan likuidasi, ADL, delisting, atau ditutup manual. Bot menyesuaikan ke target.")
            owned -= set(gone)
        meta = ctx.meta()
        untradable = frozenset(c for c in view.targets if c not in meta or meta[c].get("onlyIsolated")
                               or meta[c].get("isDelisted"))

        def journal(coin):          # tulis dulu sebelum order: koin ini milik RNT
            ls.setdefault("pending", [])
            if coin not in ls["pending"]:
                ls["pending"].append(coin)
            store.save_json("live.json", ls)

        red = alarm.level == "merah"
        r = live.run(view.targets, exec_day, cfg, trader, ctx.ctrl.mode, ctx.now,
                     scale=al.live_scale(alarm.level, cfg.alarms), reduce_only_mode=red, attempt=n,
                     owned=frozenset(owned), untradable=untradable, journal=journal,
                     block_reason="alarm MERAH" if red else "")
        res.update(r)
        for o in r["orders"]:
            store.append("orders", {"time_utc": t, "book": "live", "exec_day": exec_day, "coin": o["coin"],
                                    "side": o["side"], "kind": o["kind"], "qty": o["qty"], "px": o["px"],
                                    "mid": o["mid"], "notional": o["qty"] * o["px"], "fee": "",
                                    "reduce_only": int(o["reduce_only"]), "reason": o["reason"],
                                    "status": o["status"]})
        if "positions_after" in r:
            ls["positions"] = dict(r["positions_after"])
            ls["pending"] = []
        ls["last_equity"] = r.get("equity_after", r.get("equity_before"))
        ls["last_gross"] = r.get("gross_after")
        ls["last_net"] = r.get("net_after")
        if ctx.ctrl.mode == "flatten":
            ls["flatten_day"] = exec_day
        if not r["errors"]:
            ls["last_day"] = exec_day
    except live.Halt as e:
        res["errors"].append(f"HALT: {e}")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        res["errors"].append(f"live gagal: {type(e).__name__}")
    store.save_json("live.json", ls)
    return res


# =========================================================================== #
#  Catatan harian
# =========================================================================== #
def _record_day(ctx: Ctx, p: dict, view: stg.View, out: dict) -> None:
    rec = p["pending_record"]
    pb = p.get("paper") or {}
    peak = float(pb.get("peak_equity", rec.get("paper_equity") or 0) or 0)
    eq = rec.get("paper_equity")
    ls = store.load_json("live.json") or {}
    a = out.get("alarm")
    store.append("equity", {
        "exec_day": rec["exec_day"], "time_utc": rec["time_utc"], "paper_equity": eq,
        "paper_gross": rec.get("paper_gross"), "paper_net": rec.get("paper_net"),
        "paper_long": rec.get("paper_long"), "paper_short": rec.get("paper_short"), "paper_peak": peak,
        "paper_dd_pct": (eq / peak - 1) * 100 if eq and peak else 0.0, "rf_equity": rec.get("rf_equity"),
        "live_equity": ls.get("last_equity") if ctx.ctrl.live else "",
        "live_gross": ls.get("last_gross") if ctx.ctrl.live else "",
        "live_net": ls.get("last_net") if ctx.ctrl.live else "",
        "live_positions": len(ls.get("positions") or {}) if ctx.ctrl.live else "",
        "alarm_level": a.level if a else "", "alarm_book": getattr(a, "book", "") if a else "",
        "dd_pct": a.dd_pct if a else "", "cusum": a.cusum if a else "",
        "k_rs": view.k_rs, "k_tr": view.k_tr, "btc_close": view.btc_close, "btc_up90": view.btc_up90,
        "target_gross": view.gross, "target_net": view.net, "n_traded": view.n_traded,
        "delay_min": rec.get("delay_min")})
    held_p = set((p.get("paper") or {}).get("positions", {}))
    held_l = set(ls.get("positions") or {})
    for c in sorted(set(view.targets) | set(view.targets_rf) | held_p | held_l):
        store.append("targets", {"exec_day": view.exec_day, "coin": c, "w": view.targets.get(c, 0.0),
                                 "w_rs": view.w_rs.get(c, 0.0), "w_tr": view.w_tr.get(c, 0.0),
                                 "w_rf": view.targets_rf.get(c, 0.0), "rs_rank": view.rs_rank.get(c, ""),
                                 "in_rs": c in view.rs_universe, "in_tr": c in view.tr_universe,
                                 "held_paper": c in held_p, "held_live": c in held_l}, mirror=False)
    p.pop("pending_record", None)
    _tracking_check(ctx)


# =========================================================================== #
#  Pesan
# =========================================================================== #
def _fmt_side(b: dict, mids: dict, sign: int) -> str:
    eq = bk.equity(b, mids) or 1.0
    items = sorted(((c, n / eq) for c, n in bk.notional(b, mids).items() if (n > 0) == (sign > 0)),
                   key=lambda x: -abs(x[1]))
    return " ".join(f"{notify.esc(c)} {abs(w) * 100:.0f}%" for c, w in items) or "-"


def _perf(ctx: Ctx, p: dict, out: dict) -> tuple[float, float]:
    """(PnL %, DD %) sejak awal. Live memakai ekuitas live kalau sudah punya riwayat; selain itu paper."""
    pb = p["paper"]
    if ctx.ctrl.live:
        hist = _equity_history("live_equity")
        last = (store.load_json("live.json") or {}).get("last_equity")
        if len(hist) and last:
            peak = max(float(hist.max()), float(last))
            return (float(last) / float(hist.iloc[0]) - 1) * 100, abs(min(0.0, (float(last) / peak - 1) * 100))
    eq = out["paper"]["paper"]["equity"]
    peak = float(pb.get("peak_equity", eq))
    start = float(pb.get("start_capital", ctx.cfg.capital_usdc))
    return (eq / start - 1) * 100, abs(min(0.0, (eq / peak - 1) * 100)) if peak else 0.0


def _coin_pnl(b: dict, coin: str, mids: dict) -> float:
    pos = b["positions"][coin]
    cost = float(pos.get("cost") or 0.0)
    return (pos["qty"] * bk.px_of(b, coin, mids) - cost) / abs(cost) * 100 if cost else 0.0


def _sleeve_lines(b: dict, sleeve: dict, mids: dict) -> list[str]:
    """Posisi terbuka milik satu mesin (koin yang ada di targetnya hari ini), long dulu lalu short."""
    held = [c for c in b["positions"] if c in sleeve]
    out = []
    for icon, name, sign in (("🟢", "Long", 1), ("🔴", "Short", -1)):
        cs = sorted((c for c in held if b["positions"][c]["qty"] * sign > 0),
                    key=lambda c: -abs(bk.notional(b, mids)[c]))
        if cs:
            out.append(f"  {icon} Open {name} Position: "
                       + " ".join(f"{notify.esc(c)} ({_coin_pnl(b, c, mids):+.1f}%)" for c in cs))
    return out or ["No Open Position"]


def daily_message(ctx: Ctx, view: stg.View, out: dict, p: dict, mids: dict) -> str:
    cfg = ctx.cfg
    pb = p["paper"]
    pnl, dd = _perf(ctx, p, out)
    t = pd.Timestamp(ctx.now).tz_convert("UTC").strftime("%Y-%m-%d %H:%M")
    day_n = ""
    if cfg.forward_start:
        day_n = f" · hari ke-{(pd.Timestamp(view.exec_day) - pd.Timestamp(cfg.forward_start)).days + 1}"
    lines = [
        f"📊 <b>RNT forward test · {'Live' if ctx.ctrl.live else 'Paper'}{day_n}</b>",
        f"<code>{t} UTC · candle {view.last_close_day} · telat {out['delay_min']:.0f} menit</code>",
        "",
        f"📈 PnL: {pnl:+.1f}% · DD {dd:.1f}%",
        "",
        "<b>Relative Strength Report</b>",
        *_sleeve_lines(pb, view.w_rs, mids),
        "",
        "<b>Trend Report</b>",
        *_sleeve_lines(pb, view.w_tr, mids),
    ]
    return "\n".join(lines)


def _live_message(lv: dict, ctx: Ctx, pnl: float | None = None) -> str:
    eq = lv.get("equity_after", lv.get("equity_before"))
    lines = [f"⚡ <b>RNT live</b>: {notify.usd(eq)} USDC"
             + (f" ({pnl:+.1f}%)" if pnl is not None else "") + f" · order {len(lv.get('orders', []))}"]
    for o in lv.get("orders", [])[:15]:
        lines.append(f"  {'✅' if o['status'] == 'filled' else '❌'} {o['side']} {notify.esc(o['coin'])} "
                     f"{o['qty']:g} @ {o['px']:g} ({notify.esc(o['kind'])})")
    if lv.get("skipped"):
        lines.append("  dilewati: " + ", ".join(f"{notify.esc(c)} ({notify.esc(w)})" for c, w in lv["skipped"][:10]))
    for e in lv.get("errors", [])[:8]:
        lines.append(f"  ⚠️ {notify.esc(e)}")
    return "\n".join(lines)


def daily_message_from_state(ctx: Ctx) -> str | None:
    """Ringkasan terakhir dari state (dipakai smoke test)."""
    p = store.load_json("paper.json") or {}
    v = store.load_json("view.json")
    if not p.get("paper") or not v:
        return None
    pb = p["paper"]
    mids = {c: x.get("last_px") for c, x in pb["positions"].items()}
    eq = bk.equity(pb, mids)
    return (f"📊 <b>RNT — status terakhir ({notify.esc(v['exec_day'])})</b>\n"
            f"Paper v1.1: {notify.usd(eq)} USDC\n  🟢 long: {_fmt_side(pb, mids, +1)}\n"
            f"  🔴 short: {_fmt_side(pb, mids, -1)}")
