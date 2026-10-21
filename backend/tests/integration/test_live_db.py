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


@pytest.mark.parametrize("table", ["LIVE_PHOTO_LOGS", "LIVE_PHOTO_LOGS_ARCHIVE"])
def test_table_exists(table):
    rows = db.fetch_all("SELECT name FROM sys.tables WHERE name = ?", [table])
    assert rows, f"{table} not found - run dba/local_dev_seed.py"


@pytest.mark.parametrize("table", ["LIVE_PHOTO_LOGS", "LIVE_PHOTO_LOGS_ARCHIVE"])
def test_seeded_rows_present(table):
    rows = db.fetch_all(f"SELECT COUNT(*) AS N FROM {table} WITH (NOLOCK)")
    assert rows[0]["N"] > 0, "no seeded rows - run dba/local_dev_seed.py"


@pytest.mark.parametrize("table", ["LIVE_PHOTO_LOGS", "LIVE_PHOTO_LOGS_ARCHIVE"])
def test_catalog_query_returns_window_rows(table):
    end = dt.date.today()
    start = end - dt.timedelta(days=30)
    sql, params = queries.catalog_query(table)
    df = db.fetch_df(sql, [start.isoformat(), end.isoformat(), *params])
    assert not df.empty
    for column in ("TXN_ID", "SOURCE", "REQUEST_HIT_DATETIME",
                   "FRAUD_ATTEMPT", "USER_REVIEW"):
        assert column in df.columns


@pytest.mark.parametrize("table", ["LIVE_PHOTO_LOGS", "LIVE_PHOTO_LOGS_ARCHIVE"])
def test_range_query_reports_window(table):
    df = db.fetch_df(queries.range_query(table))
    assert int(df.iloc[0]["N"]) > 0
    assert df.iloc[0]["MIN_TS"] is not None and df.iloc[0]["MAX_TS"] is not None


def test_live_and_archive_are_disjoint_windows():
    live = db.fetch_all(
        f"SELECT MIN(COALESCE(REQUEST_HIT_DATETIME, HEAD_NOD_REQUEST_HIT_DATETIME)) AS MN "
        "FROM LIVE_PHOTO_LOGS WITH (NOLOCK)")
    archive = db.fetch_all(
        f"SELECT MAX(COALESCE(REQUEST_HIT_DATETIME, HEAD_NOD_REQUEST_HIT_DATETIME)) AS MX "
        "FROM LIVE_PHOTO_LOGS_ARCHIVE WITH (NOLOCK)")
    # Archive holds older data; live holds newer data.
    assert archive[0]["MX"] < live[0]["MN"]


def test_dashboard_build_over_real_rows():
    end = dt.date.today()
    start = end - dt.timedelta(days=30)
    sql, params = queries.catalog_query(get_settings().table)
    df = db.fetch_df(sql, [start.isoformat(), end.isoformat(), *params])
    payload = metrics.build_dashboard(df, start=start, end=end, granularity="1d")
    assert payload["kpis"]["total_txns"] == len(df)
    assert payload["time_series"]
    assert "Fraud Attempt" in payload["stage_breakdown"]
    assert payload["latency"]["stats"]


def test_fraud_queries_execute():
    table = get_settings().table
    start, end = "2000-01-01", "2100-01-01"

    summary_sql, summary_params = queries.fraud_summary_query(table, SOURCE, 3, start, end)
    summary = db.fetch_df(summary_sql, summary_params)
    assert not summary.empty
    assert int(summary.iloc[0]["TOTAL_USERS"]) >= 0

    eventual_sql, eventual_params = queries.fraud_eventual_query(table, SOURCE, 3, start, end)
    db.fetch_df(eventual_sql, eventual_params)  # must not raise

    never_sql, never_params = queries.fraud_never_succeeded_query(table, SOURCE, 3, start, end)
    never = db.fetch_df(never_sql, never_params)
    for row in never.to_dict(orient="records"):
        assert row["TOTAL_ATTEMPTS"] >= 3
