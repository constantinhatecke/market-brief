"""Tool-use loop tested against a fake Anthropic client; fallback tested for schema and length."""
import json
from types import SimpleNamespace

import pytest

from brief.analyst import Analyst, build_context, fallback_brief
from brief.config import Settings
from brief.render import reading_minutes, render_text
from brief.schemas import Brief


def _ctx():
    m = {"price": 100.0, "ret_1w": 0.02, "pct_vs_dma20": 0.03, "rsi14": 62.0, "atr_pct": 0.02, "mom_20": 0.08,
         "mom_40": 0.1, "rs_sector_20": 0.02, "rs_market_20": 0.03, "eps_rev_pct": 0.03, "vol_20": 0.3,
         "pct_from_20d_high": -0.01, "rel_volume": 1.4, "name": "Test Co", "next_earnings": "2026-10-20"}
    metrics = {t: dict(m) for t in ["AAA", "BBB", "CCC", "CL=F", "GC=F"]}
    regime = {"label": "risk-on", "spy_vs_200dma": 0.05, "spy_vs_50dma": 0.01, "vix": 16.0, "breadth_sectors_above_50dma": 0.7, "spy_vol_20": 0.12}
    rows = [{"ticker": "AAA", "shares": 10, "cost_basis": 90, "value": 1000, "pnl_pct": 0.11, "note": None}]
    return metrics, build_context("2026-09-17", regime, metrics, rows, ["BBB"], ["CCC"], ["CL=F", "GC=F"], 1200)


def test_fallback_brief_schema_and_length():
    metrics, ctx = _ctx()
    b = fallback_brief(ctx)
    assert isinstance(b, Brief) and b.portfolio[0].ticker == "AAA" and len(b.watchlist) == 2
    text = render_text(b, ctx["regime"], metrics, "2026-09-17")
    assert reading_minutes(text) <= 6.0


class FakeClient:
    """First call asks for detail + news, second call submits the brief."""
    def __init__(self):
        self.calls = 0
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kw):
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(content=[
                SimpleNamespace(type="tool_use", id="t1", name="get_ticker_detail", input={"ticker": "BBB"}),
                SimpleNamespace(type="tool_use", id="t2", name="get_news", input={"ticker": "BBB"}),
            ])
        if self.calls == 2:  # invalid submission first, to exercise validation feedback
            return SimpleNamespace(content=[SimpleNamespace(type="tool_use", id="t3", name="submit_brief", input={"headline": "x"})])
        tool_results = kw["messages"][-1]["content"]
        assert any(r.get("is_error") for r in tool_results)
        b = fallback_brief(json.loads(kw["messages"][0]["content"].split("Market data for this brief:\n")[1].split("\n\nInvestigate")[0]))
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", id="t4", name="submit_brief", input=b.model_dump())])


def test_tool_loop_with_fake_client():
    metrics, ctx = _ctx()
    client = FakeClient()
    a = Analyst(Settings(anthropic_api_key="x"), metrics, news_fn=lambda t: [{"title": "hello", "url": "u"}], client=client)
    b = a.run(ctx)
    assert isinstance(b, Brief)
    assert client.calls == 3
    assert {c["tool"] for c in a.tool_calls} == {"get_ticker_detail", "get_news"}


def test_loop_gives_up():
    metrics, ctx = _ctx()
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(content=[SimpleNamespace(type="text", text="thinking")])))
    with pytest.raises(RuntimeError):
        Analyst(Settings(anthropic_api_key="x"), metrics, client=client).run(ctx)
