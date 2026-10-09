"""T01: backtest ulang independen vs angka penulis."""
import pandas as pd, numpy as np, time, json
import dq
t0=time.time()
H=dq.load_hl(delisted=True, ghost="asis")
print("panel", H["close"].shape, H["close"].index[0], H["close"].index[-1], round(time.time()-t0,1))
S=dq.signals(H)
D,T,O=dq.account(S["W"],H,dq.S0,dq.S1)
st=dq.stats(D.equity); print("INDEP DUET", {k:round(v,4) for k,v in st.items()}, "orders",len(O),"closed",T.exit.notna().sum())
A=pd.read_csv(dq.EDGE+"/results/oos_daily_hype.csv",index_col=0,parse_dates=True)
diff=(D.equity-A.equity)
print("author end",A.equity.iloc[-1],"indep end",D.equity.iloc[-1],"max abs diff equity",diff.abs().max(), "max rel", (diff/A.equity).abs().max())
print("trip pnl sum",T.pnl.sum(),"equity change",D.equity.iloc[-1]-200)
for nm,k in [("M1","W1"),("M2","W2")]:
    d,_,_=dq.account(S[k],H,dq.S0,dq.S1); print(nm,{k:round(v,3) for k,v in dq.stats(d.equity).items()})
D.to_csv("out_indep_daily.csv"); T.to_csv("out_indep_trips.csv",index=False); O.to_csv("out_indep_orders.csv",index=False)
# author's cached panel vs raw
import pickle
for nm,ghost,dl in [("panel_hl_1d_ext.pkl","asis",True),("panel_hl_1d.pkl","asis",False)]:
    Pc=pd.read_pickle(dq.EDGE+"/results/cache/"+nm)
    Pm=dq.load_hl(delisted=dl) if not dl else H
    c1=Pc["close"]; c2=Pm["close"].reindex(index=c1.index,columns=c1.columns)
    print(nm,"cache shape",c1.shape,"mine",Pm["close"].shape,"cols only in cache",set(c1.columns)-set(Pm["close"].columns),"only mine",set(Pm["close"].columns)-set(c1.columns),
          "max abs close diff",float((c1-c2).abs().max().max()),"nan mismatch",int((c1.isna()!=c2.isna()).sum().sum()),
          "fund diff",float((Pc["fund"]-Pm["fund"].reindex(index=c1.index,columns=c1.columns)).abs().max().max()),
          "qv diff",float((Pc["qv"]-Pm["qv"].reindex(index=c1.index,columns=c1.columns)).abs().max().max()))
