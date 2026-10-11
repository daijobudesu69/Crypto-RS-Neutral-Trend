# Crypto RS-Neutral & Trend (RNT)

> **Mulai di sini:** [docs/SETUP.md](docs/SETUP.md) (GitHub, Telegram, Sheets, HYPE) dan
> [research/SPEC_v1.1.md](research/SPEC_v1.1.md) (aturan strategi lengkap).
> Laporan lengkap hasil backtest + grafik: [research/PROJECT CRYPTO - RNT.md](research/PROJECT%20CRYPTO%20-%20RNT.md).

Forward test di **HYPE (Hyperliquid)**, modal **200 USDC**, sekali sehari setelah close
harian 00:00 UTC (**07:00 WIB**). Hanya butuh candle harian HYPE: **tanpa VPS, tanpa OI,
tanpa funding sebagai sinyal** (funding hanya biaya).

- **Mesin 1, RS-Neutral:** long 4–8 koin dengan kekuatan relatif *risk-adjusted* terbaik
  dan short 4–8 koin terlemah dari 20 perp paling likuid, nilai long = nilai short.
- **Mesin 2, Trend:** long-only 5 perp paling likuid, ukuran mengikuti posisi close di
  channel 20/55/100 hari.
- Tiap mesin diskala ke volatilitas 20%/tahun, gross maks 2,5×. Aturan order sama persis
  dengan backtest (minimum 10 USD, band 40%).

> [!WARNING]
> Ekspektasi jujur setelah audit (2026-10-09): median ±+25%/tahun, peluang rugi 12 bulan
> ±26–42%, DD sampai −35–40%, masa datar bisa hampir 2 tahun. Backtest OOS v1.1
> (Jan 2025 → Sep 2026): 200 → 440 USD, tetapi tidak lagi murni out-of-sample. Alpha mesin 1
> pro-siklus (untung terutama saat BTC naik) dan profit terkonsentrasi di sedikit posisi.
> Lihat [research/audit_response/AUDIT_RESPONSE.md](research/audit_response/AUDIT_RESPONSE.md).

## Cara kerja

```
GitHub Actions (bot.yml)  cron -> watcher hidup ~5,5 jam, siklus tiap 10 menit
  └─ run_cycle.py
       └─ job harian: sekali per hari UTC (>= 00:02 UTC = 07:02 WIB)
            candle 1d semua perp HYPE (450 hari) -> target bobot (state/view.json)
            -> buku paper "paper" (v1.1) + "rf" (bayangan filter rezim, tidak diadopsi)
            -> alarm (DD 20/25% + CUSUM) -> [live: subaccount HYPE, kalau mode live/manage/flatten]
            -> Telegram (outbox) + log CSV di state/ (+ cermin Google Sheets)
  └─ tools/save_state.sh  commit state/ ke repo
watchdog.yml   alarm + nyalakan watcher baru kalau state tidak diperbarui > 90 menit
control.yml    ganti mode: gh workflow run control.yml -f mode=live
canary.yml     uji jalur order live (long + short ±10 USDC) sebelum live
smoke.yml      cek Telegram, Sheets, kunci API wallet (hanya baca), data HYPE
ci.yml         tes offline (gerbang) + cek konektivitas harian
```

| Mode (`control/bot.yaml`) | Paper | Live |
|---|---|---|
| `paper` (default) | ✅ | — |
| `live` | ✅ | buka, tambah, kurangi, tutup, balik arah |
| `manage` | ✅ | hanya kurangi / tutup |
| `flatten` | ✅ | tutup semua posisi milik RNT |
| `off` | — | — |

**Alarm** (pengganti "stop di DD 35%", dihitung dari ekuitas live kalau live aktif, selain itu paper):

| Level | Pemicu | Tindakan bot |
|---|---|---|
| 🟡 kuning | DD > 20% atau CUSUM > 0,45 | ukuran live × 0,5 |
| 🔴 merah | DD > 25% | live hanya mengurangi/menutup posisi; keputusan berhenti di user |
| 🛠 teknis | return live − paper bulan lalu > 3 poin | Telegram: cari masalah eksekusi |

Reset: `gh workflow run control.yml -f reset_breaker=true`.

## Perintah

```bash
python run_status.py
```

Target bobot hari ini + rencana order buku paper, tanpa mengubah state (±6–7 menit).

```bash
python -m pytest -q tests --ignore=tests/test_connectivity.py
```

```bash
python tools/parity_check.py
```

Hanya di PC dengan data lake: bot vs kode riset di data nyata (bobot identik, akun OOS = 440,45 USD).

```bash
python run_cycle.py
```

Satu siklus penuh (dipakai watcher). Tanpa secret Telegram, pesan dicetak ke layar.

## Struktur

| Path | Isi |
|---|---|
| `config.yaml` | parameter strategi (= SPEC v1.1), aturan order, biaya, alarm, alamat live |
| `control/bot.yaml` | mode bot, dibaca tiap siklus |
| `rntbot/strategy.py` | strategi murni (port riset, dibuktikan identik) |
| `rntbot/plan.py`, `rntbot/book.py` | aturan order (sama untuk paper dan live) dan buku paper long/short |
| `rntbot/live.py` | eksekusi live via SDK resmi HYPE (cross, reduce-only, cloid "RNT") |
| `rntbot/alarms.py` | DD, CUSUM, cek teknis bulanan |
| `rntbot/jobs.py` | job harian |
| `rntbot/hype.py`, `notify.py`, `sheets.py`, `store.py`, `control.py`, `canary.py` | data HYPE, Telegram, Sheets, state, mode, canary |
| `run_cycle.py`, `run_status.py`, `run_watchdog.py`, `run_canary.py` | entry point |
| `tools/` | simpan/sinkron state, kontrol, `check_live.py`, `smoke_test.py`, `parity_check.py` |
| `tests/` | tes offline, termasuk paritas bobot dan akun dengan kode riset |
| `state/` | log dan state forward test ([state/README.md](state/README.md)) |
| `research/` | riset asal, laporan, audit, dan respons audit ([research/README.md](research/README.md)) |
