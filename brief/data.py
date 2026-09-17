"""Market data access. Everything network-bound lives here so it can be mocked in tests."""
from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)


def download_prices(tickers: list[str], period: str = "2y") -> dict[str, pd.DataFrame]:
    """Batch-download adjusted OHLCV for many tickers. Returns {ticker: DataFrame}."""
    tickers = sorted(set(tickers))
    if not tickers:
        return {}
    raw = yf.download(tickers, period=period, auto_adjust=True, group_by="ticker", threads=True, progress=False)
    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            df = df.dropna(subset=["Close"])
            if len(df):
                out[t] = df
            else:
                log.warning("no data for %s", t)
        except KeyError:
            log.warning("ticker missing from download: %s", t)
    return out


def get_news(ticker: str, limit: int = 5) -> list[dict]:
    """Recent headlines from Yahoo. Handles both the old and new yfinance news payloads."""
    try:
        items = yf.Ticker(ticker).news or []
    except Exception as exc:  # network / parsing errors are not fatal
        log.warning("news failed for %s: %s", ticker, exc)
        return []
    out = []
    for it in items[:limit]:
        c = it.get("content", it) or {}
        title = c.get("title") or it.get("title")
        url = (c.get("canonicalUrl") or {}).get("url") or it.get("link")
        published = c.get("pubDate") or it.get("providerPublishTime")
        publisher = (c.get("provider") or {}).get("displayName") or it.get("publisher")
        if title:
            out.append({"title": title, "url": url, "published": str(published), "publisher": publisher})
    return out
