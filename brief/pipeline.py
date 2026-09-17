"""Orchestration: data -> metrics -> ranking -> LLM -> email."""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

import pandas as pd

from . import data as data_mod
from .analyst import Analyst, build_context
from .config import BENCHMARK, COMMODITIES, SECTOR_ETF, VIX, Settings, load_settings, output_dir, portfolio_path, read_yaml, state_dir, universe_path
from .fundamentals import fetch_fundamentals, update_revisions
from .indicators import compute_technicals
from .mailer import send_email
from .regime import compute_regime
from .render import reading_minutes, render_html, render_text
from .schemas import BriefResult, Portfolio
from .scoring import score_table, select_candidates

log = logging.getLogger(__name__)


def load_portfolio() -> Portfolio:
    return Portfolio.model_validate(read_yaml(portfolio_path()) or {})


def load_universe() -> list[str]:
    return [t.upper() for t in (read_yaml(universe_path()).get("stocks") or [])]


def _relative(m: dict, prices: dict[str, pd.DataFrame], tech: dict[str, dict]) -> None:
    """Stock vs sector ETF and vs SPY over 20 and 40 days."""
    spy = tech.get(BENCHMARK, {})
    sec = tech.get(m.get("sector_etf") or "", {})
    for n in (20, 40):
        mom = m.get(f"mom_{n}")
        m[f"rs_market_{n}"] = None if mom is None or spy.get(f"mom_{n}") is None else mom - spy[f"mom_{n}"]
        m[f"rs_sector_{n}"] = None if mom is None or sec.get(f"mom_{n}") is None else mom - sec[f"mom_{n}"]


def run(send: bool = False, settings: Settings | None = None, today: date | None = None,
        fetch_fundamentals_fn=fetch_fundamentals, download_fn=data_mod.download_prices,
        news_fn=data_mod.get_news, client=None) -> BriefResult:
    settings = settings or load_settings()
    today = today or date.today()
    portfolio = load_portfolio()
    universe = load_universe()
    stocks = sorted(set(universe) | set(portfolio.tickers()))
    all_tickers = stocks + list(COMMODITIES) + list(SECTOR_ETF.values()) + [BENCHMARK, VIX]

    log.info("downloading prices for %d tickers", len(all_tickers))
    prices = download_fn(all_tickers)

    tech = {t: compute_technicals(df) for t, df in prices.items() if len(df) >= 30}

    log.info("fetching fundamentals for %d stocks", len(stocks))
    with ThreadPoolExecutor(max_workers=8) as ex:
        fund = dict(zip(stocks, ex.map(lambda t: fetch_fundamentals_fn(t, prices.get(t, pd.DataFrame()).get("Close")), stocks)))
    update_revisions(fund, state_dir() / "estimates.json", today)

    metrics: dict[str, dict] = {}
    for t in prices:
        m = {**tech.get(t, {}), **fund.get(t, {})}
        _relative(m, prices, tech)
        metrics[t] = m

    regime = compute_regime(prices)

    universe_metrics = {t: metrics[t] for t in stocks if t in metrics and metrics[t].get("price")}
    table = score_table(universe_metrics)
    for t, s in table["score"].items():
        metrics[t]["score"] = float(s)
    up, down = select_candidates(table, settings.watchlist_size, settings.min_dollar_volume, set(portfolio.tickers()))

    portfolio_rows = []
    for p in portfolio.positions:
        m = metrics.get(p.ticker, {})
        px = m.get("price")
        portfolio_rows.append({
            "ticker": p.ticker, "shares": p.shares, "cost_basis": p.cost_basis,
            "value": None if px is None else px * p.shares,
            "pnl_pct": None if px is None or not p.cost_basis else px / p.cost_basis - 1,
            "note": p.note,
        })

    ctx = build_context(today.isoformat(), regime, metrics, portfolio_rows, up, down, list(COMMODITIES), settings.target_words)
    analyst = Analyst(settings, metrics, news_fn=news_fn, client=client)
    brief = analyst.run(ctx)
    used_model = settings.model if (settings.anthropic_api_key or client) else None

    text = render_text(brief, regime, metrics, today.isoformat())
    minutes = reading_minutes(text)
    html = render_html(brief, regime, metrics, today.isoformat(), portfolio_rows, minutes, used_model)

    result = BriefResult(generated_at=datetime.now(timezone.utc).isoformat(), regime=regime, brief=brief,
                         metrics={t: metrics[t] for t in set(up) | set(down) | set(portfolio.tickers()) | set(COMMODITIES) if t in metrics},
                         html=html, text=text, reading_minutes=minutes, model=used_model)

    (output_dir() / f"brief_{today.isoformat()}.html").write_text(html)
    (state_dir() / "last_brief.json").write_text(result.model_dump_json(indent=1, exclude={"html"}))

    if send:
        send_email(settings, f"Market brief {today.isoformat()}: {brief.headline}", html, text)
        result.sent = True
        log.info("email sent to %s", settings.email_to)
    return result


def last_result() -> dict | None:
    p = state_dir() / "last_brief.json"
    return json.loads(p.read_text()) if p.exists() else None
