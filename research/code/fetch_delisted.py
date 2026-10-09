"""Survivorship check data (read-only public endpoints), saved under Crypto-RS-Neutral & Trend/data.
1) HYPE: 1d candles + funding of perps that are DELISTED today (listed in the snapshot's isDelisted).
2) Binance UM: 1d klines of perps that exist in the data.binance.vision archive but are no longer trading."""
import os, sys, io, zipfile, glob
import pandas as pd
sys.path.insert(0, r"C:\Crypto data\backtest data and more\scripts")
import hyperliquid_download as HD
import bv_list as BV

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
LAKE = r"C:\Crypto data\backtest data and more\data"


def hype_delisted():
    snap = pd.read_parquet(glob.glob(os.path.join(LAKE, "hyperliquid", "snapshots", "*"))[0])
    dl = snap[snap["isDelisted"].fillna(False).astype(bool)]["name"].tolist()
    os.makedirs(os.path.join(OUT, "hl_delisted", "1d"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "hl_delisted", "funding"), exist_ok=True)
    got = []
    for c in dl:
        p = os.path.join(OUT, "hl_delisted", "1d", f"{c}.parquet")
        if os.path.exists(p):
            got.append(c); continue
        df = HD.candles(c, "1d", start_ms=int(pd.Timestamp("2023-01-01", tz="UTC").value // 10**6))
        if df is None or len(df) == 0:
            print("no candles", c); continue
        df.to_parquet(p, index=False)
        print(c, len(df), str(df.ts.min())[:10], str(df.ts.max())[:10], flush=True)
        got.append(c)
    return got


def hype_funding(coins):
    """funding (cost only) for the delisted coins that actually enter the universe."""
    for c in coins:
        fp = os.path.join(OUT, "hl_delisted", "funding", f"{c}.parquet")
        if os.path.exists(fp):
            continue
        rows, start = [], int(pd.Timestamp("2024-06-01", tz="UTC").value // 10**6)
        while True:
            raw = HD.post({"type": "fundingHistory", "coin": c, "startTime": start}, per_items=20)
            if not raw:
                break
            rows += raw
            nxt = raw[-1]["time"] + 1
            if len(raw) < 500 or nxt <= start:
                break
            start = nxt
        if rows:
            f = pd.DataFrame(rows)
            pd.DataFrame({"ts": pd.to_datetime(f["time"], unit="ms", utc=True).dt.floor("h"),
                          "funding_rate": f["fundingRate"].astype(float)}).to_parquet(
                os.path.join(OUT, "hl_delisted", "funding", f"{c}.parquet"), index=False)
        print("funding", c, len(rows), flush=True)


def binance_delisted():
    alive = {os.path.basename(f)[:-8] for f in glob.glob(os.path.join(LAKE, "binance", "um", "klines", "1d", "*.parquet"))}
    excl = set(pd.read_csv(os.path.join(LAKE, "universe", "excluded_tradfi_pegged.csv"))["symbol"])
    allsym = BV.symbols("futures/um", "monthly", "klines")
    cand = [s for s in allsym if s.endswith("USDT") and s not in alive and s not in excl
            and not any(x in s for x in ["USDC", "BUSD", "TUSD", "FDUSD", "USDP", "_"])]
    print(len(allsym), "archive symbols;", len(cand), "not alive candidates", flush=True)
    os.makedirs(os.path.join(OUT, "bn_dead", "1d"), exist_ok=True)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(_one_bn, cand))


def _one_bn(s):
    p = os.path.join(OUT, "bn_dead", "1d", f"{s}.parquet")
    if os.path.exists(p):
        return
    try:
        _, keys = BV._list(f"data/futures/um/monthly/klines/{s}/1d/")
        frames = []
        for k, sz in keys:
            if not k.endswith(".zip"):
                continue
            r = BV.get("https://data.binance.vision/" + k)
            if r.status_code != 200:
                continue
            z = zipfile.ZipFile(io.BytesIO(r.content))
            raw = z.read(z.namelist()[0]).decode()
            lines = [l for l in raw.splitlines() if l and l[0].isdigit()]
            if lines:
                frames.append(pd.read_csv(io.StringIO(chr(10).join(lines)), header=None).iloc[:, :8])
        if not frames:
            return
        d = pd.concat(frames)
        df = pd.DataFrame({"ts": pd.to_datetime(d[0], unit="ms", utc=True), "open": d[1].astype(float),
                           "high": d[2].astype(float), "low": d[3].astype(float), "close": d[4].astype(float),
                           "volume": d[5].astype(float), "quote_volume": d[7].astype(float)})
        df = df.drop_duplicates("ts").sort_values("ts")
        df.to_parquet(p, index=False)
        print(s, len(df), str(df.ts.min())[:10], str(df.ts.max())[:10], flush=True)
    except Exception as e:
        print("ERR", s, e, flush=True)


if __name__ == "__main__":
    which = sys.argv[1]
    if which == "hl":
        hype_delisted()
    elif which == "hlf":
        hype_funding(sys.argv[2].split(","))
    else:
        binance_delisted()
