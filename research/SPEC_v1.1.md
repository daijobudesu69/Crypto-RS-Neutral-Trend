# RNT v1.1 — spesifikasi lengkap (perbaikan pasca-audit, 2026-10-09)

**Status:** pengganti [SPEC_FROZEN.md](SPEC_FROZEN.md) (v1.0). Hanya dua definisi yang berubah, dan keduanya dipilih dari data **in-sample**, bukan OOS. Bukti ada di [audit_response/AUDIT_RESPONSE.md](audit_response/AUDIT_RESPONSE.md).

**Catatan kejujuran:** OOS 2025-01 → 2026-09 sudah dilihat sebelum v1.1 ditulis. Karena itu angka OOS v1.1 **tidak lagi murni out-of-sample**. Bukti yang tersisa untuk v1.1 adalah IS dan forward test.

## Yang berubah dari v1.0

| # | v1.0 | v1.1 | Alasan (data IS) |
|---|---|---|---|
| 1 | Umur koin = jumlah candle harian, **termasuk** ±999 candle pra-listing yang dikirim API HYPE (harga Binance, volume 0) | Umur koin = jumlah hari dengan **volume > 0 di HYPE** | Replika kondisi ini di IS (perp Binance diisi mundur dengan harga spot): aturan v1.0 Sharpe 1,72, aturan v1.1 Sharpe 1,92 |
| 2 | Persentil skor dihitung antar **semua koin yang punya harga** hari itu, termasuk candle pra-listing | Persentil antar koin yang **benar-benar diperdagangkan hari itu** (harga ada **dan** volume > 0) | Netral di IS (1,92 vs 1,95). Dipilih karena terdefinisi jelas dan sama persis dengan yang bisa dihitung bot. Versi "hanya top-20" lebih buruk di IS (1,83 vs 1,91), jadi tidak dipakai |

## Rumus lengkap

Notasi: hari `d` = candle harian HYPE yang dibuka 00:00 UTC hari `d` dan ditutup 00:00 UTC hari `d+1`. Semua perhitungan memakai data sampai close hari `d`. Order dikirim tepat setelah close itu (07:00 WIB).

1. **Data:** candle 1d semua perp HYPE yang belum delist (`candleSnapshot`). Keluarkan USDC, USDT, USDE, USDH, FDUSD, DAI, PYUSD, USD1, PAXG, XAUT, USTC.
2. **Aktif(c, d)** = close(c, d) ada **dan** quote_volume(c, d) > 0. Quote volume = volume × (open + high + low + close) / 4.
3. **Umur(c, d)** = jumlah hari ≤ d dengan Aktif(c, ·) = benar.
4. **Likuiditas(c, d)** = rata-rata quote_volume 30 hari terakhir (minimal 15 hari data). Hanya dihitung untuk koin dengan Umur ≥ 200.
5. **Universe RS(d)** = 20 koin dengan Likuiditas tertinggi. **Universe Trend(d)** = 5 koin teratas.
6. **Volatilitas(c, d)** = EWM std return close-to-close harian (span 30, minimal 15 hari) × √365.
7. **Skor RS(c, d)** = rata-rata, untuk L ∈ {7, 14, 28, 56}, dari persentil (0–1, `rank(pct=True)`) nilai x_L = [close(d)/close(d−L) − 1] ÷ [Volatilitas(c, d) × √(L/365)]. Persentil dihitung **di antara semua koin yang Aktif hari d dan punya x_L**. Ini bukan hanya top-20; universe hanya membatasi koin yang boleh dibeli atau di-short.
8. **Buku RS:** di dalam Universe RS, urutkan Skor dari tertinggi.
   - Long: masuk kalau peringkat ≤ 4, tahan selama peringkat ≤ 8. Short: sama, dihitung dari skor terendah.
   - Keluar dari universe = keluar dari buku.
   - Bobot: tiap leg dibagi rata. Total long = +0,5 dan total short = −0,5 (sebelum penskalaan).
9. **Buku Trend:** untuk n ∈ {20, 55, 100}, posisi_n = 2 × (close − min_n) ÷ (max_n − min_n) − 1, dengan min/max dari close n hari termasuk hari d. Sinyal = rata-rata ketiganya. Bobot(c) = max(0, sinyal) × 0,40 ÷ Volatilitas(c), maksimal 1,5, lalu dibagi 5. Koin di luar Universe Trend = 0.
10. **Penskalaan tiap buku:** faktor(d) = min(2, 0,20 ÷ RV(d)). RV(d) = std return harian buku mentah (bobot kemarin × return hari ini) selama 60 hari terakhir (minimal 20) × √365.
11. **Gabungan:** W = RS × faktor_RS + Trend × faktor_Trend. Kalau Σ|W| > 2,5, semua bobot dikecilkan proporsional.
12. **Eksekusi:**
    - Target USD = W × ekuitas.
    - |target| < 10 USD: jadi ±10 kalau |target| ≥ 5, selain itu 0.
    - Posisi searah tidak disentuh selama |target − posisi| ≤ max(10 USD, 40% × |target|).
    - Order yang lebih kecil dari 10 USD tidak dikirim, kecuali untuk menutup posisi.
    - Margin: cross, di subaccount khusus.
13. **Biaya di backtest:** 0,07% per sisi, ditambah funding HYPE per jam riil (biaya saja, bukan sinyal).

Kode: `code/rnt.py` dengan `SPEC` + `age_mode="real"`, `pct_scope="traded"`, dan `code/account.py`.

## Alarm (pengganti "stop di DD 35%")

Lihat bagian alarm di [audit_response/AUDIT_RESPONSE.md](audit_response/AUDIT_RESPONSE.md).
