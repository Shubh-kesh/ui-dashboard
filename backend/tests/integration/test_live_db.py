"""Integration tests against a real local MSSQL (Azure SQL Edge).

Gated behind LIVE_PHOTO_TEST_LIVE_DB=1 so the default test run stays offline.
Seed first:  python dba/local_dev_seed.py

    LIVE_PHOTO_TEST_LIVE_DB=1 pytest tests/integration -q
"""
from __future__ import annotations

import datetime as dt
import os

import pytest

from app import db, queries
from app.config import get_settings
from app.services import metrics

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_PHOTO_TEST_LIVE_DB") != "1",
    reason="set LIVE_PHOTO_TEST_LIVE_DB=1 and seed the local DB to run",
)

SOURCE = os.getenv("LIVE_PHOTO_TEST_SOURCE", "MOBILE_APP")


def test_database_reachable():
    assert db.ping() is True


def test_table_exists():
    table = get_settings().table.split(".")[-1]
    rows = db.fetch_all(
        "SELECT name FROM sys.tables WHERE name = ?", [table])
    assert rows, f"{table} not found - run dba/local_dev_seed.py"


def test_seeded_rows_present():
    table = get_settings().table
    rows = db.fetch_all(f"SELECT COUNT(*) AS N FROM {table} WITH (NOLOCK)")
    assert rows[0]["N"] > 0, "no seeded rows - run dba/local_dev_seed.py"


def test_catalog_query_returns_window_rows():
    end = dt.date.today()
    start = end - dt.timedelta(days=30)
    sql, params = queries.catalog_query(1000)
    df = db.fetch_df(sql, [start.isoformat(), end.isoformat(), *params])
    assert not df.empty
    for column in ("TXN_ID", "SOURCE", "REQUEST_HIT_DATETIME"):
        assert column in df.columns


def test_dashboard_build_over_real_rows():
    end = dt.date.today()
    start = end - dt.timedelta(days=30)
    sql, params = queries.catalog_query(2000)
    df = db.fetch_df(sql, [start.isoformat(), end.isoformat(), *params])
    payload = metrics.build_dashboard(df)
    assert payload["kpis"]["total_txns"] == len(df)
    assert payload["daily_volume"]


def test_fraud_queries_execute():
    summary_sql, summary_params = queries.fraud_summary_query(SOURCE, 3)
    summary = db.fetch_df(summary_sql, summary_params)
    assert not summary.empty
    assert int(summary.iloc[0]["TOTAL_USERS"]) >= 0

    total_sql, total_params = queries.fraud_total_users_query(SOURCE)
    total = db.fetch_df(total_sql, total_params)
    assert int(total.iloc[0]["TOTAL_USERS"]) >= 0

    burst_sql, burst_params = queries.fraud_burst_query(SOURCE, 5, 3)
    db.fetch_df(burst_sql, burst_params)  # must not raise

    eventual_sql, eventual_params = queries.fraud_eventual_query(SOURCE, 3)
    db.fetch_df(eventual_sql, eventual_params)  # must not raise
