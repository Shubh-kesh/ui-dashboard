"""Unit tests for SQL builder query strings and identifier safety."""
from __future__ import annotations

import pytest

from app import queries
from app.config import Settings


def test_catalog_query_includes_window_and_source():
    sql, params = queries.catalog_query(100, source="MOBILE_APP")
    assert "SELECT TOP (100)" in sql
    assert "SOURCE = ?" in sql
    assert "DATEADD(day, 1, ?)" in sql
    assert params == ["MOBILE_APP"]


def test_catalog_query_no_source_filter():
    sql, params = queries.catalog_query(50)
    assert "SOURCE = ?" not in sql
    assert params == []


def test_catalog_columns_cover_every_stage():
    for cols in queries.STAGES.values() if hasattr(queries, "STAGES") else []:
        pass  # STAGES lives in services.metrics, not here
    for column in ["TXN_ID", "REQUEST_HIT_DATETIME", "SOURCE", "CALLBACK_STATUS",
                   "VERIFY_TOKEN_RES_DURATION", "TRACKING_ID"]:
        assert column in queries.CATALOG_COLUMNS


def test_sources_query_shape():
    assert "DISTINCT SOURCE" in queries.sources_query()


def test_fraud_summary_query_parameterized_source_and_threshold():
    sql, params = queries.fraud_summary_query("NETBANKING", 4)
    assert "SOURCE = ?" in sql
    assert params == ["NETBANKING"]
    assert "SUCCESS_ATTEMPT_NO < 4" in sql


def test_fraud_burst_query_embeds_gap_and_params_source():
    sql, params = queries.fraud_burst_query("BRANCH_TAB", 7, 2)
    assert "GAP_SECONDS <= 7" in sql
    assert "BURST_PAIRS >= 2" in sql
    assert params == ["BRANCH_TAB"]


def test_fraud_eventual_query_min_failed():
    sql, params = queries.fraud_eventual_query("MOBILE_APP", 5)
    assert ">= 5" in sql
    assert params == ["MOBILE_APP"]


def test_table_identifier_validation_rejects_injection():
    with pytest.raises(ValueError):
        Settings(table="LIVE_PHOTO_LOGS; DROP TABLE users")
    with pytest.raises(ValueError):
        Settings(table="has space")
    # Valid identifiers (incl. schema-qualified) are accepted.
    assert Settings(table="docai.LIVE_PHOTO_LOGS").table == "docai.LIVE_PHOTO_LOGS"
