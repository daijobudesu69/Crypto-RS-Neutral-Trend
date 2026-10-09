import pandas as pd, numpy as np, dq
H=dq.load_hl(True,"asis"); B=dq.load_bn(False); C=H["close"]; idx=C.index
bn=pd.read_parquet(dq.BASE+"/_bn_15m_hour0.parquet"); bn["t"]=pd.to_datetime(bn.ts).dt.tz_localize(None)
bn["coin"]=bn.sym.str.replace("USDT$","",regex=True).map(lambda x: dq.BN2HL.get(x,x)); bn["d"]=bn.t.dt.floor("D")-pd.Timedelta(days=1); bn["mm"]=bn.t.dt.minute
bnc=B["close"].reindex(index=idx,columns=C.columns); ok=((C/bnc-1).abs()<0.03)
ratio=bn[bn.mm==15].pivot(index="d",columns="coin",values="close").reindex(index=idx,columns=C.columns)/bnc
EX30=(C*ratio).where(ok&ratio.notna()&((ratio-1).abs()<0.5))
def go(label,spec,ex=None,eq0=200,excl=()):
    S=dq.signals(H,spec,exclude=excl); D,T,O=dq.account(S["W"],H,dq.S0,dq.S1,exec_px=ex,eq0=eq0); st=dq.stats(D.equity,eq0); e=D.equity*200/eq0
    op=T[T.exit.isna()].pnl.sum()*200/eq0
    print(f"{label:<66} akhir {e.iloc[-1]:6.1f} | per 31 Jul 2026 {e.loc['2026-07-31']:6.1f} | Sharpe {st['sharpe']:.2f} | DD {st['mdd']*100:5.1f}% | CAGR {st['cagr']*100:4.0f}% | mengambang {op:5.1f}")
    return D
go("1. persis laporan",{})
go("2. + eksekusi 30 menit setelah close",{},EX30)
go("3. + umur 200 hari dari candle nyata",{"hist_mode":"real"},EX30)
go("4. = (3) dgn modal besar (tanpa efek pembulatan order minimum)",{"hist_mode":"real"},EX30,eq0=100000)
go("5. = (3) + persentil di dalam top-20",{"hist_mode":"real","pct_scope":"universe"},EX30)
go("6. = (3) tanpa ZEC",{"hist_mode":"real"},EX30,excl=("ZEC",))
go("7. = (3) tanpa ZEC & BERA",{"hist_mode":"real"},EX30,excl=("ZEC","BERA"))
D=go("8. = (3) biaya 2x (0,15%/sisi)",{"hist_mode":"real"},EX30)
S=dq.signals(H,{"hist_mode":"real"}); D,_,_=dq.account(S["W"],H,dq.S0,dq.S1,exec_px=EX30,cost=0.0015); print("   biaya 2x:",round(D.equity.iloc[-1],1),round(dq.stats(D.equity)["sharpe"],2))
for k,nm in [("W1","Mesin 1 saja"),("W2","Mesin 2 saja")]:
    D,_,_=dq.account(S[k],H,dq.S0,dq.S1,exec_px=EX30); print("   (3)",nm,round(D.equity.iloc[-1],1),round(dq.stats(D.equity)["sharpe"],2),round(dq.stats(D.equity)["mdd"]*100,1))
D,_,_=dq.account(S["W"],H,dq.S0,dq.S1,exec_px=EX30); D.to_csv("out_konservatif_daily.csv")
e=D.equity; r=e.pct_change().fillna(e.iloc[0]/200-1); m=(1+r).groupby(r.index.to_period("M")).prod()-1; print("   (3) bulanan:",(m*100).round(1).to_dict())
print("   (3) 2025:",round((e.loc['2025'].iloc[-1]/200-1)*100,1),"% 2026:",round((e.iloc[-1]/e.loc['2025'].iloc[-1]-1)*100,1),"% | t-stat",round(dq.stats(e)["t"],2))
