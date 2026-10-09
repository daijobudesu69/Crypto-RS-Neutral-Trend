import pandas as pd, numpy as np, dq
pd.set_option("display.width",220); pd.set_option("display.max_rows",300)
H=dq.load_hl(True,"asis"); B=dq.load_bn(False)
S=dq.signals(H)
c=[x for x in H["close"].columns if x in B["close"].columns]
print("koin di HL:",H["close"].shape[1],"| juga ada di Binance:",len(c))
rh=H["close"][c].pct_change(fill_method=None).loc[dq.S0:dq.S1]; rb=B["close"][c].pct_change(fill_method=None).loc[dq.S0:dq.S1]
real=(H["qv"][c].loc[dq.S0:dq.S1]>0)
a=rh.where(real).stack(); b=rb.where(real).stack(); j=pd.concat([a,b],axis=1,keys=["hl","bn"]).dropna()
print("korelasi return harian HL vs Binance (hari bervolume, OOS):",round(j.corr().iloc[0,1],5),"n",len(j))
d=(j.hl-j.bn); print("selisih return harian: median abs",d.abs().median(),"p99",d.abs().quantile(.99),"max",d.abs().max())
print("10 selisih terbesar:"); print(pd.concat([j,d.rename("diff")],axis=1).reindex(d.abs().sort_values(ascending=False).index[:10]).round(4).to_string())
# level check
lv=(H["close"][c]/B["close"][c]-1).loc[dq.S0:dq.S1].where(real)
print("selisih LEVEL harga close HL vs Binance: median abs",float(lv.abs().stack().median()),"p99",float(lv.abs().stack().quantile(.99)),"max",float(lv.abs().stack().max()))
# coverage of traded coins
W=S["W"].loc[dq.S0:dq.S1]; tr=W.columns[(W.abs()>0).any()]
print("koin yang pernah dipegang strategi:",len(tr),"| tidak ada di Binance top-150:",[x for x in tr if x not in c])
gross=W.abs().sum(); print("porsi eksposur pada koin yang bisa dicek silang ke Binance:",round(gross[c].sum()/gross.sum(),4))
# strategy PnL recomputed with Binance returns for overlapping coins (weights from HL)
D=pd.read_csv("out_indep_daily.csv",index_col=0,parse_dates=True)
Hx={k:(v.copy() if isinstance(v,pd.DataFrame) else v) for k,v in H.items()}
bc=B["close"][c].reindex(H["close"].index)
m=real.reindex(H["close"].index).fillna(False)&bc.notna()
Hx["close"][c]=H["close"][c].where(~m,bc)
Dx,_,_=dq.account(S["W"],Hx,dq.S0,dq.S1)
print("Bobot dari HL, tapi untung-rugi dihitung dgn harga BINANCE utk koin yg tumpang tindih -> akhir",round(Dx.equity.iloc[-1],1),"Sharpe",round(dq.stats(Dx.equity)["sharpe"],2))
# full strategy on Binance data only
SB=dq.signals(B); DB,_,_=dq.account(SB["W"],B,dq.S0,dq.S1); print("Strategi penuh di data BINANCE (universe Binance, akun 200):",{k:round(v,3) for k,v in dq.stats(DB.equity).items()})
for nm,k in [("M1","W1"),("M2","W2")]:
    d_,_,_=dq.account(SB[k],B,dq.S0,dq.S1); print("  ",nm,round(d_.equity.iloc[-1],1), round(dq.stats(d_.equity)["sharpe"],2))
# benchmarks
r=H["close"].pct_change(fill_method=None)
btc=(1+r["BTC"].loc[dq.S0:dq.S1].fillna(0)).cumprod()*200
ew=(1+r.where(S["U20"].shift(1)).mean(axis=1).loc[dq.S0:dq.S1].fillna(0)).cumprod()*200
print("BTC beli-tahan:",round(btc.iloc[-1],1),"DD",round((btc/btc.cummax()-1).min(),3),"| basket 20:",round(ew.iloc[-1],1),"DD",round((ew/ew.cummax()-1).min(),3))
print("BTC close 2024-12-31",H["close"]["BTC"].loc["2024-12-31"],"2025-01-01",H["close"]["BTC"].loc["2025-01-01"],"2026-09-30",H["close"]["BTC"].loc["2026-09-30"], "max",H["close"]["BTC"].loc[dq.S0:dq.S1].max())
