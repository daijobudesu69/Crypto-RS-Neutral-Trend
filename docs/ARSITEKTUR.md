# Arsitektur, koneksi, dan akses RNT

Peta satu halaman. Sumbernya kode dan workflow di repo ini (rujukan `file:baris` ada di tiap
tabel). Untuk langkah pasang bot lihat [SETUP.md](SETUP.md); isi tiap file `state/` ada di
[state/README.md](../state/README.md). Halaman ini tidak berisi secret, hanya NAMA secret.

## Alur satu siklus

`bot.yml` (watcher ±5,5 jam, menyalakan penggantinya sendiri, cron + `watchdog.yml` sebagai
cadangan) memanggil `run_cycle.py` tiap ~10 menit:

1. baca `control/bot.yaml` (mode)
2. kalau hari UTC baru dan belum diproses (>= 00:02 UTC): job harian di `rntbot/jobs.py`
   (buku paper + alarm + live jika mode live/manage/flatten)
3. kirim pesan Telegram yang tertunda, catat `state/runs.csv`
4. `tools/save_state.sh` commit + push `state/` (`[skip ci]`)

Mode `control/bot.yaml`: `off` | `paper` (default, aman) | `live` | `manage` (hanya kurangi/tutup)
| `flatten` (tutup semua posisi milik RNT). Diubah lewat workflow `control.yml`.

## Koneksi keluar

| Tujuan | Dari | Untuk apa |
|---|---|---|
| Hyperliquid `/info` (publik) | `rntbot/hype.py`, `config.yaml:70` | candle, mids, funding (batas 1000 bobot/menit) |
| Hyperliquid `/exchange` | `rntbot/live.py:83,133,139` | order IOC dan set leverage di subaccount RNT, hanya mode live/manage/flatten |
| Telegram Bot API | `rntbot/notify.py:22` | pesan harian dan alarm |
| Google Sheets API / webhook | `rntbot/sheets.py:22-33` | cermin data (opsional) |
| GitHub REST API / `gh` | `run_watchdog.py`, `bot.yml:124` | baca status run, dispatch ulang watcher |
| Repo GitHub (push) | `tools/save_state.sh`, `tools/save_control.sh` | simpan `state/` dan `control/bot.yaml` |
| Riset saja: arsip Binance `data.binance.vision` | `research/code/fetch_delisted.py` | kline pair yang sudah delisted, publik, tanpa key |

Riset (`research/`) membaca data lake lokal di luar repo (`C:\Crypto data\backtest data and more`);
bot tidak bergantung padanya.

## Secret dan siapa yang memakainya

| Secret | Dipakai oleh |
|---|---|
| `HYPE_RNT_AGENT_KEY_66_CHAR` (key API wallet, bisa menandatangani order) | `bot`, `canary`, `smoke` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `bot`, `watchdog`, `canary`, `smoke` |
| `GOOGLE_SERVICE_ACCOUNT_JSON`, `GSHEET_SPREADSHEET_ID`, `GSHEET_WEBHOOK_URL` | `bot`, `smoke` |
| `GITHUB_TOKEN` (otomatis) | `bot`, `watchdog` |

## Izin workflow

| Workflow | Izin | Pemicu |
|---|---|---|
| `bot.yml` | `contents: write`, `actions: write` | cron 11,41 + self-dispatch |
| `watchdog.yml` | `contents: write`, `actions: write` | cron tiap 15 menit |
| `control.yml` | `contents: write` | manual |
| `canary.yml`, `smoke.yml` | `contents: read` | manual |
| `ci.yml` | tanpa secret | push, PR, cron harian |

## Batas akses di sisi trading

- Satu-satunya pemanggilan SDK Hyperliquid yang menulis adalah `Exchange.order` (limit IOC,
  reduce-only untuk tutup/kurangi/balik arah) dan `Exchange.update_leverage`
  (`rntbot/live.py:133,139`). Pencarian seluruh repo (`*.py`, `*.sh`, `*.yml`) tidak menemukan
  withdraw, transfer, `approve_agent`, atau cancel.
- Live hanya jalan jika mode live/manage/flatten **dan** key tersedia. Alamat master/akun/agent
  di `config.yaml` kosong secara default, dan `make_trader` menolak jalan sebelum diisi.
- Akun harus SUBACCOUNT khusus RNT. Posisi yang bukan milik RNT membuat live berhenti (Halt);
  `blocked_agents` menolak API wallet bot lain; `verify_agent` menolak key yang tidak cocok
  atau kedaluwarsa.
- Semua order bercloid berawalan `RNT`; hanya posisi tercatat di `state/live.json` yang disentuh.

Batasan: ini dibaca dari kode, bukan audit keamanan. Apa yang bisa dilakukan API wallet di sisi
bursa ditentukan Hyperliquid, bukan repo ini.

## Peta yang bisa dijelajahi

Graph interaktif dibuat dengan graphify (lokal, tidak di-commit): jalankan `/graphify .`
lalu buka `graphify-out/graph.html`. Cek ulang halaman ini bila workflow, secret, atau modul
integrasi berubah.
