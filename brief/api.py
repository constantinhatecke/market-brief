"""FastAPI surface: portfolio CRUD, on-demand brief, metrics lookup."""
from __future__ import annotations

import logging
from datetime import date

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException

from . import pipeline
from .config import load_settings, portfolio_path, write_yaml
from .data import download_prices
from .indicators import compute_technicals, setup_tags
from .schemas import Portfolio, Position

log = logging.getLogger(__name__)
app = FastAPI(title="Market Brief", version="1.0.0",
              description="LLM-backed service producing structured stock and commodity briefs.")


def require_token(x_api_token: str | None = Header(default=None)) -> None:
    expected = load_settings().api_token
    if expected and x_api_token != expected:
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Token")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "date": date.today().isoformat()}


@app.get("/portfolio", response_model=Portfolio)
def get_portfolio() -> Portfolio:
    return pipeline.load_portfolio()


@app.put("/portfolio", response_model=Portfolio, dependencies=[Depends(require_token)])
def replace_portfolio(p: Portfolio) -> Portfolio:
    write_yaml(portfolio_path(), p.model_dump())
    return p


@app.post("/portfolio/positions", response_model=Portfolio, dependencies=[Depends(require_token)])
def upsert_position(pos: Position) -> Portfolio:
    p = pipeline.load_portfolio()
    p.positions = [x for x in p.positions if x.ticker != pos.ticker] + [pos]
    write_yaml(portfolio_path(), p.model_dump())
    return p


@app.delete("/portfolio/positions/{ticker}", response_model=Portfolio, dependencies=[Depends(require_token)])
def delete_position(ticker: str) -> Portfolio:
    p = pipeline.load_portfolio()
    before = len(p.positions)
    p.positions = [x for x in p.positions if x.ticker != ticker.upper()]
    if len(p.positions) == before:
        raise HTTPException(status_code=404, detail=f"{ticker.upper()} not in portfolio")
    write_yaml(portfolio_path(), p.model_dump())
    return p


@app.post("/brief/run", dependencies=[Depends(require_token)])
def run_brief(send: bool = False, background: bool = False, tasks: BackgroundTasks = None) -> dict:
    """Generate a brief now. background=true returns immediately (the run takes a few minutes)."""
    if background:
        tasks.add_task(pipeline.run, send)
        return {"status": "started", "send": send}
    r = pipeline.run(send=send)
    return {"status": "done", "sent": r.sent, "reading_minutes": r.reading_minutes,
            "headline": r.brief.headline, "brief": r.brief.model_dump()}


@app.get("/brief/latest")
def latest_brief() -> dict:
    r = pipeline.last_result()
    if r is None:
        raise HTTPException(status_code=404, detail="no brief generated yet")
    return r


@app.get("/metrics/{ticker}")
def ticker_metrics(ticker: str) -> dict:
    """Technical + risk fields for any ticker, computed live."""
    t = ticker.upper()
    prices = download_prices([t], period="1y")
    if t not in prices:
        raise HTTPException(status_code=404, detail=f"no data for {t}")
    m = compute_technicals(prices[t])
    return {"ticker": t, **m, "tags": setup_tags(m)}
