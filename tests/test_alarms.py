import numpy as np
import pandas as pd

from rntbot import alarms


def series(vals, start="2026-10-10"):
    return pd.Series(vals, index=pd.date_range(start, periods=len(vals), freq="D"))


def test_levels_from_drawdown(cfg):
    a = cfg.alarms
    assert alarms.evaluate(series([200, 210, 220]), a).level == "ok"
    st = alarms.evaluate(series([200, 250, 195]), a)          # -22%
    assert st.level == "kuning" and st.dd_pct < -20
    st = alarms.evaluate(series([200, 250, 180]), a)          # -28%
    assert st.level == "merah"
    assert alarms.live_scale("kuning", a) == 0.5 and alarms.live_scale("merah", a) == 1.0


def test_cusum_fires_on_flat_strategy_but_not_on_good_one(cfg):
    a = cfg.alarms
    flat = series(200 * np.ones(600))          # 0%/hari: S = n x k, lewat h=0,45 setelah ±523 hari
    assert alarms.evaluate(flat, a).level == "kuning"         # 0%/hari < k terus-menerus
    good = series(200 * np.cumprod(np.full(400, 1 + 0.6 / 365)))
    st = alarms.evaluate(good, a)
    assert st.level == "ok" and st.cusum == 0.0


def test_since_resets_peak(cfg):
    s = series([200, 300, 210, 215])
    assert alarms.evaluate(s, cfg.alarms).level == "merah"
    assert alarms.evaluate(s, cfg.alarms, since=s.index[2]).level == "ok"


def test_tracking_gap():
    idx = pd.date_range("2026-10-25", "2026-11-30", freq="D")
    paper = pd.Series(np.linspace(200, 220, len(idx)), index=idx)
    live = paper * 0.95
    live.loc["2026-11"] = paper.loc["2026-11"] * 0.90
    g = alarms.tracking_gap(paper, live, "2026-11")
    assert g is not None and -6 < g < -4
    assert alarms.tracking_gap(paper, live, "2026-09") is None
