# RNT — spesifikasi beku (dikunci 2026-10-09, SEBELUM uji OOS)

Semua aturan di bawah dipilih hanya dari data in-sample (Binance perp, 2020-07 → 2024-12). File ini ditulis sebelum OOS (2025-01 → 2026-09) dijalankan, dan tidak diubah setelahnya. Kode: `code/rnt.py` (SPEC) dan `code/account.py`.

| Komponen | Aturan |
|---|---|
| Data | Candle harian HYPE (OHLCV). Tidak memakai OI, funding, order book, ataupun taker flow sebagai sinyal |
| Jadwal | Sekali sehari, setelah close harian 00:00 UTC (07:00 WIB) |
| Volatilitas koin | EWM std return harian, span 30, ×√365 |
| Eligible | ≥ 200 candle harian; diranking dari rata-rata quote volume 30 hari |
| **Mesin 1: RS-Neutral** | Universe 20 koin paling likuid. Skor = rata-rata persentil lintas koin dari [return L hari ÷ (vol × √(L/365))] untuk L = 7, 14, 28, 56 |
| | Long: masuk kalau peringkat ≤ 4, tahan selama peringkat ≤ 8. Short: kebalikannya (4 terlemah, tahan selama ≤ 8 dari bawah) |
| | Bobot sama per leg, long 50% dan short 50% dari gross mesin |
| **Mesin 2: Trend** | Universe 5 koin paling likuid. Sinyal = rata-rata posisi close di channel 20/55/100 hari, diskala ke −1..1 |
| | Long-only: bobot = max(0, sinyal) × (40% ÷ vol koin) ÷ 5, maksimal 1,5 per koin |
| Penskalaan | Tiap mesin diskala ke volatilitas tahunan 20% (realized vol buku 60 hari terakhir, faktor maksimal 2×). Lalu kedua buku dijumlahkan |
| Batas gross | Total gross ≤ 2,5× ekuitas |
| Eksekusi | Target notional = bobot × ekuitas |
| | Order minimum 10 USD: target < 10 dibulatkan ke 10 kalau ≥ 5, selain itu 0 |
| | Posisi searah tidak disentuh selama selisihnya ≤ max(10 USD, 40% target) |
| Biaya | 0,07% per sisi (fee taker HYPE 0,045% + slippage), ditambah funding HYPE riil per jam (hanya sebagai biaya) |

Pilihan parameter yang dilihat di IS: lookback ensemble 7/14/28/56, buffer 4/8, top-20, top-5 trend, band 0,40. Semuanya berada di dataran parameter yang lebar (lihat `results/stage*_is.csv`).
