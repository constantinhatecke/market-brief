"""HTML + plain-text rendering of a Brief, with reading-time estimate."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import ROOT
from .schemas import Brief

WPM = 220


def _pct(v, digits: int = 1) -> str:
    return "n/a" if v is None else f"{v * 100:+.{digits}f}%"


def _num(v, digits: int = 1) -> str:
    return "n/a" if v is None else f"{v:,.{digits}f}"


def links(ticker: str) -> dict[str, str]:
    t = ticker.replace("^", "%5E")
    return {
        "Yahoo": f"https://finance.yahoo.com/quote/{t}",
        "Finviz": f"https://finviz.com/quote.ashx?t={ticker.replace('-', '.')}",
        "TradingView": f"https://www.tradingview.com/symbols/{ticker.replace('=F', '1!').replace('-', '.')}",
    }


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    env.filters["pct"] = _pct
    env.filters["num"] = _num
    env.globals["links"] = links
    return env


def reading_minutes(text: str) -> float:
    return round(len(text.split()) / WPM, 1)


def render_text(brief: Brief, regime: dict, metrics: dict, date: str) -> str:
    lines = [f"MARKET BRIEF {date}", brief.headline, "", "REGIME", brief.regime_summary, "", "PORTFOLIO"]
    for p in brief.portfolio:
        m = metrics.get(p.ticker, {})
        lines.append(f"{p.ticker} [{p.status}] {_num(m.get('price'), 2)} 1w {_pct(m.get('ret_1w'))} | {p.note}")
    lines += ["", "WATCHLIST"]
    for w in brief.watchlist:
        lines += [f"{w.ticker} ({w.direction}) {w.thesis} Levels: {w.levels} Risk: {w.risk}"]
    lines += ["", "COMMODITIES"] + [f"{c.name}: {c.note}" for c in brief.commodities]
    lines += ["", "RISKS"] + [f"- {r}" for r in brief.risks]
    if brief.calendar:
        lines += ["", "CALENDAR"] + [f"- {c}" for c in brief.calendar]
    return "\n".join(lines)


def render_html(brief: Brief, regime: dict, metrics: dict, date: str, portfolio_rows: list[dict],
                reading: float, model: str | None) -> str:
    tpl = _env().get_template("email.html")
    return tpl.render(brief=brief, regime=regime, metrics=metrics, date=date,
                      portfolio_rows=portfolio_rows, reading=reading, model=model)
