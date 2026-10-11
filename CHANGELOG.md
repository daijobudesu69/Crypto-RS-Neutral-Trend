# Changelog

Setiap perubahan parameter strategi (`config.yaml` → `strategy`, `rules`) dicatat di sini
dengan tanggal dan alasan, karena membuat forward test tidak lagi sebanding dengan backtest.

## 2026-10-09 — infrastruktur awal

- Bot harian RNT v1.1 (= `research/SPEC_v1.1.md`): paper selalu jalan; live di subaccount HYPE
  hanya kalau user menyalakannya.
- Buku bayangan "rf" (mesin 1 off saat BTC 90 hari turun), paper saja, untuk evaluasi saran audit.
- Alarm: kuning (DD 20% / CUSUM) → ukuran live ×0,5; merah (DD 25%) → live hanya kurangi/tutup;
  cek teknis bulanan live vs paper.
- Paritas dengan kode riset dibuktikan di data nyata (`tools/parity_check.py`): bobot identik,
  akun OOS 440,45 USD = riset, 1.616 order = riset.
- Satu beda yang disengaja dari loader riset: riset membuang koin yang FILE-nya < 30 candle
  (memakai panjang file total, termasuk masa depan). Bot tidak bisa tahu itu, jadi semua koin ikut;
  bobot tetap identik di data nyata.
- `forward_start` = 2026-10-10 (07:00 WIB).

## 2026-10-10 — pesan Telegram

- Pesan harian diringkas: PnL dan DD, Relative Strength Report, Trend Report. Pesan live dipisah.
- Peringatan API wallet kedaluwarsa hanya di sisa 14/7/3/2/1/0 hari; peringatan API wallet bot lain sekali saja.
- Tidak ada perubahan parameter strategi.

## 2026-10-11 — laporan v1.1

- `research/PROJECT CRYPTO - RNT.md` ditulis ulang untuk v1.1 (hasil OOS/IS, ketahanan, rezim, konsentrasi, alarm, bot,
  forward test) dengan 16 grafik baru (`research/charts/v11_*.png`).
- Skrip baru: `research/code/report_v11_data.py`, `report_v11_charts.py`. Tidak ada perubahan parameter strategi.
