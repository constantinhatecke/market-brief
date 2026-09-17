"""Fundamental fields from Yahoo plus the estimate-revision snapshot logic.

Yahoo serves current consensus estimates but not their history for revenue, so we
persist a small snapshot per run in state/estimates.json and compute revisions vs the
entry that is at least 21 days old (falling back to Yahoo's 30-day EPS trend when the
snapshot is too young)."""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

from .config import SECTOR_ETF
from .indicators import _f

log = logging.getLogger(__name__)

FIELDS = [
    "name", "sector", "sector_etf", "market_cap", "trailing_pe", "forward_pe",
    "eps_est_cy", "eps_growth_q", "eps_growth_cy", "eps_growth_ny",
    "eps_trend_30d_pct", "eps_rev_up30", "eps_rev_down30",
    "rev_est_cy", "rev_growth_cy",
    "pe_hist_median", "pe_vs_hist", "next_earnings",
]


def _get(df: pd.DataFrame | None, row: str, col: str) -> float | None:
    try:
        if df is None or df.empty:
            return None
        return _f(df.loc[row, col])
    except (KeyError, IndexError):
        return None


def fetch_fundamentals(ticker: str, close: pd.Series | None = None) -> dict:
    """Best effort: any block that fails returns None fields rather than raising."""
    f: dict = {k: None for k in FIELDS}
    t = yf.Ticker(ticker)

    try:
        info = t.info or {}
        f["name"] = info.get("shortName") or info.get("longName")
        f["sector"] = info.get("sector")
        f["sector_etf"] = SECTOR_ETF.get(f["sector"] or "")
        f["market_cap"] = _f(info.get("marketCap"))
        f["trailing_pe"] = _f(info.get("trailingPE"))
        f["forward_pe"] = _f(info.get("forwardPE"))
    except Exception as exc:
        log.warning("info failed %s: %s", ticker, exc)

    try:
        ee = t.earnings_estimate
        f["eps_est_cy"] = _get(ee, "0y", "avg")
        f["eps_growth_q"] = _get(ee, "0q", "growth")
        f["eps_growth_cy"] = _get(ee, "0y", "growth")
        f["eps_growth_ny"] = _get(ee, "+1y", "growth")
    except Exception as exc:
        log.debug("earnings_estimate failed %s: %s", ticker, exc)

    try:
        et = t.eps_trend
        cur, ago = _get(et, "0y", "current"), _get(et, "0y", "30daysAgo")
        if cur and ago:
            f["eps_trend_30d_pct"] = cur / ago - 1
    except Exception as exc:
        log.debug("eps_trend failed %s: %s", ticker, exc)

    try:
        er = t.eps_revisions
        f["eps_rev_up30"] = _get(er, "0y", "upLast30days")
        f["eps_rev_down30"] = _get(er, "0y", "downLast30days")
    except Exception as exc:
        log.debug("eps_revisions failed %s: %s", ticker, exc)

    try:
        re_ = t.revenue_estimate
        f["rev_est_cy"] = _get(re_, "0y", "avg")
        f["rev_growth_cy"] = _get(re_, "0y", "growth")
    except Exception as exc:
        log.debug("revenue_estimate failed %s: %s", ticker, exc)

    try:
        cal = t.calendar or {}
        ed = cal.get("Earnings Date")
        if ed:
            f["next_earnings"] = str(ed[0] if isinstance(ed, list) else ed)
    except Exception as exc:
        log.debug("calendar failed %s: %s", ticker, exc)

    try:
        f.update(historical_pe(t.income_stmt, close, f["trailing_pe"]))
    except Exception as exc:
        log.debug("historical pe failed %s: %s", ticker, exc)

    return f


def historical_pe(income_stmt: pd.DataFrame | None, close: pd.Series | None, trailing_pe: float | None) -> dict:
    """P/E at each fiscal year end from annual diluted EPS, compared with today's trailing P/E."""
    out = {"pe_hist_median": None, "pe_vs_hist": None}
    if income_stmt is None or income_stmt.empty or close is None or "Diluted EPS" not in income_stmt.index:
        return out
    eps = income_stmt.loc["Diluted EPS"].dropna()
    close = close.dropna()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    pes = []
    for dt, e in eps.items():
        e = _f(e)
        if not e or e <= 0:
            continue
        px = close.loc[: pd.Timestamp(dt).tz_localize(None)]
        if len(px):
            pes.append(float(px.iloc[-1]) / e)
    if len(pes) >= 2:
        med = float(pd.Series(pes).median())
        out["pe_hist_median"] = med
        if trailing_pe and med > 0:
            out["pe_vs_hist"] = trailing_pe / med - 1
    return out


def _pct(cur: float | None, base: float | None) -> float | None:
    if cur is None or not base:
        return None
    return cur / base - 1


def update_revisions(fund: dict[str, dict], snapshot_path: Path, today: date | None = None, min_age_days: int = 21) -> None:
    """Mutates fund[t] in place with eps_rev_pct / rev_rev_pct and updates the snapshot file."""
    today = today or date.today()
    snap: dict[str, list[dict]] = {}
    if snapshot_path.exists():
        snap = json.loads(snapshot_path.read_text())

    for t, f in fund.items():
        hist = snap.get(t, [])
        old = [h for h in hist if (today - date.fromisoformat(h["date"])).days >= min_age_days]
        base = old[-1] if old else (hist[0] if hist else None)
        if base and (today - date.fromisoformat(base["date"])).days >= 1:
            f["eps_rev_pct"] = _pct(f.get("eps_est_cy"), base.get("eps_est_cy"))
            f["rev_rev_pct"] = _pct(f.get("rev_est_cy"), base.get("rev_est_cy"))
            f["rev_baseline_date"] = base["date"]
        else:
            f["eps_rev_pct"] = f.get("eps_trend_30d_pct")
            f["rev_rev_pct"] = None
            f["rev_baseline_date"] = None
        if f.get("eps_rev_pct") is None:
            f["eps_rev_pct"] = f.get("eps_trend_30d_pct")

        if not hist or hist[-1]["date"] != today.isoformat():
            hist.append({"date": today.isoformat(), "eps_est_cy": f.get("eps_est_cy"), "rev_est_cy": f.get("rev_est_cy")})
        snap[t] = hist[-40:]

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snap, indent=1))
