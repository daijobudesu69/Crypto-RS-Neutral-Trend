import pandas as pd, numpy as np, dq
pd.set_option("display.width",220)
H=dq.load_hl(True,"asis"); B=dq.load_bn(False); S=dq.signals(H)
C=H["close"]; idx=C.index
bn=pd.read_parquet(dq.BASE+"/_bn_15m_hour0.parquet"); bn["t"]=pd.to_datetime(bn.ts).dt.tz_localize(None)
bn["coin"]=bn.sym.str.replace("USDT$","",regex=True).map(lambda x: dq.BN2HL.get(x,x))
bn["d"]=bn.t.dt.floor("D")-pd.Timedelta(days=1)      # candle harian yg baru saja tutup
bn["mm"]=bn.t.dt.minute
hl=pd.read_parquet(dq.BASE+"/_hl_intraday_hour0.parquet"); hl["t"]=pd.to_datetime(hl.ts).dt.tz_localize(None); hl["d"]=hl.t.dt.floor("D")-pd.Timedelta(days=1); hl["mm"]=hl.t.dt.minute
def bn_px(minute_bar, col):
    x=bn[bn.mm==minute_bar].pivot(index="d",columns="coin",values=col)
    return x.reindex(index=idx,columns=C.columns)
bnc=B["close"].reindex(index=idx,columns=C.columns)
okmap=((C/bnc-1).abs()<0.03)          # hanya pakai Binance kalau harganya memang aset yang sama
def via_bn(minute_bar,col="close"):
    ratio=bn_px(minute_bar,col)/bnc
    return (C*ratio).where(okmap & ratio.notna() & ((ratio-1).abs()<0.5))
EX={}
EX["+15 menit (Binance)"]=via_bn(0)
EX["+30 menit (Binance)"]=via_bn(15)
EX["+45 menit (Binance)"]=via_bn(30)
EX["+60 menit (Binance)"]=via_bn(45)
# rata-rata 4 harga dlm jam pertama (TWAP kasar)
EX["rata-rata jam pertama (Binance)"]=(via_bn(0)+via_bn(15)+via_bn(30)+via_bn(45))/4
h4=hl[(hl.tf=="4h")].pivot(index="d",columns="coin",values="close").reindex(index=idx,columns=C.columns)
h4o=hl[(hl.tf=="4h")].pivot(index="d",columns="coin",values="open").reindex(index=idx,columns=C.columns)
EX["+4 jam (harga HL sendiri)"]=h4.where((h4/C-1).abs()<0.8)
h1=hl[(hl.tf=="1h")].pivot(index="d",columns="coin",values="close").reindex(index=idx,columns=C.columns)
EX["+60 menit (HL 1h, hanya sejak Mar 2026)"]=h1
EX["open candle berikutnya (HL)"]=H["open"].shift(-1)
base,_,O0=dq.account(S["W"],H,dq.S0,dq.S1); print(f"{'dasar: eksekusi tepat di harga close':<46} akhir {base.equity.iloc[-1]:6.1f} Sharpe {dq.stats(base.equity)['sharpe']:.2f}")
res={}
for nm,ex in EX.items():
    D,T,O=dq.account(S["W"],H,dq.S0,dq.S1,exec_px=ex)
    cov=np.mean([np.isfinite(ex.at[d,c]) if (d in ex.index and c in ex.columns) else False for d,c in zip(O.date,O.coin)])
    covn=sum(abs(dl) for d,c,dl in zip(O.date,O.coin,O.delta) if np.isfinite(ex.at[d,c]))/O.delta.abs().sum()
    st=dq.stats(D.equity); res[nm]=st["end"]
    # average slippage per order (signed: positive = merugikan)
    sl=[np.sign(dl)*(ex.at[d,c]/C.at[d,c]-1) for d,c,dl in zip(O.date,O.coin,O.delta) if np.isfinite(ex.at[d,c])]
    wsl=sum(dl*(ex.at[d,c]/C.at[d,c]-1) for d,c,dl in zip(O.date,O.coin,O.delta) if np.isfinite(ex.at[d,c]))
    print(f"{nm:<46} akhir {st['end']:6.1f} Sharpe {st['sharpe']:.2f} DD {st['mdd']*100:5.1f}% | order tercakup {cov*100:3.0f}% (nilai {covn*100:3.0f}%) | rata2 selip/order {np.mean(sl)*1e4:+.1f} bp | total selip {wsl:+.1f} USD")
# sub-period for the HL 1h test to compare apples to apples
for nm in ["+60 menit (HL 1h, hanya sejak Mar 2026)","+60 menit (Binance)","+4 jam (harga HL sendiri)"]:
    ex=EX[nm]; D,_,_=dq.account(S["W"],H,dq.S0,dq.S1,exec_px=ex)
    a=base.equity.loc["2026-03-10":]; b=D.equity.loc["2026-03-10":]
    print(f"  sub-periode sejak 10 Mar 2026: dasar x{a.iloc[-1]/a.iloc[0]:.3f} vs {nm} x{b.iloc[-1]/b.iloc[0]:.3f}")
# 1 hari telat, 2 hari telat
for lag in [1,2,3]:
    D,_,_=dq.account(S["W"].shift(lag).fillna(0),H,dq.S0,dq.S1); st=dq.stats(D.equity); print(f"telat {lag} hari penuh -> akhir {st['end']:.1f} Sharpe {st['sharpe']:.2f} DD {st['mdd']*100:.1f}%")
# is first-15-min move predictable by signal? momentum continuation right after close
O0["slip15"]=[EX["+15 menit (Binance)"].at[d,c]/C.at[d,c]-1 if np.isfinite(EX["+15 menit (Binance)"].at[d,c]) else np.nan for d,c in zip(O0.date,O0.coin)]
O0["slip60"]=[EX["+60 menit (Binance)"].at[d,c]/C.at[d,c]-1 if np.isfinite(EX["+60 menit (Binance)"].at[d,c]) else np.nan for d,c in zip(O0.date,O0.coin)]
x=O0.dropna(subset=["slip60"]); print("order beli: harga rata2 bergerak",round(x[x.delta>0].slip15.mean()*1e4,1),"bp dlm 15 mnt,",round(x[x.delta>0].slip60.mean()*1e4,1),"bp dlm 60 mnt | order jual:",round(x[x.delta<0].slip15.mean()*1e4,1),round(x[x.delta<0].slip60.mean()*1e4,1), "| n",len(x))
