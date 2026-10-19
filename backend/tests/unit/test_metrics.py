"""Unit tests for the pandas aggregation layer (ported metrics)."""
from __future__ import annotations

import pandas as pd

from app.services import metrics
from tests.conftest import make_catalog_df


def test_kpi_summary_counts_and_rates():
    df = make_catalog_df(n=6)
    kpis = metrics.kpi_summary(df)
    assert kpis["total_txns"] == 6
    assert kpis["callback_success_rate"] == 50.0
    assert kpis["avg_callback_latency"] == 1.0


def test_kpi_summary_empty():
    kpis = metrics.kpi_summary(pd.DataFrame())
    assert kpis == {"total_txns": 0, "callback_success_rate": None, "avg_callback_latency": None}


def test_daily_volume_groups_by_date():
    df = pd.concat([make_catalog_df(n=3, day=1), make_catalog_df(n=2, day=2)], ignore_index=True)
    out = metrics.daily_volume(df)
    by_date = {r["date"]: r["count"] for r in out}
    assert by_date == {"2026-10-01": 3, "2026-10-02": 2}


def test_daily_volume_falls_back_to_head_nod_datetime():
    df = make_catalog_df(n=2)
    df["HEAD_NOD_REQUEST_HIT_DATETIME"] = df["REQUEST_HIT_DATETIME"]
    df["REQUEST_HIT_DATETIME"] = None
    out = metrics.daily_volume(df)
    assert sum(r["count"] for r in out) == 2


def test_funnel_counts_uses_response_flags():
    out = metrics.funnel_counts(make_catalog_df(n=4))
    counts = {r["stage"]: r["count"] for r in out}
    assert counts["Blink"] == 4
    assert counts["Callback"] == 2


def test_funnel_counts_empty_df():
    out = metrics.funnel_counts(pd.DataFrame())
    assert len(out) == len(metrics.FUNNEL_ORDER)
    assert all(r["count"] == 0 for r in out)


def test_stage_status_breakdown():
    out = metrics.stage_status_breakdown(make_catalog_df(n=4), "Callback")
    statuses = {r["status"]: r["count"] for r in out}
    assert statuses == {"PASSED": 2, "FAILED": 2}


def test_latency_stats_and_raw():
    df = make_catalog_df(n=3)
    stats = {r["stage"]: r for r in metrics.latency_stats(df)}
    assert stats["Blink"]["mean"] == 0.5
    assert stats["Blink"]["n"] == 3
    raw = metrics.latency_raw_long(df)
    assert any(r["stage"] == "Blink" for r in raw)


def test_exception_rows_only_for_non_null():
    rows = metrics.exception_rows(make_catalog_df(n=3))
    assert len(rows) == 1
    assert rows[0]["TXN_ID"].endswith("~1")
    assert rows[0]["EXCEPTION_MESSAGE"] == "boom"


def test_build_dashboard_shape_and_json_safe():
    payload = metrics.build_dashboard(make_catalog_df(n=2))
    assert set(payload) == {"kpis", "daily_volume", "funnel", "stage_breakdown", "latency", "exceptions"}
    assert set(payload["stage_breakdown"]) == set(metrics.STAGES)
    assert isinstance(payload["kpis"]["total_txns"], int)
    # No numpy/NaN leakage.
    import json

    json.dumps(payload)
