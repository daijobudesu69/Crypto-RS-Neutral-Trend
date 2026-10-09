# state/

Ditulis bot setiap siklus dan di-commit oleh workflow (`[skip ci]`). Jangan edit manual saat
watcher jalan.

| File | Isi |
|---|---|
| `equity.csv` | 1 baris per hari: ekuitas paper v1.1, bayangan filter rezim (`rf_equity`), live, gross/net, level alarm, DD, CUSUM, skala mesin, BTC 90 hari, telat eksekusi |
| `orders.csv` | semua order (buku `paper`, `rf`, `live`) |
| `targets.csv` | target bobot per koin per hari (gabungan, mesin 1, mesin 2, bayangan) + peringkat RS + dipegang paper/live |
| `positions.csv` | posisi paper yang ditutup: sisi, masuk/keluar, PnL bersih, fee, funding |
| `alarms.csv` | setiap perubahan level alarm |
| `runs.csv` | log siklus (baris idle maks 1x per jam) |
| `paper.json` | buku paper `paper` dan `rf` + hari terakhir yang diproses |
| `view.json` | target bobot hari ini (dipakai ulang oleh percobaan live di hari yang sama) |
| `live.json` | posisi milik RNT, hari terakhir live sukses, percobaan per hari, ekuitas terakhir |
| `alarm_state.json` | level alarm terakhir, awal hitungan (`since`), cek teknis bulanan |
| `outbox.json` | pesan Telegram yang belum terkirim |
| `alerts.json`, `watchdog.json` | penanda supaya alarm tidak dikirim berulang |

CSV memakai `merge=union` (`.gitattributes`), jadi run yang menulis bersamaan tidak bentrok.
