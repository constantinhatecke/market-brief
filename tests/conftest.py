import numpy as np
import pandas as pd
import pytest


def synthetic_ohlcv(n: int = 300, drift: float = 0.0005, vol: float = 0.015, seed: int = 0, start: float = 100.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, n)
    close = start * np.exp(np.cumsum(rets))
    high = close * (1 + rng.uniform(0, 0.01, n))
    low = close * (1 - rng.uniform(0, 0.01, n))
    opn = np.r_[close[0], close[:-1]]
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    idx = pd.bdate_range(end="2026-09-16", periods=n)
    return pd.DataFrame({"Open": opn, "High": high, "Low": low, "Close": close, "Volume": volume}, index=idx)


@pytest.fixture
def ohlcv():
    return synthetic_ohlcv()


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """Point config/state/output dirs at a temp folder so tests never touch real files."""
    cfg, st, out = tmp_path / "config", tmp_path / "state", tmp_path / "out"
    cfg.mkdir()
    monkeypatch.setenv("BRIEF_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("BRIEF_STATE_DIR", str(st))
    monkeypatch.setenv("BRIEF_OUTPUT_DIR", str(out))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("BRIEF_API_TOKEN", raising=False)
    (cfg / "portfolio.yaml").write_text("currency: USD\ncash: 0\npositions:\n  - ticker: AAA\n    shares: 10\n    cost_basis: 90\n")
    (cfg / "universe.yaml").write_text("stocks: [AAA, BBB, CCC, DDD, EEE, FFF]\n")
    return tmp_path
