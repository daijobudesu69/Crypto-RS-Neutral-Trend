"""Audit response r06 — a faster alarm than "stop at DD 35%".

Stationary block bootstrap (30-day blocks) of RNT v1.1 daily account returns (IS Binance+dead+real funding, then OOS HYPE).
Worlds:  H1 = edge as backtested | H1/2 = half the backtested mean | H0 = no edge (mean 0) | H0- = no edge and -8%/yr costs.
For each rule: probability of an alarm within 6 / 12 months and the median day of the alarm.
A good rule fires often under H0/H0- (power) and rarely under H1 (false alarm)."""
import os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
r_is = pd.read_csv(os.path.join(HERE, "v11_is_daily.csv"), index_col=0, parse_dates=True)["equity"]
r_oos = pd.read_csv(os.path.join(HERE, "v11_oos_daily.csv"), index_col=0, parse_dates=True)["equity"]
ret = pd.concat([r_is.pct_change().dropna(), r_oos.pct_change().dropna()]).values
mu = ret.mean()
print(f"base series: {len(ret)} days, mean {mu*365*100:.1f}%/yr (simple), vol {ret.std()*np.sqrt(365)*100:.1f}%")
WORLDS = {"H1 edge spt backtest": ret, "H1/2 edge separuh": ret - mu / 2, "H0 tanpa edge": ret - mu,
          "H0- tanpa edge, biaya 8%/th": ret - mu - 0.08 / 365}
rng = np.random.default_rng(7)
N, T, BL = 4000, 365, 30


def paths(x):
    out = np.empty((N, T))
    for i in range(N):
        seq = []
        while len(seq) < T:
            s = rng.integers(0, len(x) - BL)
            seq.extend(x[s:s + BL])
        out[i] = seq[:T]
    return out


def cusum_h(x_h1, k, target_fa=0.10):
    """pick the CUSUM threshold h so the 12-month false-alarm rate under H1 is ~target."""
    S = np.zeros(N); first = np.full(N, np.inf)
    hs = np.linspace(0.05, 1.5, 59)
    best = None
    for h in hs:
        S = np.zeros(N); first = np.full(N, np.inf)
        for t in range(T):
            S = np.maximum(0, S + (k - x_h1[:, t]))
            hit = (S > h) & np.isinf(first)
            first[hit] = t
        fa = np.isfinite(first).mean()
        if fa <= target_fa:
            return h
    return hs[-1]


P = {w: paths(x) for w, x in WORLDS.items()}
eq = {w: np.cumprod(1 + p, axis=1) for w, p in P.items()}
k_ref = (mu + 0) / 2                                    # CUSUM reference between H1 mean and 0
h = cusum_h(P["H1 edge spt backtest"], k_ref, 0.10)
print(f"CUSUM reference k = {k_ref*365*100:.1f}%/yr, threshold h = {h:.2f} (tuned for 10% false alarm/12m under H1)")


def first_alarm(w, rule):
    e = eq[w]; x = P[w]
    if rule.startswith("DD>"):
        th = float(rule[3:]) / 100
        dd = e / np.maximum.accumulate(e, axis=1) - 1
        m = dd < -th
    elif rule.startswith("ret"):
        n, th = rule[3:].split("<")
        n, th = int(n), float(th) / 100
        ef = np.concatenate([np.ones((N, 1)), e], axis=1)
        roll = ef[:, n:] / ef[:, :-n] - 1
        m = np.concatenate([np.zeros((N, n - 1), bool), roll < th], axis=1)[:, :T]
    elif rule == "CUSUM":
        S = np.zeros(N); m = np.zeros((N, T), bool)
        for t in range(T):
            S = np.maximum(0, S + (k_ref - x[:, t])); m[:, t] = S > h
    any_ = m.any(axis=1)
    day = np.where(any_, m.argmax(axis=1), np.nan)
    return day


rules = ["DD>35", "DD>25", "DD>20", "ret90<-12", "ret120<-10", "ret180<-5", "CUSUM"]
rows = []
for rule in rules:
    row = {"aturan": rule}
    for w in WORLDS:
        d = first_alarm(w, rule)
        row[f"{w} | 6bln"] = np.mean(d < 182)
        row[f"{w} | 12bln"] = np.mean(d < 365)
        row[f"{w} | median hari"] = np.nanmedian(d) if np.isfinite(d).any() else np.nan
    rows.append(row)
    print(f"{rule:<10} " + " | ".join(f"{w.split()[0]}: 6m {row[f'{w} | 6bln']*100:4.0f}% 12m {row[f'{w} | 12bln']*100:4.0f}% (med {row[f'{w} | median hari']:.0f}d)" for w in WORLDS), flush=True)
pd.DataFrame(rows).to_csv(os.path.join(HERE, "r06_alarm.csv"), index=False)
