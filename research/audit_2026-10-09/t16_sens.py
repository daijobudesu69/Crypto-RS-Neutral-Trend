import pandas as pd, numpy as np, dq, itertools
pd.set_option("display.width",220)
H=dq.load_hl(True,"asis"); B=dq.load_bn(False)
IS0,IS1="2020-07-01","2024-12-31"
def run(P,spec,a,b,eng="W"):
    S=dq.signals(P,spec); D,_,O=dq.account(S[eng],P,a,b); st=dq.stats(D.equity); return st["end"],st["sharpe"],st["mdd"]
def both(label,spec):
    i=run(B,spec,IS0,IS1); o=run(H,spec,dq.S0,dq.S1); ob=run(B,spec,dq.S0,dq.S1)
    print(f"{label:<44} IS(Binance) akhir {i[0]:7.0f} Sharpe {i[1]:.2f} DD {i[2]*100:5.1f}% | OOS(HL) akhir {o[0]:5.0f} Sharpe {o[1]:.2f} DD {o[2]*100:5.1f}% | OOS(Binance) {ob[0]:5.0f} {ob[1]:.2f}")
    return i,o,ob
print("== dasar & ambiguitas spesifikasi")
both("dasar (spesifikasi beku)",{})
both("persentil dihitung di dalam top-20 saja",{"pct_scope":"universe"})
both("persentil antar koin yg lolos umur",{"pct_scope":"eligible"})
both("channel pakai high/low (Donchian klasik)",{"channel":"hl"})
print("\n== 14 tetangga parameter dari laporan + IS-nya")
var=[("buffer 3/7",{"rs_in":3,"rs_out":7}),("buffer 5/9",{"rs_in":5,"rs_out":9}),("buffer 4/6",{"rs_in":4,"rs_out":6}),("buffer 4/10",{"rs_in":4,"rs_out":10}),
     ("lookback 14/28",{"rs_L":(14,28)}),("lookback 7/14/28",{"rs_L":(7,14,28)}),("lookback 28/56",{"rs_L":(28,56)}),("RS top-15",{"rs_top":15}),("RS top-30",{"rs_top":30}),
     ("trend top-3",{"tr_top":3}),("trend top-8",{"tr_top":8}),("vol mesin 15%",{"sleeve_vol":0.15}),("vol mesin 25%",{"sleeve_vol":0.25})]
rows=[]
for nm,sp in var:
    i,o,ob=both(nm,sp); rows.append((nm,i[1],o[1],ob[1],o[0]))
print("\n== Mesin 1 saja, satu lookback (apakah mulus antar lookback?)")
for L in [3,5,7,10,14,21,28,35,42,56,70,90]:
    sp={"rs_L":(L,)}
    i=run(B,sp,IS0,IS1,"W1"); o=run(H,sp,dq.S0,dq.S1,"W1"); ob=run(B,sp,dq.S0,dq.S1,"W1")
    print(f"L={L:>2}: IS Sharpe {i[1]:5.2f} | OOS HL Sharpe {o[1]:5.2f} akhir {o[0]:4.0f} | OOS Binance Sharpe {ob[1]:5.2f}")
print("\n== Mesin 1 saja, grid lebih luas (48 kombinasi): sebaran hasil OOS HL")
res=[]
for Ls in [(7,14,28,56),(14,28),(7,14,28),(14,28,42),(10,20,40,80),(21,42)]:
    for top in [15,20,30]:
        for (a,b) in [(3,6),(4,8),(5,10),(6,12)] if top>=20 else [(3,6),(4,8)]:
            sp={"rs_L":Ls,"rs_top":top,"rs_in":a,"rs_out":b}
            i=run(B,sp,IS0,IS1,"W1"); o=run(H,sp,dq.S0,dq.S1,"W1"); res.append((Ls,top,a,b,i[1],o[1],o[0]))
R=pd.DataFrame(res,columns=["Ls","top","in","out","is_sh","oos_sh","oos_end"])
print("n",len(R),"| OOS Sharpe min/25%/median/75%/max:",R.oos_sh.quantile([0,.25,.5,.75,1]).round(2).tolist(),"| IS Sharpe median",round(R.is_sh.median(),2),"| OOS akhir median",round(R.oos_end.median()),"| korelasi IS vs OOS Sharpe",round(R.is_sh.corr(R.oos_sh),2),"| share OOS>IS",round((R.oos_sh>R.is_sh).mean(),2))
b=R[(R.Ls==(7,14,28,56))&(R.top==20)&(R["in"]==4)]; print("dasar:",b.round(2).to_string(index=False)); print("peringkat dasar di OOS:",int((R.oos_sh>b.oos_sh.iloc[0]).sum())+1,"dari",len(R))
R.to_csv("out_grid_m1.csv",index=False)
