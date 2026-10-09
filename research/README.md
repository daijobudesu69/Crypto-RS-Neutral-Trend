# Riset RNT (ex-DUET), 2026-10-09

Riset asal strategi, di data lake `C:\Crypto data\backtest data and more\data` (tidak ikut repo).
Bot tidak membutuhkan apa pun dari folder ini, kecuali tes paritas (`tests/test_strategy_parity.py`
mengimpor `research/code` dengan panel sintetis).

| File | Isi |
|---|---|
| [PROJECT CRYPTO - RNT.md](PROJECT%20CRYPTO%20-%20RNT.md) | laporan riset v1.0 (+ blok koreksi pasca-audit di atas) |
| [SPEC_FROZEN.md](SPEC_FROZEN.md) | spesifikasi v1.0, dikunci sebelum OOS |
| [SPEC_v1.1.md](SPEC_v1.1.md) | **spesifikasi yang berlaku** (rumus lengkap 13 langkah) |
| [audit_2026-10-09/](audit_2026-10-09/) | audit independen oleh user |
| [audit_response/AUDIT_RESPONSE.md](audit_response/AUDIT_RESPONSE.md) | respons audit dengan bukti data (r01–r07) |
| `code/` | pipeline riset: `lab.py` (loader, engine, metrik), `strat.py`, `rnt.py` (strategi), `account.py` (simulasi akun 200 USD), `explore1-6.py` (tahap IS), `oos.py`, `survivorship_is.py`, `fetch_delisted.py` |
| `results/` | tabel hasil (CSV/JSON). `results/cache/` (panel pickle, ±218 MB) tidak ikut repo |
| `charts/` | grafik laporan |
| `data/` (lokal saja) | candle koin delist HYPE (56) dan perp Binance di luar data lake (579), funding riil 70 koin mati |

Hasil utama v1.1 (setelah audit):
- OOS Jan 2025 → Sep 2026: 200 → 440 USD, Sharpe 1,69, DD −16% (tidak lagi murni OOS).
- IS 2020-07 → 2024-12 (Binance + koin mati + funding riil): Sharpe 2,09, DD −25,5%.
