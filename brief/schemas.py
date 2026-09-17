"""Pydantic models: portfolio input and the structured brief the LLM must return."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Position(BaseModel):
    ticker: str
    shares: float = Field(gt=0)
    cost_basis: float | None = Field(default=None, ge=0)
    note: str | None = None

    @field_validator("ticker")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.strip().upper()


class Portfolio(BaseModel):
    currency: str = "USD"
    cash: float = 0.0
    positions: list[Position] = []

    def tickers(self) -> list[str]:
        return [p.ticker for p in self.positions]


class PortfolioNote(BaseModel):
    ticker: str
    status: Literal["hold", "watch", "review"] = Field(
        description="hold = nothing to do; watch = a level or event is close; review = thesis or risk has changed"
    )
    note: str = Field(description="Two sentences max. Reference specific numbers from the data.")


class WatchItem(BaseModel):
    ticker: str
    name: str | None = None
    direction: Literal["bullish", "bearish", "neutral"]
    thesis: str = Field(description="Why it matters this week, 2 to 3 sentences, numbers included")
    levels: str = Field(description="Key price levels: 20DMA, 20-day high, ATR-based stop distance")
    risk: str = Field(description="What breaks the setup, one sentence")


class CommodityNote(BaseModel):
    ticker: str
    name: str
    note: str = Field(description="One or two sentences on trend, momentum and what to watch")


class Brief(BaseModel):
    headline: str = Field(description="One line, under 15 words, the week's main point")
    regime_summary: str = Field(description="3 to 4 sentences on market regime, volatility and breadth")
    portfolio: list[PortfolioNote]
    watchlist: list[WatchItem] = Field(description="4 to 7 names, mix of bullish and bearish")
    commodities: list[CommodityNote] = Field(description="3 to 5 commodities worth a line")
    risks: list[str] = Field(description="3 to 5 concrete risk flags for the coming days")
    calendar: list[str] = Field(default_factory=list, description="Known events this week, if any")


class BriefResult(BaseModel):
    generated_at: str
    regime: dict
    brief: Brief
    metrics: dict[str, dict]
    html: str
    text: str
    reading_minutes: float
    sent: bool = False
    model: str | None = None
