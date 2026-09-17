"""Settings, paths and static reference data."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent


def config_dir() -> Path:
    return Path(os.environ.get("BRIEF_CONFIG_DIR", ROOT / "config"))


def state_dir() -> Path:
    p = Path(os.environ.get("BRIEF_STATE_DIR", ROOT / "state"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def output_dir() -> Path:
    p = Path(os.environ.get("BRIEF_OUTPUT_DIR", ROOT / "outputs"))
    p.mkdir(parents=True, exist_ok=True)
    return p


BENCHMARK = "SPY"
VIX = "^VIX"

# Yahoo sector name -> SPDR sector ETF used for "stock vs sector"
SECTOR_ETF = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

COMMODITIES = {
    "CL=F": "WTI crude",
    "BZ=F": "Brent crude",
    "NG=F": "Natural gas",
    "GC=F": "Gold",
    "SI=F": "Silver",
    "HG=F": "Copper",
    "ZW=F": "Wheat",
    "ZC=F": "Corn",
}


class Settings(BaseModel):
    anthropic_api_key: str | None = None
    model: str = "claude-sonnet-4-6"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_password: str | None = None
    email_from: str | None = None
    email_to: str | None = None
    api_token: str | None = None
    watchlist_size: int = 6
    min_dollar_volume: float = 2e7  # 20-day average traded value, USD
    target_words: int = 1250  # roughly 6 minutes at 220 wpm including tables


def load_settings() -> Settings:
    e = os.environ
    return Settings(
        anthropic_api_key=e.get("ANTHROPIC_API_KEY"),
        model=e.get("BRIEF_MODEL", "claude-sonnet-4-6"),
        smtp_host=e.get("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(e.get("SMTP_PORT", "465")),
        smtp_user=e.get("SMTP_USER"),
        smtp_password=e.get("SMTP_PASSWORD"),
        email_from=e.get("EMAIL_FROM") or e.get("SMTP_USER"),
        email_to=e.get("EMAIL_TO"),
        api_token=e.get("BRIEF_API_TOKEN"),
        watchlist_size=int(e.get("BRIEF_WATCHLIST_SIZE", "6")),
    )


def read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def portfolio_path() -> Path:
    return config_dir() / "portfolio.yaml"


def universe_path() -> Path:
    return config_dir() / "universe.yaml"
