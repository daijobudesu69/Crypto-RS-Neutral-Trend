import pandas as pd, numpy as np, dq
H=dq.load_hl(True,"asis"); Hd=dq.load_hl(True,"drop")
def run(P,spec,label):
    S=dq.signals(P,spec); D,T,O=dq.account(S["W"],P,dq.S0,dq.S1); st=dq.stats(D.equity)
    d1,_,_=dq.account(S["W1"],P,dq.S0,dq.S1)
    e=D.equity; y25=e.loc["2025"].iloc[-1]/200-1; y26=e.iloc[-1]/e.loc["2025"].iloc[-1]-1
    print(f"{label:<62} akhir {st['end']:6.1f} Sharpe {st['sharpe']:.2f} DD {st['mdd']*100:5.1f}%  2025 {y25*100:+5.1f}% 2026 {y26*100:+5.1f}% | Mesin1 saja {d1.equity.iloc[-1]:6.1f}")
    return D,T
run(H,{}, "A. persis penulis (candle hantu ikut semua)")
run(H,{"hist_mode":"real"}, "B. umur 200 hari dihitung dari candle NYATA saja")
run(H,{"pct_scope":"traded"}, "C. persentil hanya antar koin yg sedang diperdagangkan")
run(H,{"pct_scope":"traded","hist_mode":"real"}, "D. B + C")
run(H,{"pct_scope":"eligible","hist_mode":"real"}, "E. persentil antar koin yg lolos umur (nyata)")
run(H,{"pct_scope":"universe"}, "F. persentil hanya di dalam top-20")
run(H,{"pct_scope":"universe","hist_mode":"real"}, "G. F + umur nyata")
run(Hd,{}, "H. candle hantu dibuang total dari data")
run(Hd,{"pct_scope":"universe"}, "I. H + persentil di dalam top-20")
# how many ghost coins in cross-section over time
C,QV=H["close"],H["qv"]
gh=(C.notna()&(QV<=0))
print("jumlah koin 'hantu' (punya harga, volume 0) per tanggal:", {str(d.date()):int(gh.loc[d].sum()) for d in pd.to_datetime(["2025-01-01","2025-06-01","2025-10-01","2026-01-01","2026-06-01","2026-09-30"])}, "| total koin berharga:", {str(d.date()):int(C.loc[d].notna().sum()) for d in pd.to_datetime(["2025-01-01","2026-09-30"])})
