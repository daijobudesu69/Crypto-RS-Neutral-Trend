import pandas as pd, numpy as np, dq
H=dq.load_hl(True,"asis"); BX=dq.load_bn(True); B=dq.load_bn(False)
def sr(x): return x.mean()/x.std()*np.sqrt(365) if len(x)>40 else np.nan
def table(P,a,b,label,btcP=None):
    S=dq.signals(P); m1=dq.weights_bt(S["W1"],P,a,b); m2=dq.weights_bt(S["W2"],P,a,b); du=dq.weights_bt(S["W"],P,a,b)
    R=P["close"].pct_change(fill_method=None).fillna(0)
    l=dq.weights_bt(S["W1"].clip(lower=0),P,a,b); s=dq.weights_bt(S["W1"].clip(upper=0),P,a,b)
    btc=(btcP or P)["close"]["BTC"]; C=P["close"]
    tr=(btc/btc.shift(90)-1).shift(1); tr30=(btc/btc.shift(30)-1).shift(1)
    ma=(btc/btc.rolling(200).mean()-1).shift(1)
    disp=(C/C.shift(28)-1).where(S["U20"]).std(axis=1).shift(1)
    df=pd.DataFrame({"m1":m1,"m2":m2,"du":du,"l":l,"s":s,"tr":tr.reindex(m1.index),"tr30":tr30.reindex(m1.index),"ma":ma.reindex(m1.index),"disp":disp.reindex(m1.index)}).dropna()
    print(f"\n{label}: {len(df)} hari | Sharpe M1 {sr(df.m1):.2f} (long {sr(df.l):.2f}, short {sr(df.s):.2f}) M2 {sr(df.m2):.2f} DUET {sr(df.du):.2f}")
    for nm,mk in [("BTC 90h naik",df.tr>0),("BTC 90h turun",df.tr<=0),("BTC di atas MA200",df.ma>0),("BTC di bawah MA200",df.ma<=0),("BTC 30h naik",df.tr30>0),("BTC 30h turun",df.tr30<=0)]:
        x=df[mk]; print(f"   {nm:<20} {len(x):>4} hari ({len(x)/len(df)*100:3.0f}%) | M1 Sharpe {sr(x.m1):5.2f} return/th {x.m1.mean()*36500:6.1f}% (long {x.l.mean()*36500:6.1f}%, short {x.s.mean()*36500:6.1f}%) | M2 Sharpe {sr(x.m2):5.2f} | DUET Sharpe {sr(x.du):5.2f} return/th {x.du.mean()*36500:6.1f}%")
    return df
table(BX,"2020-07-01","2024-12-31","IS Binance + koin mati (2020-07..2024-12)")
table(B,"2020-07-01","2024-12-31","IS Binance koin hidup saja")
table(H,dq.S0,dq.S1,"OOS HL (2025-01..2026-09)",btcP=B)
table(B,dq.S0,dq.S1,"OOS Binance")
# per year IS with dead
S=dq.signals(BX); m1=dq.weights_bt(S["W1"],BX,"2020-07-01","2024-12-31"); print("\nM1 per tahun (bobot, +mati):",((1+m1).groupby(m1.index.year).prod()-1).mul(100).round(0).to_dict())
btc=BX["close"]["BTC"]; print("BTC per tahun:",(btc.groupby(btc.index.year).last()/btc.groupby(btc.index.year).first()-1).mul(100).round(0).to_dict())
