"""Market regime from SPY trend, VIX and sector breadth."""
from __future__ import annotations

import pandas as pd

from .config import BENCHMARK, SECTOR_ETF, VIX
from .indicators import _f, realized_vol, sma


def compute_regime(prices: dict[str, pd.DataFrame]) -> dict:
    out: dict = {"label": "unknown", "notes": []}
    spy = prices.get(BENCHMARK)
    if spy is not None and len(spy) >= 200:
        c = spy["Close"]
        last = float(c.iloc[-1])
        out["spy_price"] = last
        out["spy_vs_50dma"] = _f(last / sma(c, 50).iloc[-1] - 1)
        out["spy_vs_200dma"] = _f(last / sma(c, 200).iloc[-1] - 1)
        out["spy_ret_1w"] = _f(c.iloc[-1] / c.iloc[-6] - 1)
        out["spy_ret_1m"] = _f(c.iloc[-1] / c.iloc[-22] - 1)
        out["spy_vol_20"] = _f(realized_vol(c, 20).iloc[-1])
        out["spy_drawdown_1y"] = _f(last / c.iloc[-252:].max() - 1)

    vix = prices.get(VIX)
    if vix is not None and len(vix) >= 20:
        out["vix"] = _f(vix["Close"].iloc[-1])
        out["vix_20dma"] = _f(sma(vix["Close"], 20).iloc[-1])

    above = total = 0
    sector_rows = {}
    for etf in SECTOR_ETF.values():
        df = prices.get(etf)
        if df is None or len(df) < 50:
            continue
        c = df["Close"]
        total += 1
        vs50 = float(c.iloc[-1] / sma(c, 50).iloc[-1] - 1)
        above += vs50 > 0
        sector_rows[etf] = {"vs_50dma": vs50, "mom_20": float(c.iloc[-1] / c.iloc[-21] - 1)}
    out["breadth_sectors_above_50dma"] = above / total if total else None
    out["sector_momentum_20"] = dict(sorted(((k, v["mom_20"]) for k, v in sector_rows.items()), key=lambda kv: -kv[1]))

    trend = out.get("spy_vs_200dma")
    v = out.get("vix")
    breadth = out.get("breadth_sectors_above_50dma")
    if trend is not None and v is not None and breadth is not None:
        if trend > 0 and v < 20 and breadth >= 0.5:
            out["label"] = "risk-on"
        elif trend < 0 and (v > 25 or breadth < 0.35):
            out["label"] = "risk-off"
        elif v >= 25:
            out["label"] = "high-volatility"
        else:
            out["label"] = "neutral"
    return out
