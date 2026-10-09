# Audit DUET — 2026-10-09

Laporan lengkap: https://claude.ai/artifact/48BgTzdFk8qzzd8mME5azR

Semua skrip memakai `dq.py` (implementasi independen dari SPEC_FROZEN.md, tidak meng-import kode penulis).
Dijalankan dengan Python 3.13, pandas 3.0.5. Set `DUET_AUDIT_BASE` ke folder yang berisi `data/` (data lake) dan `Edge Hypotesis 20261009/`.

| Skrip | Isi | Hasil utama |
|---|---|---|
| t01_indep.py | backtest ulang independen vs penulis | 522,39 = 522,39; cache penulis = data mentah |
| t02_lookahead_ghost.py | uji look-ahead; candle volume 0 | selisih bobot 0; 0 order di hari volume 0 |
| t04b_ghost_decomp.py | aturan umur & cakupan persentil | umur nyata 446; persentil top-20 424; keduanya 358 |
| t03_data_truth.py | HL vs Binance | korelasi 0,9994; PnL dgn harga Binance 525; universe Binance 459 |
| t05_enddate_stats.py | tanggal akhir, bootstrap, hari terbaik | 31 Jul 2026: 354; realized 378; Sharpe 95% 0,5–3,5 |
| t07_exec.py, t07b_exec_is.py | eksekusi telat 15 mnt – 3 hari | +15–60 mnt: 499–506; +4 jam 516; telat 1 hari 450 |
| t08_ops_size.py | hari terlewat, ukuran akun, band | lewat 2–3 hari/bln median 511; modal ≥500 setara 492 |
| t09_misc.py | konsentrasi posisi, klaim lain di laporan | 5 posisi = 50% profit; 10 = 81% |
| t10_is_dead.py, t10b.py | IS + koin mati, penalti funding, underwater | 2.651; penalti 0,05–0,1%/hari 2.314–1.983; underwater 715 hari |
| t13_risk.py, t13b_regime.py | stress, rezim pasar, aturan stop | BTC 90h naik: +97%/+106% per th; turun: +5%/+18% |
| t16_sens.py | tetangga parameter IS & OOS, grid 60 | OOS>IS di 87%; korelasi IS-OOS 0,06; dasar peringkat 7 |
| t20_combo.py | koreksi gabungan | 30 mnt + umur nyata 429; + persentil top-20 342 |

File `_b*.tar`, `_bundle_daily.tar`, `_bn_15m_hour0.parquet`, `_hl_intraday_hour0.parquet` adalah paket data sementara untuk audit; aman dihapus.
