import pandas as pd, numpy as np, dq, itertools
IS0,IS1="2020-07-01","2024-12-31"
B=dq.load_bn(False); BX=dq.load_bn(True)
out={}
for nm,P in [("hidup",B),("mati",BX)]:
    S=dq.signals(P); D,T,O=dq.account(S["W"],P,IS0,IS1); e=D.equity; out[nm]=e
    m=e.resample("ME").last()
    print(nm,"akhir bulan: Apr21",round(m.loc["2021-04"].iloc[0]),"Mei21",round(m.loc["2021-05"].iloc[0]),"Okt23",round(m.loc["2023-10"].iloc[0]),"| Mei21->Okt23 x",round(m.loc["2023-10"].iloc[0]/m.loc["2021-05"].iloc[0],3))
    dd=e/e.cummax()-1
    # longest underwater spell with dates
    best=(0,None,None); cur=0; st=None
    for d,v in dd.items():
        if v<0:
            if cur==0: st=d
            cur+=1
            if cur>best[0]: best=(cur,st,d)
        else: cur=0
    print("   underwater terlama",best[0],"hari:",best[1].date(),"->",best[2].date(),"| DD maks",round(dd.min()*100,1),"% pada",dd.idxmin().date())
    sp=sorted([(len(list(g)),) for k,g in itertools.groupby(dd<0) if k],reverse=True)[:4]; print("   4 periode underwater terpanjang (hari):",[x[0] for x in sp])
    r=dq.weights_bt(S["W"],P,IS0,IS1); eq=(1+r).cumprod(); d2=eq/eq.cummax()-1
    print("   versi bobot: underwater terlama",max(len(list(g)) for k,g in itertools.groupby(d2<0) if k),"hari | Mei21->Okt23 x",round(eq.resample('ME').last().loc['2023-10'].iloc[0]/eq.resample('ME').last().loc['2021-05'].iloc[0],3))
pd.DataFrame(out).to_csv("out_is_equity.csv")
