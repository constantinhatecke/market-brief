from datetime import date

import pandas as pd

from brief.fundamentals import historical_pe, update_revisions


def test_historical_pe():
    inc = pd.DataFrame({pd.Timestamp("2025-12-31"): [5.0], pd.Timestamp("2024-12-31"): [4.0], pd.Timestamp("2023-12-31"): [2.0]}, index=["Diluted EPS"])
    close = pd.Series([80.0, 100.0, 120.0], index=pd.to_datetime(["2023-12-29", "2024-12-31", "2025-12-31"]))
    out = historical_pe(inc, close, trailing_pe=48.0)
    assert out["pe_hist_median"] == 25.0  # PEs 40, 25, 24 -> median 25
    assert abs(out["pe_vs_hist"] - 0.92) < 1e-9


def test_revisions_snapshot(tmp_path):
    snap = tmp_path / "estimates.json"
    fund = {"AAA": {"eps_est_cy": 10.0, "rev_est_cy": 1000.0, "eps_trend_30d_pct": 0.01}}
    update_revisions(fund, snap, today=date(2026, 8, 1))
    assert fund["AAA"]["eps_rev_pct"] == 0.01  # no baseline yet -> Yahoo trend fallback
    assert fund["AAA"]["rev_rev_pct"] is None
    fund = {"AAA": {"eps_est_cy": 11.0, "rev_est_cy": 1050.0, "eps_trend_30d_pct": 0.01}}
    update_revisions(fund, snap, today=date(2026, 9, 1))
    assert abs(fund["AAA"]["eps_rev_pct"] - 0.10) < 1e-9
    assert abs(fund["AAA"]["rev_rev_pct"] - 0.05) < 1e-9
    assert fund["AAA"]["rev_baseline_date"] == "2026-08-01"
