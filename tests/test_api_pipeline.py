"""End-to-end pipeline with mocked network, and the FastAPI surface."""
from datetime import date

import pandas as pd
from fastapi.testclient import TestClient

from brief import pipeline
from brief.api import app
from brief.config import COMMODITIES, SECTOR_ETF, Settings
from tests.conftest import synthetic_ohlcv


def fake_download(tickers, period="2y"):
    return {t: synthetic_ohlcv(300, drift=0.0005 * (i % 5 - 2), seed=i, start=15 if t == "^VIX" else 100)
            for i, t in enumerate(sorted(set(tickers)))}


def fake_fund(ticker, close=None):
    return {"name": f"{ticker} Inc", "sector": "Technology", "sector_etf": "XLK", "trailing_pe": 20.0,
            "eps_est_cy": 5.0, "rev_est_cy": 1e9, "eps_growth_cy": 0.1, "eps_trend_30d_pct": 0.02, "next_earnings": "2026-10-20"}


def test_pipeline_end_to_end(isolated_dirs):
    res = pipeline.run(send=False, settings=Settings(watchlist_size=3), today=date(2026, 9, 17),
                       fetch_fundamentals_fn=fake_fund, download_fn=fake_download, news_fn=lambda t: [])
    assert res.sent is False and res.reading_minutes <= 6
    assert "AAA" in res.metrics and "CL=F" in res.metrics
    w = res.brief.watchlist[0].ticker
    assert res.metrics[w]["rs_sector_20"] is not None and res.metrics[w]["rs_market_20"] is not None  # relative metrics computed
    assert (isolated_dirs / "state" / "estimates.json").exists()
    assert (isolated_dirs / "state" / "last_brief.json").exists()
    assert "<html" in res.html and "AAA" in res.html
    assert len(res.brief.watchlist) == 3


def test_api_portfolio_crud(isolated_dirs):
    c = TestClient(app)
    assert c.get("/health").json()["status"] == "ok"
    assert c.get("/portfolio").json()["positions"][0]["ticker"] == "AAA"
    r = c.post("/portfolio/positions", json={"ticker": "bbb", "shares": 2, "cost_basis": 50})
    assert r.status_code == 200 and {p["ticker"] for p in r.json()["positions"]} == {"AAA", "BBB"}
    r = c.post("/portfolio/positions", json={"ticker": "bbb", "shares": 4})
    assert [p for p in r.json()["positions"] if p["ticker"] == "BBB"][0]["shares"] == 4  # upsert
    assert c.delete("/portfolio/positions/aaa").status_code == 200
    assert c.delete("/portfolio/positions/aaa").status_code == 404
    assert c.post("/portfolio/positions", json={"ticker": "X", "shares": 0}).status_code == 422


def test_api_token_required(isolated_dirs, monkeypatch):
    monkeypatch.setenv("BRIEF_API_TOKEN", "s3cret")
    c = TestClient(app)
    assert c.post("/portfolio/positions", json={"ticker": "Z", "shares": 1}).status_code == 401
    assert c.post("/portfolio/positions", json={"ticker": "Z", "shares": 1}, headers={"X-API-Token": "s3cret"}).status_code == 200


def test_api_run_and_latest(isolated_dirs, monkeypatch):
    c = TestClient(app)
    assert c.get("/brief/latest").status_code == 404
    monkeypatch.setattr(pipeline, "run", lambda send=False, **kw: pipeline.run.__wrapped__(send=send, settings=Settings(watchlist_size=2),
                        fetch_fundamentals_fn=fake_fund, download_fn=fake_download, news_fn=lambda t: []))
    pipeline.run.__wrapped__ = _orig_run
    r = c.post("/brief/run", params={"send": "false"})
    assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["sent"] is False
    assert c.get("/brief/latest").json()["brief"]["headline"] == r.json()["headline"]


_orig_run = pipeline.run
