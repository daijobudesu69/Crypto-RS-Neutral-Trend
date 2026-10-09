import pandas as pd, numpy as np
import dq
pd.set_option("display.width",220); pd.set_option("display.max_rows",300)
H=dq.load_hl(True,"asis"); S=dq.signals(H)
# ---- T02 look-ahead: potong data di tanggal T, hitung ulang bobot, bandingkan dengan bobot versi data penuh
print("== T02 uji look-ahead (potong data)")
mx=0
for T in pd.date_range("2025-01-15","2026-09-30",periods=40).normalize():
    Pt={k:(v.loc[:T] if isinstance(v,pd.DataFrame) else v) for k,v in H.items()}
    St=dq.signals(Pt)
    d=(St["W"].loc[T]-S["W"].loc[T]).abs().max(); mx=max(mx,d)
print("selisih bobot maksimum antara data-terpotong vs data-penuh (40 tanggal):",mx)

# ---- T04 ghost candles
print("\n== T04 candle volume 0")
C,QV=H["close"],H["qv"]; fr=H["first_real"]
D=pd.read_csv("out_indep_daily.csv",index_col=0,parse_dates=True); T=pd.read_csv("out_indep_trips.csv",parse_dates=["entry","exit"]); O=pd.read_csv("out_indep_orders.csv",parse_dates=["date"])
O["qv"]=[QV.at[d,c] for d,c in zip(O.date,O.coin)]
print("order pada hari volume 0:",int((O.qv<=0).sum()),"dari",len(O))
W=S["W"].loc[dq.S0:dq.S1]
held=(W.abs()>0)
zero=(QV.loc[dq.S0:dq.S1]<=0)|QV.loc[dq.S0:dq.S1].isna()
print("hari-koin bobot != 0 saat volume 0:",int((held&zero).sum().sum()))
# koin yang "umur 200 candle"-nya dipenuhi candle hantu: hitung real candles saat pertama kali masuk universe / diperdagangkan
real=(QV>0).cumsum()
T["real_at_entry"]=[real.at[d,c] for d,c in zip(T.entry,T.coin)]
T["ghost_n"]=[int(((QV[c]<=0)&(C[c].notna())&(C.index<fr[c])).sum()) for c in T.coin]
early=T[T.real_at_entry<200]
print("posisi yang dibuka saat koin punya <200 candle NYATA:",len(early),"dari",len(T),"| total PnL",round(early.pnl.sum(),2),"dari",round(T.pnl.sum(),2))
print(early.groupby("coin").agg(n=("pnl","size"),pnl=("pnl","sum"),first=("entry","min"),last=("entry","max"),min_real=("real_at_entry","min")).sort_values("pnl").round(2).to_string())
print("first real ZEC",fr["ZEC"], "| ZEC trips:"); print(T[T.coin=="ZEC"].round(2).to_string())
# ---- variant: buang candle hantu
Hd=dq.load_hl(True,"drop"); Sd=dq.signals(Hd)
Dd,Td,Od=dq.account(Sd["W"],Hd,dq.S0,dq.S1)
print("\nVARIAN candle hantu dibuang  ->",{k:round(v,3) for k,v in dq.stats(Dd.equity).items()}, "orders",len(Od))
for nm,k in [("M1","W1"),("M2","W2")]:
    d,_,_=dq.account(Sd[k],Hd,dq.S0,dq.S1); print("  ",nm,{k:round(v,3) for k,v in dq.stats(d.equity).items()})
Dd.to_csv("out_drop_daily.csv"); Td.to_csv("out_drop_trips.csv",index=False)
y=lambda e:(e.loc["2025"].iloc[-1]/200-1, e.iloc[-1]/e.loc["2025"].iloc[-1]-1)
print("asis 2025/2026:",[round(x,3) for x in y(D.equity)],"drop:",[round(x,3) for x in y(Dd.equity)])
print("by coin PnL (drop) top/bottom:"); g=Td.groupby("coin").pnl.sum().sort_values(); print(g.tail(8).round(1).to_dict()); print(g.head(5).round(1).to_dict())
g0=T.groupby("coin").pnl.sum().sort_values(); print("by coin PnL (asis):",g0.tail(8).round(1).to_dict())
# which coins listed (first real) within OOS or within 200d before
late=fr[fr>=pd.Timestamp("2024-06-15")].sort_values()
inU=S["U20"].loc[dq.S0:dq.S1].any()
print("\nkoin dgn candle hantu yg listing nyata >= 2024-06-15 dan pernah masuk top-20:"); 
for c in late.index:
    gh=int(((QV[c]<=0)&C[c].notna()&(C.index<fr[c])).sum())
    if gh>30 and inU.get(c,False): print(c, fr[c].date(), "ghost",gh, "pertama masuk top20", S["U20"][c].loc[dq.S0:dq.S1].idxmax().date())
