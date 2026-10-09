# Setup bot RNT

Urutan yang disarankan. Langkah 1–2 cukup untuk mulai paper. Telegram, Sheets, dan HYPE
bisa ditambahkan kapan saja tanpa mengubah kode: bot otomatis memakainya begitu secret-nya ada.

| Langkah | Wajib untuk | Dikerjakan |
|---|---|---|
| 1. Repo GitHub + Actions | semua | sudah |
| 2. Cek paper jalan | semua | user |
| 3. Telegram | notifikasi | user |
| 4. Google Sheets | cermin log (opsional) | user |
| 5. HYPE subaccount + API wallet | live | user |
| 6. Canary, lalu nyalakan live | live | user |

---

## 1. Repo GitHub

Repo: **https://github.com/daijobudesu69/Crypto-RS-Neutral-Trend** (publik). Publik =
menit Actions tidak dibatasi (watcher nonstop ±4.500 menit/bulan; privat hanya 2.000).
Konsekuensinya: isi `state/` (ekuitas, posisi, order) bisa dibaca siapa saja. Secret tetap aman.

- Workflow meminta izin tulis sendiri (`permissions`), tidak perlu mengubah setting repo.
- Cron menyalakan `RNT bot` otomatis. Untuk mulai segera:

```bash
gh workflow run bot.yml --repo daijobudesu69/Crypto-RS-Neutral-Trend -f mode=loop
```

- Forward test mulai `forward_start` di `config.yaml` (2026-10-10, 07:00 WIB). Sebelum itu
  bot hanya mencatat run.

## 2. Cek paper jalan

- Tab Actions → `RNT bot` → log `siklus #1`. Job harian butuh ±6–8 menit (candle 450 hari
  ±230 perp HYPE, dengan jeda rate limit). Siklus tanpa pekerjaan ±1 detik.
- `state/equity.csv` dapat satu baris per hari setelah 00:02 UTC (07:02 WIB).
- Lokal, tanpa mengubah state:

```bash
python run_status.py
```

## 3. Telegram

1. Chat `@BotFather` → `/newbot` → simpan token.
2. Kirim satu pesan ke bot, buka `https://api.telegram.org/bot<TOKEN>/getUpdates`, ambil `chat.id`.
3. Simpan sebagai secret:

```bash
gh secret set --repo daijobudesu69/Crypto-RS-Neutral-Trend TELEGRAM_BOT_TOKEN
```

```bash
gh secret set --repo daijobudesu69/Crypto-RS-Neutral-Trend TELEGRAM_CHAT_ID
```

Yang dikirim: ringkasan harian (±07:05–07:15 WIB), perubahan mode, perubahan level alarm,
cek teknis bulanan, posisi live yang hilang di luar bot, error (maks 1× per 6 jam), watchdog.
Pesan yang gagal terkirim disimpan di `state/outbox.json` dan dicoba ulang selama 48 jam.

## 4. Google Sheets (opsional)

Pilih **satu**:

**A. Apps Script (paling mudah, tanpa kunci).** Buka spreadsheet → Extensions → Apps Script →
tempel `docs/apps_script.gs` → Deploy → New deployment → Web app, Execute as: *Me*,
Who has access: *Anyone* → salin URL.

```bash
gh secret set --repo daijobudesu69/Crypto-RS-Neutral-Trend GSHEET_WEBHOOK_URL
```

**B. Service account.** Buat service account di Google Cloud, aktifkan Sheets API, unduh kunci
JSON, bagikan spreadsheet ke `client_email` dengan akses Editor.

```bash
gh secret set --repo daijobudesu69/Crypto-RS-Neutral-Trend GOOGLE_SERVICE_ACCOUNT_JSON < key.json
```

```bash
gh secret set --repo daijobudesu69/Crypto-RS-Neutral-Trend GSHEET_SPREADSHEET_ID
```

Tab yang ditulis: `equity`, `orders`, `positions` (posisi paper yang ditutup), `alarms`.
Gagal menulis ke Sheets tidak pernah menggagalkan run.

## 5. HYPE: subaccount + API wallet

Aturan:
- **RNT wajib di subaccount khusus.** Akun utama dipakai RMF; MEX juga di HYPE. Satu koin
  hanya bisa punya satu posisi per akun, dan RNT memegang long + short. Bot menolak jalan
  kalau `account_address` = `master_address`, dan berhenti (Halt) kalau ada posisi yang
  bukan dibuka RNT.
- **Margin: cross.** Leverage per koin di-set 3× (atau maksimum koin itu kalau lebih kecil).
  Itu hanya batas margin; eksposur diatur ukuran order (gross rata-rata ±0,9×, maks 2,5×).
- Ekuitas = seluruh saldo subaccount; ukuran order mengikuti saldo itu. Isi hanya dengan modal RNT.
- API wallet maks 180 hari. Sebelum kedaluwarsa: buat yang baru, ganti isi secret, perbarui
  `agent_address` dan `agent_valid_until`. Bot memberi peringatan 14 hari sebelumnya.

Langkah:
1. Buat subaccount di HYPE (mis. "RNT"), deposit modal RNT ke sana.
2. Buat API wallet baru (mis. "RNT.bot"). Simpan **private key** (66 karakter, `0x` + 64 hex),
   bukan alamatnya:

```bash
gh secret set --repo daijobudesu69/Crypto-RS-Neutral-Trend HYPE_RNT_AGENT_KEY_66_CHAR
```

3. Isi alamat PUBLIK di `config.yaml` → `execution`: `master_address` (akun utama),
   `account_address` (subaccount RNT), `agent_address` (API wallet), `agent_valid_until`.
4. Cek hanya-baca (tanpa order). Hasilnya dikirim ke Telegram:

```bash
gh workflow run smoke.yml --repo daijobudesu69/Crypto-RS-Neutral-Trend
```

## 6. Canary, lalu nyalakan live (user sendiri)

Canary sekali (mode harus `paper`/`off`): long ±10 USDC → tutup reduce-only, lalu short
±10 USDC → tutup reduce-only, lewat jalur order yang sama dengan live (biaya ±0,02 USDC).

```bash
gh workflow run canary.yml --repo daijobudesu69/Crypto-RS-Neutral-Trend -f coin=ETH
```

Nyalakan live hanya kalau "✅ RNT CANARY OK", dan cocokkan ekuitas di pesan itu dengan UI HYPE.

```bash
gh workflow run control.yml --repo daijobudesu69/Crypto-RS-Neutral-Trend -f mode=live
```

- Berlaku ≤ ~10 menit. Telegram mengonfirmasi "mode sekarang".
- Kalau dinyalakan di tengah hari, live langsung menyesuaikan ke target hari itu.
- Buku paper tetap jalan sebagai pembanding (cek teknis bulanan memakainya).

Rem dan pembatalan:

```bash
gh workflow run control.yml --repo daijobudesu69/Crypto-RS-Neutral-Trend -f mode=manage
```

```bash
gh workflow run control.yml --repo daijobudesu69/Crypto-RS-Neutral-Trend -f mode=flatten
```

```bash
gh workflow run control.yml --repo daijobudesu69/Crypto-RS-Neutral-Trend -f reset_breaker=true
```

## Secret (ringkasan)

| Secret | Untuk | Wajib |
|---|---|---|
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | notifikasi | tidak (tanpa ini pesan hanya di log) |
| `GSHEET_WEBHOOK_URL` atau `GOOGLE_SERVICE_ACCOUNT_JSON` + `GSHEET_SPREADSHEET_ID` | cermin Sheets | tidak |
| `HYPE_RNT_AGENT_KEY_66_CHAR` | live, canary, smoke | hanya untuk live |
