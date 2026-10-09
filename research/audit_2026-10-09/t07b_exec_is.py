import pandas as pd, numpy as np, dq
B=dq.load_bn(False); S=dq.signals(B); C=B["close"]; idx=C.index
bn=pd.read_parquet(dq.BASE+"/_bn_15m_hour0.parquet"); bn["t"]=pd.to_datetime(bn.ts).dt.tz_localize(None)
bn["coin"]=bn.sym.str.replace("USDT$","",regex=True).map(lambda x: dq.BN2HL.get(x,x)); bn["d"]=bn.t.dt.floor("D")-pd.Timedelta(days=1); bn["mm"]=bn.t.dt.minute
def px(m): 
    x=bn[bn.mm==m].pivot(index="d",columns="coin",values="close").reindex(index=idx,columns=C.columns); return x.where((x/C-1).abs()<0.5)
for a,b,lab in [("2020-07-01","2024-12-31","IS Binance 2020-24"),(dq.S0,dq.S1,"OOS Binance 2025-26")]:
    D,_,_=dq.account(S["W"],B,a,b); s0=dq.stats(D.equity); print(f"{lab}: dasar akhir {s0['end']:.0f} Sharpe {s0['sharpe']:.2f}")
    for m,nm in [(0,"+15 mnt"),(15,"+30 mnt"),(45,"+60 mnt")]:
        D,_,O=dq.account(S["W"],B,a,b,exec_px=px(m)); s=dq.stats(D.equity); print(f"   {nm}: akhir {s['end']:.0f} ({(s['end']/s0['end']-1)*100:+.1f}%) Sharpe {s['sharpe']:.2f}")
    for lag in [1,2]:
        D,_,_=dq.account(S["W"].shift(lag).fillna(0),B,a,b); s=dq.stats(D.equity); print(f"   telat {lag} hari: akhir {s['end']:.0f} ({(s['end']/s0['end']-1)*100:+.1f}%) Sharpe {s['sharpe']:.2f}")
