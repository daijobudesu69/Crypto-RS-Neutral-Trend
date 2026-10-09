import pandas as pd, numpy as np, dq
pd.set_option("display.width",220)
IS0,IS1="2020-07-01","2024-12-31"
B=dq.load_bn(False); BX=dq.load_bn(True)
print("panel hidup",B["close"].shape,"| + mati/kecil",BX["close"].shape)
for nm,P in [("koin hidup saja",B),("+ koin mati/kecil",BX)]:
    S=dq.signals(P); D,T,O=dq.account(S["W"],P,IS0,IS1); st=dq.stats(D.equity)
    e=D.equity; yr=(e.groupby(e.index.year).last()/e.groupby(e.index.year).last().shift(1).fillna(200)-1)
    print(f"{nm:<20} akhir {st['end']:7.0f} Sharpe {st['sharpe']:.2f} DD {st['mdd']*100:.1f}% | per tahun {(yr*100).round(0).to_dict()}")
    if P is BX:
        dead=P["is_dead"].fillna(False).astype(bool); W=S["W"].loc[IS0:IS1]
        g=W.abs().sum(axis=1); gd=W.loc[:,dead[W.columns].values].abs().sum(axis=1)
        print("   porsi eksposur di koin tanpa data funding: rata2",round((gd/g.replace(0,np.nan)).mean()*100,1),"% | short saja:",round((W.loc[:,dead[W.columns].values].clip(upper=0).abs().sum(axis=1)/W.clip(upper=0).abs().sum(axis=1).replace(0,np.nan)).mean()*100,1),"%")
        Td=T[T.coin.map(dead)]; print("   posisi di koin mati/kecil:",len(Td),"dari",len(T),"| PnL",round(Td.pnl.sum()),"dari",round(T.pnl.sum()), "| short:",round(Td[Td.side<0].pnl.sum()),"long:",round(Td[Td.side>0].pnl.sum()))
        print("   5 posisi terburuk:"); print(T.sort_values("pnl").head(5).round(1).to_string())
        print("   funding rata2 koin hidup yg dibayar (per tahun, % ekuitas):",round(D.pnl_funding.sum()/D.equity.mean()/4.5*100,2))
        for x in [0.0005,0.001,0.003,0.005]:
            ac=pd.DataFrame(0.0,index=P["close"].index,columns=P["close"].columns); ac.loc[:,dead[ac.columns].values]=x
            D2,_,_=dq.account(S["W"],P,IS0,IS1,abs_cost=ac); s2=dq.stats(D2.equity); print(f"   penalti funding {x*100:.2f}%/hari utk setiap posisi di koin mati -> akhir {s2['end']:7.0f} Sharpe {s2['sharpe']:.2f} DD {s2['mdd']*100:.1f}%")
        # underwater & slow period claims
        m=e.resample("ME").last(); print("   ekuitas akhir Apr 2021:",round(m.loc["2021-04"].iloc[0]),"| akhir Okt 2023:",round(m.loc["2023-10"].iloc[0]),"-> x",round(m.loc["2023-10"].iloc[0]/m.loc["2021-04"].iloc[0],3))
        dd=e/e.cummax()-1; import itertools; print("   underwater terlama:",max(len(list(g_)) for k_,g_ in itertools.groupby(dd<0) if k_),"hari")
    else:
        e0=e
        m=e.resample("ME").last(); print("   (hidup) Apr 2021 -> Okt 2023 x",round(m.loc["2023-10"].iloc[0]/m.loc["2021-04"].iloc[0],3))
        dd=e/e.cummax()-1; import itertools; print("   underwater terlama:",max(len(list(g_)) for k_,g_ in itertools.groupby(dd<0) if k_),"hari")
