"""Cross-sectional ranking of the universe. Deterministic, so the LLM writes about
names that a transparent rule selected, not names it hallucinated."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

WEIGHTS = {
    "mom_20": 0.25,
    "mom_40": 0.15,
    "rs_sector_20": 0.15,
    "rs_market_20": 0.10,
    "eps_rev_pct": 0.15,
    "rev_rev_pct": 0.10,
    "rel_volume": 0.10,
}


def zscore(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    sd = s.std()
    if not sd or math.isnan(sd):
        return s * 0.0
    return (s - s.mean()) / sd


def build_table(metrics: dict[str, dict]) -> pd.DataFrame:
    df = pd.DataFrame.from_dict(metrics, orient="index")
    for c in list(WEIGHTS) + ["rsi14", "pct_from_20d_high", "avg_dollar_vol_20", "vol_20"]:
        if c not in df.columns:
            df[c] = np.nan
    return df


def score_table(metrics: dict[str, dict]) -> pd.DataFrame:
    df = build_table(metrics)
    score = pd.Series(0.0, index=df.index)
    for col, w in WEIGHTS.items():
        s = df[col].astype(float)
        filled = s.fillna(s.median() if s.notna().any() else 0.0)
        score = score + w * zscore(filled).clip(-3, 3)
    score[df["rsi14"] >= 75] -= 0.5
    score[(df["pct_from_20d_high"] >= -0.02) & (df["rel_volume"] >= 1.2)] += 0.25
    df["score"] = score
    return df.sort_values("score", ascending=False)


def select_candidates(df: pd.DataFrame, n: int, min_dollar_volume: float, exclude: set[str] | None = None) -> tuple[list[str], list[str]]:
    """Top names (long side) and bottom names (deteriorating) among liquid, non-portfolio tickers."""
    exclude = exclude or set()
    liquid = df[(df["avg_dollar_vol_20"].fillna(0) >= min_dollar_volume) & ~df.index.isin(exclude)]
    n_up = max(1, math.ceil(n * 2 / 3))
    up = list(liquid.head(n_up).index)
    down = [t for t in liquid.tail(n - n_up).index if t not in up]
    return up, down
