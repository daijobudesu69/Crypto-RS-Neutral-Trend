import pandas as pd, numpy as np, dq
pd.set_option("display.width",220); pd.set_option("display.max_rows",300)
H=dq.load_hl(True,"asis"); B=dq.load_bn(False); S=dq.signals(H)
D=pd.read_csv("out_indep_daily.csv",index_col=0,parse_dates=True); T=pd.read_csv("out_indep_trips.csv",parse_dates=["entry","exit"]); O=pd.read_csv("out_indep_orders.csv",parse_dates=["date"])
e=D.equity; r=e.pct_change(); r.iloc[0]=e.iloc[0]/200-1
lv=(H["close"]/B["close"].reindex(index=H["close"].index,columns=H["close"].columns)-1).loc[dq.S0:dq.S1].abs().max().sort_values(ascending=False); print("level mismatch teratas:",lv.head(4).round(3).to_dict())
print("== T05 ketergantungan tanggal akhir")
for d in ["2025-06-30","2025-12-31","2026-03-31","2026-04-30","2026-06-30","2026-07-31","2026-08-31","2026-09-30"]:
    x=e.loc[:d]; n=len(x); print(d,"ekuitas",round(x.iloc[-1],1),"CAGR",round(((x.iloc[-1]/200)**(365/n)-1)*100,1),"% Sharpe",round(dq.stats(x)["sharpe"],2))
op=T[T.exit.isna()]; print("posisi terbuka 30 Sep:",len(op),"PnL mengambang",round(op.pnl.sum(),1),"| realized saja -> ekuitas",round(e.iloc[-1]-op.pnl.sum(),1))
# 2 extra days available in data (1-2 Okt 2026)
Dx,_,_=dq.account(S["W"],H,dq.S0,"2026-10-02"); print("lanjut sampai 2 Okt 2026:",Dx.equity.tail(3).round(1).to_dict())
print("puncak ekuitas",round(e.max(),1),e.idxmax().date())
print("\n== T06 statistik")
m=(1+r).groupby(r.index.to_period("M")).prod()-1
print("bulanan:",(m*100).round(1).to_dict())
top5=m.sort_values(ascending=False).head(5); print("5 bulan terbaik:",(top5*100).round(1).to_dict(),"gabungan x",round((1+top5).prod(),3),"| 16 bulan lain x",round((1+m.drop(top5.index)).prod(),3))
print("t-stat harian",round(r.mean()/r.std()*np.sqrt(len(r)),2),"| t-stat bulanan",round(m.mean()/m.std()*np.sqrt(len(m)),2), "| skew harian",round(r.skew(),2),"kurtosis",round(r.kurt(),2))
# best days
bd=r.sort_values(ascending=False).head(8); print("hari terbaik:",{str(k.date()):round(v*100,2) for k,v in bd.items()}); print("hari terburuk:",{str(k.date()):round(v*100,2) for k,v in r.sort_values().head(5).items()})
tot=np.log1p(r).sum(); 
for k in [1,3,5,10,20]:
    rr=r.drop(r.sort_values(ascending=False).index[:k]); eq=200*(1+rr).prod(); print(f"tanpa {k} hari terbaik -> akhir {eq:.0f}")
# decompose the best day by coin
C=H["close"]; ret=C.pct_change(fill_method=None)
for day in bd.index[:3]:
    prev=C.index[C.index.get_loc(day)-1]
    # positions held over `day` = positions after rebalance at prev close: reconstruct from orders
    pos=O[O.date<=prev].groupby("coin").delta.sum()  # not exact (drift) -> use weights instead
    w=S["W"].loc[prev]; contrib=(w*ret.loc[day]).dropna(); contrib=contrib[contrib!=0].sort_values()
    bnr=B["close"].pct_change(fill_method=None).reindex(columns=contrib.index).loc[day] if day in B["close"].index else None
    print(f"\n{day.date()} return akun {r.loc[day]*100:.2f}% | BTC {ret.at[day,'BTC']*100:.1f}% | kontribusi (bobot x return), sum {contrib.sum()*100:.2f}%")
    x=pd.DataFrame({"bobot":w[contrib.index],"ret_HL":ret.loc[day][contrib.index],"ret_BN":bnr,"kontrib%":contrib*100}).round(4); print(x.to_string())
# bootstrap
rng=np.random.default_rng(7); rv=r.values; n=len(rv)
def boot(block,nb=20000):
    out=np.empty(nb); end=np.empty(nb)
    nblk=int(np.ceil(n/block))
    for i in range(nb):
        st=rng.integers(0,n,nblk); idx=(st[:,None]+np.arange(block)[None,:]).ravel()%n; x=rv[idx[:n]]
        out[i]=x.mean()/x.std()*np.sqrt(365); end[i]=200*np.prod(1+x)
    return out,end
for blk in [1,5,20,30]:
    s,en=boot(blk); print(f"bootstrap blok {blk:>2} hari: Sharpe 2.5%/50%/97.5% = {np.percentile(s,2.5):.2f}/{np.percentile(s,50):.2f}/{np.percentile(s,97.5):.2f} | P(Sharpe<=0)={np.mean(s<=0)*100:.2f}% P(Sharpe<1)={np.mean(s<1)*100:.1f}% | ekuitas akhir 5%/50%/95% = {np.percentile(en,5):.0f}/{np.percentile(en,50):.0f}/{np.percentile(en,95):.0f}")
