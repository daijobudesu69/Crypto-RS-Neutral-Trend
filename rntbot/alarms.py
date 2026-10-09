"""Alarm pengganti "stop di DD 35%" (research/audit_response/AUDIT_RESPONSE.md §4).

  kuning : DD > yellow_dd_pct  ATAU  CUSUM > h      -> ukuran live dipotong (yellow_scale)
  merah  : DD > red_dd_pct                          -> live hanya mengurangi/menutup posisi
  teknis : sekali sebulan, |return live - return paper| > tracking_max_pct poin -> cari bug

CUSUM (Page): S_t = max(0, S_{t-1} + (k - r_t)), k = cusum_k_annual / 365 (separuh return
backtest). Diuji di bootstrap 12 bulan: edge = 0 tertangkap 72%, alarm palsu 9%.
Semua dihitung sejak `since` (awal forward test atau breaker_reset terakhir).
Fungsi di sini murni. Bot menandai + alarm; keputusan berhenti tetap di user.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

LEVELS = ("ok", "kuning", "merah")


@dataclass
class Status:
    level: str = "ok"
    dd_pct: float = 0.0
    peak: float = 0.0
    equity: float = 0.0
    cusum: float = 0.0
    days: int = 0
    reasons: list = field(default_factory=list)


def evaluate(equity: pd.Series, a, since=None) -> Status:
    eq = pd.to_numeric(equity, errors="coerce").dropna()
    if since is not None:
        eq = eq[pd.DatetimeIndex(eq.index) >= pd.Timestamp(since)]
    st = Status()
    if eq.empty:
        return st
    st.days = len(eq)
    st.equity = float(eq.iloc[-1])
    st.peak = float(eq.max())
    st.dd_pct = (st.equity / st.peak - 1) * 100 if st.peak > 0 else 0.0
    k = a.cusum_k_annual / 365
    s = 0.0
    for r in eq.pct_change().dropna().values:
        s = max(0.0, s + (k - r))
    st.cusum = s
    if st.dd_pct < -a.red_dd_pct:
        st.level = "merah"
        st.reasons.append(f"DD {st.dd_pct:.1f}% melewati -{a.red_dd_pct:g}%")
    else:
        if st.dd_pct < -a.yellow_dd_pct:
            st.level = "kuning"
            st.reasons.append(f"DD {st.dd_pct:.1f}% melewati -{a.yellow_dd_pct:g}%")
        if st.cusum > a.cusum_h:
            st.level = "kuning"
            st.reasons.append(f"CUSUM {st.cusum:.2f} > {a.cusum_h:g} (return di bawah ekspektasi terlalu lama)")
    return st


def live_scale(level: str, a) -> float:
    return a.yellow_scale if level == "kuning" else 1.0


def tracking_gap(paper: pd.Series, live: pd.Series, month: str) -> float | None:
    """Selisih return bulan `month` (YYYY-MM) live - paper, dalam poin persen.
    None kalau salah satu tidak punya data di awal DAN akhir bulan itu."""
    out = []
    for s in (paper, live):
        x = pd.to_numeric(s, errors="coerce").dropna()
        x.index = pd.DatetimeIndex(x.index)
        per = x.index.to_period("M")
        m = pd.Period(month, "M")
        before = x[per < m]
        inside = x[per == m]
        if before.empty or inside.empty:
            return None
        out.append(float(inside.iloc[-1]) / float(before.iloc[-1]) - 1)
    return (out[1] - out[0]) * 100
