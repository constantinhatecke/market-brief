"""LLM analyst: tool-using loop that ends with a validated structured Brief.

Flow: compact context in -> model may call get_ticker_detail / get_news -> model calls
submit_brief -> Pydantic validates -> Brief. If ANTHROPIC_API_KEY is absent a rule-based
fallback produces the same schema so the pipeline and tests run offline."""
from __future__ import annotations

import json
import logging
from typing import Callable

from pydantic import ValidationError

from .config import COMMODITIES, Settings
from .indicators import setup_tags
from .schemas import Brief, CommodityNote, PortfolioNote, WatchItem

log = logging.getLogger(__name__)

SYSTEM = """You are a senior buy-side analyst writing a twice-weekly brief for one experienced reader
who manages his own portfolio. Tone: direct, specific, professional, no hype.

Rules:
- Use only the numbers in the data provided or returned by tools. Never invent prices, dates or estimates.
- Every claim about a stock cites at least one number (price vs 20DMA, RSI, ATR, momentum, revision, P/E vs history).
- Read the setups through the market regime: the same breakout means different things in risk-on and risk-off tape.
- Frame observations and levels; do not tell the reader what to buy or sell. "Worth watching if X" is fine, "buy now" is not.
- Length budget for the whole brief: about {words} words. The reader gives it six minutes.
- Style: short sentences. No em-dashes, use commas or full stops. No compound marketing adjectives
  (no "game-changing", "cutting-edge"). No filler ("in today's dynamic environment"). No preambles.
- Use tools for at most 6 tickers: the ones where news or a fuller metric set would change the note.
- Finish by calling submit_brief exactly once with the complete brief."""

COMPACT_KEYS = [
    "price", "ret_1w", "pct_vs_dma20", "pct_vs_dma40", "pct_vs_dma100", "dma_stack", "rsi14", "atr_pct",
    "pct_from_20d_high", "rel_volume", "mom_20", "mom_40", "vol_20", "rs_sector_20", "rs_market_20",
    "eps_growth_cy", "eps_rev_pct", "rev_rev_pct", "pe_vs_hist", "trailing_pe", "next_earnings", "score",
]


def _round(v):
    return round(v, 4) if isinstance(v, float) else v


def compact(m: dict, keys: list[str] = COMPACT_KEYS) -> dict:
    out = {k: _round(m[k]) for k in keys if m.get(k) is not None}
    out["tags"] = setup_tags(m)
    return out


def build_context(today: str, regime: dict, metrics: dict[str, dict], portfolio_rows: list[dict],
                  watch_up: list[str], watch_down: list[str], commodities: list[str], words: int) -> dict:
    return {
        "date": today,
        "word_budget": words,
        "regime": {k: _round(v) for k, v in regime.items() if k != "notes"},
        "portfolio": [
            {**row, **compact(metrics.get(row["ticker"], {}))} for row in portfolio_rows
        ],
        "screen_leaders": {t: {"name": metrics[t].get("name"), **compact(metrics[t])} for t in watch_up if t in metrics},
        "screen_laggards": {t: {"name": metrics[t].get("name"), **compact(metrics[t])} for t in watch_down if t in metrics},
        "commodities": {t: {"name": COMMODITIES.get(t, t), **compact(metrics[t])} for t in commodities if t in metrics},
    }


def tool_definitions() -> list[dict]:
    return [
        {
            "name": "get_ticker_detail",
            "description": "Full metric set for one ticker (all technical, fundamental, relative and risk fields).",
            "input_schema": {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]},
        },
        {
            "name": "get_news",
            "description": "Up to 5 recent headlines with URLs for a ticker.",
            "input_schema": {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]},
        },
        {
            "name": "submit_brief",
            "description": "Submit the final brief. Call exactly once when the analysis is complete.",
            "input_schema": Brief.model_json_schema(),
        },
    ]


class Analyst:
    def __init__(self, settings: Settings, metrics: dict[str, dict],
                 news_fn: Callable[[str], list[dict]] | None = None, client=None):
        self.settings = settings
        self.metrics = metrics
        self.news_fn = news_fn
        self.client = client
        self.tool_calls: list[dict] = []

    def _call_tool(self, name: str, args: dict):
        t = str(args.get("ticker", "")).upper()
        self.tool_calls.append({"tool": name, "ticker": t})
        if name == "get_ticker_detail":
            m = self.metrics.get(t)
            return {k: _round(v) for k, v in m.items()} if m else {"error": f"unknown ticker {t}"}
        if name == "get_news":
            return self.news_fn(t) if self.news_fn else []
        return {"error": f"unknown tool {name}"}

    def run(self, context: dict) -> Brief:
        if self.client is None:
            if not self.settings.anthropic_api_key:
                log.warning("no ANTHROPIC_API_KEY, using rule-based fallback brief")
                return fallback_brief(context)
            import anthropic  # imported lazily so tests do not need credentials
            self.client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)

        system = SYSTEM.format(words=context.get("word_budget", self.settings.target_words))
        messages = [{"role": "user", "content": "Market data for this brief:\n" + json.dumps(context, default=str)
                     + "\n\nInvestigate what you need, then call submit_brief."}]
        for _ in range(14):
            resp = self.client.messages.create(
                model=self.settings.model, max_tokens=6000, system=system,
                tools=tool_definitions(), messages=messages,
            )
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                if block.name == "submit_brief":
                    try:
                        return Brief.model_validate(block.input)
                    except ValidationError as exc:
                        results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                        "content": f"Schema validation failed, fix and resubmit: {exc}"})
                        continue
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps(self._call_tool(block.name, block.input), default=str)})
            if results:
                messages.append({"role": "user", "content": results})
            else:
                messages.append({"role": "user", "content": "Call submit_brief now with the complete brief."})
        raise RuntimeError("LLM did not submit a brief within the iteration limit")


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:+.1f}%"


def _n(v, d: int = 1) -> str:
    return "n/a" if v is None else f"{v:,.{d}f}"


def fallback_brief(ctx: dict) -> Brief:
    """Deterministic brief from the data alone. Same schema, no LLM."""
    r = ctx.get("regime", {})
    regime = (
        f"Regime is {r.get('label', 'unknown')}. SPY is {_pct(r.get('spy_vs_200dma'))} vs its 200DMA and "
        f"{_pct(r.get('spy_vs_50dma'))} vs the 50DMA. VIX at {_n(r.get('vix'))}. "
        f"{round((r.get('breadth_sectors_above_50dma') or 0) * 100)}% of sectors trade above their 50DMA."
    )
    portfolio = []
    for row in ctx.get("portfolio", []):
        tags = row.get("tags", [])
        status = "review" if any(t in tags for t in ("EPS estimates cut", "bearish MA stack", "revenue estimates cut")) \
            else "watch" if any(t in tags for t in ("overbought RSI", "oversold RSI", "at 20-day high", "breakout on volume")) else "hold"
        portfolio.append(PortfolioNote(
            ticker=row["ticker"], status=status,
            note=f"Price {_n(row.get('price'), 2)}, {_pct(row.get('pct_vs_dma20'))} vs 20DMA, RSI {_n(row.get('rsi14'), 0)}, "
                 f"20d momentum {_pct(row.get('mom_20'))}. Flags: {', '.join(tags) or 'none'}."))

    def item(t: str, m: dict, direction: str) -> WatchItem:
        return WatchItem(
            ticker=t, name=m.get("name"), direction=direction,
            thesis=f"Screen rank driven by 20d momentum {_pct(m.get('mom_20'))}, sector relative {_pct(m.get('rs_sector_20'))}, "
                   f"EPS revision {_pct(m.get('eps_rev_pct'))}. Flags: {', '.join(m.get('tags', [])) or 'none'}.",
            levels=f"20DMA {_pct(m.get('pct_vs_dma20'))} away, {_pct(m.get('pct_from_20d_high'))} from 20-day high, "
                   f"ATR {_pct(m.get('atr_pct'))} of price.",
            risk="Setup fails on a close below the 20DMA on above-average volume." if direction == "bullish"
                 else "Reverses if estimates stabilise and price reclaims the 20DMA.")

    watch = [item(t, m, "bullish") for t, m in ctx.get("screen_leaders", {}).items()]
    watch += [item(t, m, "bearish") for t, m in ctx.get("screen_laggards", {}).items()]
    comms = [CommodityNote(ticker=t, name=m.get("name", t),
                           note=f"20d momentum {_pct(m.get('mom_20'))}, {_pct(m.get('pct_vs_dma40'))} vs 40DMA, RSI {_n(m.get('rsi14'), 0)}, "
                                f"realised vol {_pct(m.get('vol_20'))}.")
             for t, m in list(ctx.get("commodities", {}).items())[:5]]
    risks = [f"Market regime: {r.get('label', 'unknown')}; VIX {_n(r.get('vix'))}."]
    if (r.get("spy_vol_20") or 0) > 0.2:
        risks.append(f"SPY realised volatility elevated at {_pct(r.get('spy_vol_20'))} annualised.")
    for row in ctx.get("portfolio", []):
        if row.get("next_earnings"):
            risks.append(f"{row['ticker']} reports around {row['next_earnings']}.")
    return Brief(headline=f"{r.get('label', 'Market').capitalize()} tape, {len(watch)} screen names, {len(portfolio)} positions reviewed",
                 regime_summary=regime, portfolio=portfolio, watchlist=watch, commodities=comms, risks=risks[:5])
