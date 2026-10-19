"""Unit tests for the pandas aggregation layer (ported metrics)."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from app.services import metrics
from tests.conftest import make_catalog_df


def _event_df(times: list[dt.datetime]) -> pd.DataFrame:
    return pd.DataFrame({
        "REQUEST_HIT_DATETIME": times,
        "HEAD_NOD_REQUEST_HIT_DATETIME": [None] * len(times),
    })


def test_kpi_summary_counts_and_rates():
    df = make_catalog_df(n=6)
    kpis = metrics.kpi_summary(df)
    assert kpis["total_txns"] == 6
    assert kpis["callback_success_rate"] == 50.0
    assert kpis["avg_callback_latency"] == 1.0


def test_kpi_summary_empty():
    kpis = metrics.kpi_summary(pd.DataFrame())
    assert kpis == {"total_txns": 0, "callback_success_rate": None, "avg_callback_latency": None}


def test_time_series_buckets_by_granularity():
    day = dt.date(2026, 10, 1)
    df = _event_df([
        dt.datetime(2026, 10, 1, 9, 5),
        dt.datetime(2026, 10, 1, 9, 20),
        dt.datetime(2026, 10, 1, 9, 50),
        dt.datetime(2026, 10, 1, 10, 5),
    ])
    out = metrics.time_series(df, day, day, "30m")
    by_bucket = {r["bucket"]: r["count"] for r in out}
    assert by_bucket["2026-10-01T09:00:00"] == 2
    assert by_bucket["2026-10-01T09:30:00"] == 1
    assert by_bucket["2026-10-01T10:00:00"] == 1
    # delta_pct: first is None, then -50.0 (2 -> 1), then 0.0 (1 -> 1)
    deltas = [r["delta_pct"] for r in out]
    assert deltas == [None, -50.0, 0.0]


def test_time_series_respects_time_of_day_window():
    day = dt.date(2026, 10, 1)
    df = _event_df([
        dt.datetime(2026, 10, 1, 9, 5),
        dt.datetime(2026, 10, 1, 9, 20),
        dt.datetime(2026, 10, 1, 14, 0),
    ])
    out = metrics.time_series(df, day, day, "30m", start_time="09:00", end_time="09:30")
    assert sum(r["count"] for r in out) == 2


def test_time_series_auto_uses_daily_for_long_windows():
    start = dt.date(2026, 9, 1)
    end = dt.date(2026, 10, 1)
    df = _event_df([dt.datetime(2026, 9, 15, 12, 0)])
    out = metrics.time_series(df, start, end, "auto")
    assert out and out[0]["bucket"] == "2026-09-15"


def test_time_series_empty_df():
    assert metrics.time_series(pd.DataFrame(), dt.date(2026, 10, 1), dt.date(2026, 10, 1)) == []


def test_stage_status_breakdown():
    out = metrics.stage_status_breakdown(make_catalog_df(n=4), "Callback")
    statuses = {r["status"]: r["count"] for r in out}
    assert statuses == {"PASSED": 2, "FAILED": 2}


def test_fraud_attempt_breakdown_labels():
    out = metrics.fraud_attempt_breakdown(make_catalog_df(n=4))
    labels = {r["status"]: r["count"] for r in out}
    assert labels == {"FRAUD": 1, "GENUINE": 2, "NULL": 1}


def test_user_review_breakdown_labels():
    out = metrics.user_review_breakdown(make_catalog_df(n=4))
    labels = {r["status"]: r["count"] for r in out}
    assert labels == {"ACCEPT": 1, "REVIEW PENDING": 1, "REJECTED": 1, "NULL": 1}


def test_latency_box_stats():
    stats = {r["stage"]: r for r in metrics.box_stats(make_catalog_df(n=3))}
    blink = stats["Blink"]
    assert blink["mean"] == 0.5
    assert blink["min"] == 0.5 and blink["max"] == 0.5
    assert blink["q1"] == 0.5 and blink["q3"] == 0.5
    assert blink["n"] == 3


def test_exception_rows_only_for_non_null():
    rows = metrics.exception_rows(make_catalog_df(n=3))
    assert len(rows) == 1
    assert rows[0]["TXN_ID"].endswith("~1")
    assert rows[0]["EXCEPTION_MESSAGE"] == "boom"


def test_build_dashboard_shape_and_json_safe():
    payload = metrics.build_dashboard(make_catalog_df(n=2))
    assert set(payload) == {"kpis", "time_series", "stage_breakdown", "latency", "exceptions"}
    assert set(payload["stage_breakdown"]) == set(metrics.STAGES) | {"Fraud Attempt", "User Review"}
    assert "stats" in payload["latency"] and "raw" not in payload["latency"]
    assert isinstance(payload["kpis"]["total_txns"], int)
    # No numpy/NaN leakage.
    import json

    json.dumps(payload)
