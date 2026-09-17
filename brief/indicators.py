"""Technical indicators. Pure pandas, no network. Input: OHLCV DataFrame with columns
Open, High, Low, Close, Volume indexed by date, oldest first."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _f(x) -> float | None:
    """Convert numpy/pandas scalars to float, NaN to None."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def sma(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI (exponential smoothing with alpha = 1/n)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(100.0).where(avg_loss.notna())


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev_close).abs(), (df["Low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()


def momentum(close: pd.Series, n: int) -> pd.Series:
    return close / close.shift(n) - 1


def realized_vol(close: pd.Series, n: int = 20) -> pd.Series:
    return np.log(close).diff().rolling(n).std() * math.sqrt(252)


def compute_technicals(df: pd.DataFrame) -> dict:
    """All V1 technical fields for the last bar of df."""
    df = df.dropna(subset=["Close"])
    close = df["Close"]
    last = close.iloc[-1]
    n = len(df)

    d20, d40, d100 = sma(close, 20), sma(close, 40), sma(close, 100)
    high20 = df["High"].rolling(20).max() if "High" in df else close.rolling(20).max()
    vol = df["Volume"] if "Volume" in df else pd.Series(np.nan, index=df.index)
    rel_vol = vol / vol.rolling(20).mean()
    atr14 = atr(df, 14) if {"High", "Low"} <= set(df.columns) else pd.Series(np.nan, index=df.index)
    rsi14 = rsi(close, 14)

    def pct_vs(series: pd.Series) -> float | None:
        v = _f(series.iloc[-1])
        return None if v in (None, 0) else last / v - 1

    out = {
        "price": _f(last),
        "bars": n,
        "dma20": _f(d20.iloc[-1]),
        "dma40": _f(d40.iloc[-1]),
        "dma100": _f(d100.iloc[-1]),
        "pct_vs_dma20": pct_vs(d20),
        "pct_vs_dma40": pct_vs(d40),
        "pct_vs_dma100": pct_vs(d100),
        "rsi14": _f(rsi14.iloc[-1]),
        "atr14": _f(atr14.iloc[-1]),
        "atr_pct": _f(atr14.iloc[-1] / last) if _f(atr14.iloc[-1]) else None,
        "high_20": _f(high20.iloc[-1]),
        "pct_from_20d_high": pct_vs(high20),
        "rel_volume": _f(rel_vol.iloc[-1]),
        "mom_20": _f(momentum(close, 20).iloc[-1]),
        "mom_40": _f(momentum(close, 40).iloc[-1]),
        "ret_1w": _f(momentum(close, 5).iloc[-1]),
        "vol_20": _f(realized_vol(close, 20).iloc[-1]),
        "avg_dollar_vol_20": _f((close * vol).rolling(20).mean().iloc[-1]),
    }
    d20v, d40v, d100v = out["dma20"], out["dma40"], out["dma100"]
    if None not in (d20v, d40v, d100v):
        out["dma_stack"] = "bull" if d20v > d40v > d100v else "bear" if d20v < d40v < d100v else "mixed"
    else:
        out["dma_stack"] = None
    return out


def setup_tags(m: dict) -> list[str]:
    """Human-readable flags derived from the metrics dict. Used in the email and in the LLM context."""
    tags: list[str] = []
    g = m.get
    if g("pct_from_20d_high") is not None and g("pct_from_20d_high") >= -0.01 and (g("rel_volume") or 0) >= 1.3:
        tags.append("breakout on volume")
    elif g("pct_from_20d_high") is not None and g("pct_from_20d_high") >= -0.01:
        tags.append("at 20-day high")
    if g("dma_stack") == "bull":
        tags.append("bullish MA stack")
    elif g("dma_stack") == "bear":
        tags.append("bearish MA stack")
    if g("rsi14") is not None:
        if g("rsi14") >= 75:
            tags.append("overbought RSI")
        elif g("rsi14") <= 30:
            tags.append("oversold RSI")
    if g("eps_rev_pct") is not None:
        if g("eps_rev_pct") >= 0.02:
            tags.append("EPS estimates rising")
        elif g("eps_rev_pct") <= -0.02:
            tags.append("EPS estimates cut")
    if g("rev_rev_pct") is not None:
        if g("rev_rev_pct") >= 0.01:
            tags.append("revenue estimates rising")
        elif g("rev_rev_pct") <= -0.01:
            tags.append("revenue estimates cut")
    if g("pe_vs_hist") is not None:
        if g("pe_vs_hist") >= 0.25:
            tags.append("P/E rich vs history")
        elif g("pe_vs_hist") <= -0.25:
            tags.append("P/E cheap vs history")
    if g("rs_sector_20") is not None and g("rs_sector_20") >= 0.05:
        tags.append("leading sector")
    elif g("rs_sector_20") is not None and g("rs_sector_20") <= -0.05:
        tags.append("lagging sector")
    if g("vol_20") is not None and g("vol_20") >= 0.5:
        tags.append("high volatility")
    if g("avg_dollar_vol_20") is not None and g("avg_dollar_vol_20") < 2e7:
        tags.append("thin liquidity")
    return tags
