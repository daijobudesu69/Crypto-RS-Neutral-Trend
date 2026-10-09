import pandas as pd, numpy as np, dq, itertools
pd.set_option("display.width",220)
H=dq.load_hl(True,"asis"); S=dq.signals(H); B=dq.load_bn(False); BX=dq.load_bn(True)
D=pd.read_csv("out_indep_daily.csv",index_col=0,parse_dates=True); e=D.equity; r=e.pct_change(); r.iloc[0]=e.iloc[0]/200-1
W=S["W"].loc[dq.S0:dq.S1]
sh=W.clip(upper=0).abs().sum(axis=1); lg=W.clip(lower=0).sum(axis=1)
print("== T13 eksposur & stress")
print("eksposur short (x ekuitas): rata2",round(sh.mean(),2),"median",round(sh.median(),2),"maks",round(sh.max(),2),"| long: rata2",round(lg.mean(),2),"maks",round(lg.max(),2))
print("posisi tunggal terbesar (x ekuitas): rata2",round(W.abs().max(axis=1).mean(),3),"maks",round(W.abs().max().max(),3),"| short tunggal terbesar",round(W.clip(upper=0).abs().max().max(),3))
for shock in [0.3,0.5,1.0]:
    print(f"semua short naik {shock*100:.0f}% (long diam): rugi {sh.mean()*shock*100:.0f}% ekuitas pada eksposur rata2, {sh.max()*shock*100:.0f}% pada eksposur maks | satu koin short naik {shock*100:.0f}%: rugi {W.clip(upper=0).abs().max(axis=1).mean()*shock*100:.1f}% (rata2) s/d {W.clip(upper=0).abs().max().max()*shock*100:.1f}% (maks)")
# worst realised
for nm,x in [("OOS akun",r)]:
    print(nm,"hari terburuk",round(x.min()*100,2),"% | 3 hari terburuk",round(((1+x).rolling(3).apply(np.prod,raw=True)-1).min()*100,2),"% | 7 hari",round(((1+x).rolling(7).apply(np.prod,raw=True)-1).min()*100,2),"% | 30 hari",round(((1+x).rolling(30).apply(np.prod,raw=True)-1).min()*100,2),"%")
SX=dq.signals(BX); DX,TX,OX=dq.account(SX["W"],BX,"2020-07-01","2024-12-31"); rx=DX.equity.pct_change().fillna(0)
print("IS (+koin mati) hari terburuk",round(rx.min()*100,2),"%",rx.idxmin().date(),"| 3 hari",round(((1+rx).rolling(3).apply(np.prod,raw=True)-1).min()*100,2),"% | 7 hari",round(((1+rx).rolling(7).apply(np.prod,raw=True)-1).min()*100,2),"% | 30 hari",round(((1+rx).rolling(30).apply(np.prod,raw=True)-1).min()*100,2),"%")
# intraday wick risk on shorts in OOS: max high vs entry close
T=pd.read_csv("out_indep_trips.csv",parse_dates=["entry","exit"])
# regime analysis: Mesin 1 (bobot, Binance hidup 2020-07..2026-09 utk kontinuitas) menurut kondisi pasar
SB=dq.signals(B); m1=dq.weights_bt(SB["W1"],B,"2020-07-01",dq.S1); m2=dq.weights_bt(SB["W2"],B,"2020-07-01",dq.S1); du=dq.weights_bt(SB["W"],B,"2020-07-01",dq.S1)
C=B["close"]; btc=C["BTC"]; R=C.pct_change(fill_method=None)
trend=(btc/btc.shift(90)-1).shift(1)      # diketahui sehari sebelumnya
U=SB["U20"]; disp=(C/C.shift(28)-1).where(U).std(axis=1).shift(1)
ew=R.where(U.shift(1)).mean(axis=1)
df=pd.DataFrame({"m1":m1,"m2":m2,"duet":du,"trend":trend,"disp":disp,"ew":ew}).dropna()
def sr(x): return x.mean()/x.std()*np.sqrt(365) if len(x)>30 else np.nan
print("\nMesin 1 / Mesin 2 / DUET (bobot, Binance, Jul 2020-Sep 2026) menurut kondisi pasar yang sudah diketahui sehari sebelumnya:")
dm=df.disp.median()
for nm,mask in [("BTC naik 90h",df.trend>0),("BTC turun 90h",df.trend<=0),("dispersi tinggi",df.disp>dm),("dispersi rendah",df.disp<=dm),
                ("BTC turun & dispersi tinggi",(df.trend<=0)&(df.disp>dm)),("BTC turun & dispersi rendah",(df.trend<=0)&(df.disp<=dm)),("BTC naik & dispersi tinggi",(df.trend>0)&(df.disp>dm)),("BTC naik & dispersi rendah",(df.trend>0)&(df.disp<=dm))]:
    x=df[mask]; print(f"  {nm:<30} {len(x):>4} hari ({len(x)/len(df)*100:2.0f}%) | Sharpe M1 {sr(x.m1):5.2f}  M2 {sr(x.m2):5.2f}  DUET {sr(x.duet):5.2f} | return tahunan M1 {x.m1.mean()*365*100:5.1f}%")
o=df.loc[dq.S0:]; i=df.loc[:"2024-12-31"]
print("  porsi hari 'BTC turun 90h': IS",round((i.trend<=0).mean()*100),"% vs OOS",round((o.trend<=0).mean()*100),"% | dispersi rata2: IS",round(i.disp.mean(),3),"OOS",round(o.disp.mean(),3))
# momentum crash: setelah basket naik tajam
for th in [0.08,0.12]:
    ev=df.index[df.ew>th]; nxt=[df.m1.iloc[df.index.get_loc(d):df.index.get_loc(d)+1].sum() for d in ev]
    print(f"  hari basket alt naik > {th*100:.0f}%: {len(ev)} hari, rata2 return Mesin 1 hari itu {np.mean(nxt)*100:.2f}% (terburuk {np.min(nxt)*100:.1f}%)")
# per-year M1 on Binance alive
print("  Mesin 1 per tahun (bobot, Binance hidup):",((1+df.m1).groupby(df.index.year).prod()-1).mul(100).round(0).to_dict())
print("  Mesin 2 per tahun:",((1+df.m2).groupby(df.index.year).prod()-1).mul(100).round(0).to_dict())

print("\n== T14 aturan berhenti DD 35%")
ri=pd.read_csv("out_is_equity.csv",index_col=0,parse_dates=True)["mati"].pct_change().dropna()
pool=pd.concat([ri,r]); v=pool.values; sd=v.std()
rng=np.random.default_rng(3)
def sim(target_sharpe,days,nb=4000,block=20):
    x0=v-v.mean()+target_sharpe*sd/np.sqrt(365)
    n=len(x0); nblk=int(np.ceil(days/block)); hit=0; mdds=[]; tt=[]; fin=[]
    for _ in range(nb):
        st=rng.integers(0,n,nblk); idx=(st[:,None]+np.arange(block)[None,:]).ravel()%n; x=x0[idx[:days]]
        eq=np.cumprod(1+x); dd=eq/np.maximum.accumulate(np.maximum(eq,1.0))-1; mdds.append(dd.min()); fin.append(eq[-1])
        h=np.nonzero(dd<=-0.35)[0]
        if len(h): hit+=1; tt.append(h[0])
    return hit/nb, np.median(mdds), np.percentile(mdds,5), (np.median(tt) if tt else np.nan), np.median(fin), np.mean(np.array(fin)<1)
print("vol harian tahunan (gabungan IS+OOS):",round(sd*np.sqrt(365)*100,1),"%")
for sh_ in [2.0,1.0,0.5,0.0,-0.5]:
    for days in [365,730]:
        p,md,m5,tt,fin,pl=sim(sh_,days)
        print(f"edge sebenarnya Sharpe {sh_:4.1f}, {days//365} th: P(kena stop DD35%)={p*100:5.1f}% | DD maks median {md*100:5.1f}% (5% terburuk {m5*100:5.1f}%) | ekuitas median x{fin:.2f} | P(rugi)={pl*100:4.1f}%" + (f" | median hari sampai stop {tt:.0f}" if p>0.02 else ""))
