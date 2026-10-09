"""Cek jaringan sungguhan (CI: job connectivity, bukan gerbang). Tidak ada order."""
import time

import pytest

from rntbot import config, hype, strategy

pytestmark = pytest.mark.network


def test_hype_meta_and_candles():
    cfg = config.load()
    info = hype.InfoClient(cfg.hype.info_url, cfg.hype.weight_per_minute)
    meta = info.meta()
    assert "BTC" in meta and meta["BTC"]["szDecimals"] >= 0
    now = int(time.time() * 1000)
    df = info.candles("BTC", "1d", now - 40 * 86_400_000)
    assert len(df) >= 35 and (strategy.quote_volume(df) > 0).all()
    assert info.all_mids()["BTC"] > 0
