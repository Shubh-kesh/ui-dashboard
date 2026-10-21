"""Unit tests for SQL builder query strings and identifier safety."""
from __future__ import annotations

import pytest

from app import queries
from app.config import Settings

LIVE = "LIVE_PHOTO_LOGS"
ARCHIVE = "LIVE_PHOTO_LOGS_ARCHIVE"


def test_catalog_query_has_no_limit_and_includes_window_and_source():
    sql, params = queries.catalog_query(LIVE, source="MOBILE_APP")
    assert "SELECT TOP" not in sql.upper()
    assert f"FROM {LIVE}" in sql
    assert "SOURCE = ?" in sql
    assert "DATEADD(day, 1, ?)" in sql
    assert params == ["MOBILE_APP"]


def test_catalog_query_no_source_filter():
    sql, params = queries.catalog_query(LIVE)
    assert "SOURCE = ?" not in sql
    assert params == []


def test_catalog_query_targets_archive_table():
    sql, _ = queries.catalog_query(ARCHIVE)
    assert f"FROM {ARCHIVE}" in sql


def test_catalog_columns_cover_stages_and_review_columns():
    for column in ["TXN_ID", "REQUEST_HIT_DATETIME", "SOURCE", "CALLBACK_STATUS",
                   "VERIFY_TOKEN_RES_DURATION", "TRACKING_ID",
                   "FRAUD_ATTEMPT", "USER_REVIEW"]:
        assert column in queries.CATALOG_COLUMNS


def test_sources_query_shape():
    assert "DISTINCT SOURCE" in queries.sources_query(LIVE)
    assert ARCHIVE in queries.sources_query(ARCHIVE)


def test_fraud_summary_query_parameterized_source_and_threshold():
    sql, params = queries.fraud_summary_query(LIVE, "NETBANKING", 4, "2026-10-01", "2026-10-07")
    assert "SOURCE = ?" in sql
    assert params == ["NETBANKING", "2026-10-01", "2026-10-07"]
    assert "SUCCESS_ATTEMPT_NO < 4" in sql


def test_fraud_queries_apply_the_date_window():
    _, params = queries.fraud_eventual_query(
        ARCHIVE, "MOBILE_APP", 5, "2026-09-01", "2026-09-30")
    assert params == ["MOBILE_APP", "2026-09-01", "2026-09-30"]
    sql, _ = queries.fraud_summary_query(LIVE, "NETBANKING", 4, "2026-10-01", "2026-10-07")
    assert "DATEADD(day, 1, ?)" in sql


def test_fraud_never_succeeded_query_min_attempts_and_archive_target():
    sql, params = queries.fraud_never_succeeded_query(
        ARCHIVE, "MOBILE_APP", 5, "2026-09-01", "2026-09-30")
    assert ARCHIVE in sql
    assert "SUCCESS_ATTEMPT_NO IS NULL" in sql
    assert "TOTAL_ATTEMPTS >= 5" in sql
    assert params == ["MOBILE_APP", "2026-09-01", "2026-09-30"]


def test_fraud_eventual_query_min_failed_and_archive_target():
    sql, params = queries.fraud_eventual_query(ARCHIVE, "MOBILE_APP", 5, "2026-09-01", "2026-09-30")
    assert ARCHIVE in sql
    assert ">= 5" in sql
    assert params == ["MOBILE_APP", "2026-09-01", "2026-09-30"]


def test_table_identifier_validation_rejects_injection():
    with pytest.raises(ValueError):
        Settings(table="LIVE_PHOTO_LOGS; DROP TABLE users")
    with pytest.raises(ValueError):
        Settings(table="has space")
    with pytest.raises(ValueError):
        Settings(archive_table="bad;name")
    # Valid identifiers (incl. schema-qualified) are accepted.
    assert Settings(table="docai.LIVE_PHOTO_LOGS").table == "docai.LIVE_PHOTO_LOGS"


def test_table_for_resolves_selectors():
    s = Settings()
    assert s.table_for("live") == s.table
    assert s.table_for("archive") == s.archive_table
    with pytest.raises(ValueError):
        s.table_for("both")
