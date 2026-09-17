import numpy as np
import pandas as pd

from brief.indicators import atr, compute_technicals, momentum, rsi, setup_tags, sma


def test_sma_matches_rolling_mean(ohlcv):
    assert np.isclose(sma(ohlcv["Close"], 20).iloc[-1], ohlcv["Close"].iloc[-20:].mean())


def test_rsi_bounds_and_direction():
    up = pd.Series(np.linspace(100, 150, 60))
    down = pd.Series(np.linspace(150, 100, 60))
    assert rsi(up).iloc[-1] > 70
    assert rsi(down).iloc[-1] < 30
    r = rsi(up + np.sin(np.arange(60)) * 5)
    assert r.dropna().between(0, 100).all()


def test_atr_positive_and_scaled(ohlcv):
    a = atr(ohlcv, 14).iloc[-1]
    assert a > 0
    assert a < ohlcv["Close"].iloc[-1] * 0.1


def test_momentum_formula(ohlcv):
    c = ohlcv["Close"]
    assert np.isclose(momentum(c, 20).iloc[-1], c.iloc[-1] / c.iloc[-21] - 1)


def test_compute_technicals_fields(ohlcv):
    m = compute_technicals(ohlcv)
    for k in ["price", "dma20", "dma40", "dma100", "rsi14", "atr14", "high_20", "rel_volume", "mom_20", "mom_40", "vol_20", "avg_dollar_vol_20"]:
        assert m[k] is not None, k
    assert m["pct_from_20d_high"] <= 0
    assert m["dma_stack"] in {"bull", "bear", "mixed"}
    assert 0 < m["atr_pct"] < 0.2


def test_setup_tags():
    tags = setup_tags({"pct_from_20d_high": -0.005, "rel_volume": 1.6, "dma_stack": "bull", "rsi14": 80,
                       "eps_rev_pct": 0.05, "pe_vs_hist": 0.4, "rs_sector_20": 0.08, "vol_20": 0.6, "avg_dollar_vol_20": 1e6})
    assert "breakout on volume" in tags and "overbought RSI" in tags and "EPS estimates rising" in tags
    assert "P/E rich vs history" in tags and "leading sector" in tags and "thin liquidity" in tags
