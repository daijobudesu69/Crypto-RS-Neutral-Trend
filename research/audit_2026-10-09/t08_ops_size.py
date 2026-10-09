import pandas as pd, numpy as np, dq
pd.set_option("display.width",220)
H=dq.load_hl(True,"asis"); S=dq.signals(H)
days=H["close"].loc[dq.S0:dq.S1].index
base,T0,O0=dq.account(S["W"],H,dq.S0,dq.S1)
print("== T08 hari terlewat (trader tidak menjalankan strategi di hari itu; posisi dibiarkan)")
rng=np.random.default_rng(11)
for label,p in [("1 hari/bulan",1/30.4),("2-3 hari/bulan",2.5/30.4),("1 hari/minggu",1/7),("2 hari/minggu",2/7)]:
    ends=[];sh=[]
    for i in range(60):
        sk=set(days[rng.random(len(days))<p]); D,_,_=dq.account(S["W"],H,dq.S0,dq.S1,skip_days=sk); st=dq.stats(D.equity); ends.append(st["end"]); sh.append(st["sharpe"])
    print(f"lewat {label:<15}: akhir median {np.median(ends):.0f} (5%-95%: {np.percentile(ends,5):.0f}-{np.percentile(ends,95):.0f}) Sharpe median {np.median(sh):.2f} | {np.mean(np.array(ends)<522.4)*100:.0f}% lebih rendah dari dasar")
# skip weekends, liburan 7 hari, hanya rebalance tiap k hari
wk=set(d for d in days if d.dayofweek>=5); D,_,_=dq.account(S["W"],H,dq.S0,dq.S1,skip_days=wk); print("tidak pernah jalan Sabtu-Minggu ->",round(D.equity.iloc[-1],1),round(dq.stats(D.equity)["sharpe"],2))
for k in [2,3,7]:
    out=[]
    for off in range(k):
        sk=set(d for i,d in enumerate(days) if i%k!=off); D,_,_=dq.account(S["W"],H,dq.S0,dq.S1,skip_days=sk); out.append((round(D.equity.iloc[-1]),round(dq.stats(D.equity)["sharpe"],2)))
    print(f"hanya jalan tiap {k} hari (semua kemungkinan hari mulai):",out)
vac=[]
for st_ in days[::14][:-1]:
    sk=set(pd.date_range(st_,periods=7)); D,_,_=dq.account(S["W"],H,dq.S0,dq.S1,skip_days=sk); vac.append(D.equity.iloc[-1])
print("satu kali libur 7 hari berturut (45 posisi tanggal): akhir min/median/max",round(min(vac)),round(np.median(vac)),round(max(vac)))

print("\n== T11 ukuran akun")
bt=dq.weights_bt(S["W"],H,dq.S0,dq.S1); print("versi bobot ideal (tanpa minimum order, rebalance penuh tiap hari):",{k:round(v,3) for k,v in dq.rstats(bt).items()}, "-> 200 jadi",round(200*(1+bt).prod(),1))
for eq0 in [100,200,300,500,1000,2000,10000,100000]:
    D,T,O=dq.account(S["W"],H,dq.S0,dq.S1,eq0=eq0); st=dq.stats(D.equity,eq0)
    print(f"modal {eq0:>6}: x{st['end']/eq0:.3f} (setara 200 -> {200*st['end']/eq0:6.1f}) Sharpe {st['sharpe']:.2f} DD {st['mdd']*100:5.1f}% order {len(O)} fee {(-D.fees.sum())/eq0*100:.1f}% modal")
for band in [0.0,0.10,0.25,0.40,0.60]:
    D,T,O=dq.account(S["W"],H,dq.S0,dq.S1,band=band); st=dq.stats(D.equity); print(f"band {band:.2f} (modal 200): akhir {st['end']:.1f} Sharpe {st['sharpe']:.2f} order {len(O)}")
for band in [0.0,0.10,0.25,0.40,0.60]:
    D,T,O=dq.account(S["W"],H,dq.S0,dq.S1,band=band,eq0=100000,min_order=10); st=dq.stats(D.equity,100000); print(f"band {band:.2f} (modal 100rb, min order tak berpengaruh): x{st['end']/100000:.3f} Sharpe {st['sharpe']:.2f}")
# position sizes in the 200 account
tg=(S["W"].loc[dq.S0:dq.S1].mul(base.equity,axis=0)).abs(); v=tg.values[tg.values>0]
print("target posisi (USD) di akun 200: median",round(np.median(v),1),"| <5 (dibuang):",round(np.mean(v<5)*100,1),"% | 5-10 (dibulatkan ke 10):",round(np.mean((v>=5)&(v<10))*100,1),"% | 10-25:",round(np.mean((v>=10)&(v<25))*100,1),"% | >25:",round(np.mean(v>=25)*100,1),"%")
print("jumlah posisi per hari: median",int((tg>0).sum(axis=1).median()),"maks",int((tg>0).sum(axis=1).max()))
