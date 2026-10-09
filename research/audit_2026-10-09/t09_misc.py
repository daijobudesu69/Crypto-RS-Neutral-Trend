import pandas as pd, numpy as np, dq, os
pd.set_option("display.width",220); pd.set_option("display.max_rows",300)
H=dq.load_hl(True,"asis"); S=dq.signals(H)
D=pd.read_csv("out_indep_daily.csv",index_col=0,parse_dates=True); T=pd.read_csv("out_indep_trips.csv",parse_dates=["entry","exit"]); O=pd.read_csv("out_indep_orders.csv",parse_dates=["date"])
e=D.equity; r=e.pct_change(); r.iloc[0]=e.iloc[0]/200-1
# BERA check
k=pd.read_parquet(dq.LAKE+"/hyperliquid/candles/1d/BERA.parquet"); k["d"]=pd.to_datetime(k.ts).dt.tz_localize(None)
print("BERA HL:"); print(k[(k.d>="2026-02-07")&(k.d<="2026-02-15")][["d","open","high","low","close","volume","trades","quote_volume"]].to_string())
p=dq.EDGE+"/data/bn_dead/1d/BERAUSDT.parquet"
if os.path.exists(p):
    b=pd.read_parquet(p); b["d"]=pd.to_datetime(b.ts).dt.tz_localize(None); print("BERA Binance (arsip):"); print(b[(b.d>="2026-02-07")&(b.d<="2026-02-15")][["d","open","high","low","close","quote_volume"]].to_string())
print("trips BERA:"); print(T[T.coin=="BERA"].round(2).to_string())
print("\n== T09 profil posisi")
T["closed"]=T.exit.notna()
for nm,x in [("semua",T),("long",T[T.side>0]),("short",T[T.side<0])]:
    c=x[x.closed]; print(f"{nm:<6} n={len(x)} (selesai {len(c)}) PnL total {x.pnl.sum():7.1f} | selesai {c.pnl.sum():7.1f} | win rate selesai {100*(c.pnl>0).mean():.0f}% | avg win {c[c.pnl>0].pnl.mean():.2f} avg loss {c[c.pnl<=0].pnl.mean():.2f}")
tot=T.pnl.sum(); s=T.pnl.sort_values(ascending=False)
for kk in [1,3,5,10,20,30]:
    print(f"tanpa {kk:>2} posisi terbaik: PnL {tot-s.head(kk).sum():7.1f} dari {tot:.1f} ({100*s.head(kk).sum()/tot:.0f}% profit dari {kk} posisi)")
print("10 posisi terbaik:"); print(T.sort_values("pnl",ascending=False).head(10).round(2).to_string())
print("5 posisi terburuk:"); print(T.sort_values("pnl").head(5).round(2).to_string())
g=T.groupby("coin").pnl.sum().sort_values(ascending=False); print("PnL per koin (termasuk terbuka) top 8:",g.head(8).round(1).to_dict(),"| bottom 6:",g.tail(6).round(1).to_dict()); print("jumlah koin untung/rugi:",int((g>0).sum()),int((g<=0).sum()), "| top-3 koin =",round(100*g.head(3).sum()/tot),"% dari profit")
lg=T[T.side>0].pnl.sort_values(ascending=False); print("LONG: total",round(lg.sum(),1),"| tanpa 5 terbaik",round(lg.sum()-lg.head(5).sum(),1),"| tanpa 10 terbaik",round(lg.sum()-lg.head(10).sum(),1))
sh=T[T.side<0].pnl.sort_values(ascending=False); print("SHORT: total",round(sh.sum(),1),"| tanpa 5 terbaik",round(sh.sum()-sh.head(5).sum(),1),"| tanpa 10 terbaik",round(sh.sum()-sh.head(10).sum(),1))
# engine attribution of trips is mixed (same coin can be in both engines). Use weights-level attribution
C=H["close"]; R=C.pct_change(fill_method=None).fillna(0)
for nm,k in [("M1 long",S["W1"].clip(lower=0)),("M1 short",S["W1"].clip(upper=0)),("M2 trend",S["W2"])]:
    x=(k.shift(1)*R).sum(axis=1).loc[dq.S0:dq.S1]; print(f"{nm:<9} kontribusi return aritmetik (sebelum biaya) {x.sum()*100:6.1f}% | Sharpe {x.mean()/x.std()*np.sqrt(365):.2f}")
# exclusion tests
for ex in [("ZEC",),("ZEC","ENA","NEAR"),("BERA",),("ZEC","BERA"),("ZEC","ENA","NEAR","BERA","POPCAT")]:
    Sx=dq.signals(H,exclude=ex); Dx,_,_=dq.account(Sx["W"],H,dq.S0,dq.S1); print("tanpa",ex,"-> akhir",round(Dx.equity.iloc[-1],1),"Sharpe",round(dq.stats(Dx.equity)["sharpe"],2))
print("\n== T15 klaim lain di laporan")
btc=R["BTC"].loc[dq.S0:dq.S1]
print("beta ke BTC",round(np.cov(r,btc.reindex(r.index))[0,1]/btc.var(),3),"korelasi",round(np.corrcoef(r,btc.reindex(r.index))[0,1],3))
dn=btc[btc<-0.03].index; up=btc[btc>0.03].index
print("hari BTC < -3%:",len(dn),"rata-rata DUET",round(r.reindex(dn).mean()*100,3),"% | hari BTC > +3%:",len(up),"rata-rata",round(r.reindex(up).mean()*100,3),"%")
al=R.where(S["U20"].shift(1).fillna(False)|True)
for d in ["2025-10-10","2026-02-05"]:
    d=pd.Timestamp(d); med=C.pct_change(fill_method=None).loc[d].where(H["qv"].loc[d]>0).drop("BTC").median()
    print(d.date(),"BTC",round(btc.loc[d]*100,2),"% median altcoin",round(med*100,1),"% DUET",round(r.loc[d]*100,2),"%")
# max adverse move of short positions in OOS
mx=0; who=None
for _,t in T[T.side<0].iterrows():
    c=C[t.coin].loc[t.entry:(t.exit if pd.notna(t.exit) else dq.S1)]
    hi=H["high"][t.coin].loc[t.entry:(t.exit if pd.notna(t.exit) else dq.S1)].iloc[1:]
    a=c.max()/c.iloc[0]-1
    ah=(hi.max()/c.iloc[0]-1) if len(hi) else 0
    if a>mx: mx,who=a,(t.coin,str(t.entry.date()),round(ah,3))
print("short: gerakan melawan terbesar (close)",round(mx,3),who)
dd=e/e.cummax()-1; print("DD maks",round(dd.min(),4),dd.idxmin().date(),"| underwater terlama (hari)",max(len(list(g)) for k_,g in __import__('itertools').groupby(dd<0) if k_))
print("fee",round(-D.fees.sum(),2),"funding",round(D.pnl_funding.sum(),2),"| leverage gross avg/max",round(D.gross_lev.mean(),2),round(D.gross_lev.max(),2),"| net avg",round(D.net_lev.mean(),2))
cl=T[T.closed]; hold=(cl.exit-cl.entry).dt.days; print("lama pegang median/mean",hold.median(),round(hold.mean(),1),"| order",len(O),"| posisi selesai",len(cl))
