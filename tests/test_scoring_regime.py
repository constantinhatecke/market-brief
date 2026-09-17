import pandas as pd

from brief.config import SECTOR_ETF
from brief.regime import compute_regime
from brief.scoring import score_table, select_candidates
from tests.conftest import synthetic_ohlcv


def _m(mom, liq=1e8, rsi=50, **kw):
    return {"mom_20": mom, "mom_40": mom, "rs_sector_20": mom, "rs_market_20": mom, "eps_rev_pct": 0.0,
            "rev_rev_pct": 0.0, "rel_volume": 1.0, "rsi14": rsi, "pct_from_20d_high": -0.05, "avg_dollar_vol_20": liq, **kw}


def test_ranking_and_liquidity_filter():
    metrics = {"A": _m(0.20), "B": _m(0.10), "C": _m(0.0), "D": _m(-0.10), "E": _m(0.30, liq=1e6), "P": _m(0.25)}
    df = score_table(metrics)
    assert df.index[0] == "E"  # highest raw momentum ranks first
    up, down = select_candidates(df, 3, 2e7, exclude={"P"})
    assert "E" not in up and "P" not in up  # illiquid and portfolio names excluded
    assert up[0] == "A" and down == ["D"]


def test_overbought_penalty():
    metrics = {"A": _m(0.20, rsi=80), "B": _m(0.20, rsi=50)}
    df = score_table(metrics)
    assert df.loc["B", "score"] > df.loc["A", "score"]


def test_regime_labels():
    prices = {"SPY": synthetic_ohlcv(300, drift=0.001, seed=1), "^VIX": synthetic_ohlcv(300, seed=2, start=15)}
    for i, etf in enumerate(SECTOR_ETF.values()):
        prices[etf] = synthetic_ohlcv(300, drift=0.001, seed=10 + i)
    r = compute_regime(prices)
    assert r["label"] in {"risk-on", "neutral", "risk-off", "high-volatility"}
    assert 0 <= r["breadth_sectors_above_50dma"] <= 1
    assert len(r["sector_momentum_20"]) == len(SECTOR_ETF)
