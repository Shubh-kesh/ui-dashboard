"""API tests with the DB layer monkeypatched (no live database needed)."""
from __future__ import annotations

import pandas as pd
import pytest

from app import db
from tests.conftest import make_catalog_df


@pytest.fixture
def fake_db(monkeypatch, catalog_df):
    def fake_fetch_df(sql, params=()):
        if "DISTINCT SOURCE" in sql:
            return pd.DataFrame({"SOURCE": ["MOBILE_APP", "NETBANKING", "MOBILE_APP"]})
        if "QUICK_SUCCESS_USERS" in sql:
            return pd.DataFrame([{"TOTAL_USERS": 10, "QUICK_SUCCESS_USERS": 6}])
        if "SUCCESS_ATTEMPT_NO IS NULL" in sql:
            return pd.DataFrame([{"BASE_TXN_ID": "n1", "TOTAL_ATTEMPTS": 4}])
        if "FAILED_ATTEMPTS_BEFORE_SUCCESS" in sql:
            return pd.DataFrame([{"BASE_TXN_ID": "b2", "TOTAL_ATTEMPTS": 5,
                                  "SUCCESS_ATTEMPT_NO": 5,
                                  "FAILED_ATTEMPTS_BEFORE_SUCCESS": 4,
                                  "SUCCESS_TXN_ID": "b2~5"}])
        if "MIN_TS" in sql:
            return pd.DataFrame([{"N": 42, "MIN_TS": "2026-09-20 00:06:47",
                                  "MAX_TS": "2026-10-12 23:59:50"}])
        return catalog_df

    monkeypatch.setattr(db, "fetch_df", fake_fetch_df)
    monkeypatch.setattr(db, "ping", lambda: True)
    return fake_fetch_df


DATE = {"start": "2026-10-01", "end": "2026-10-01"}


def test_health_ok(client, fake_db):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["database_reachable"] is True
    assert body["table"] == "LIVE_PHOTO_LOGS"
    assert body["archive_table"] == "LIVE_PHOTO_LOGS_ARCHIVE"


def test_health_degraded_when_db_down(client, monkeypatch, catalog_df):
    monkeypatch.setattr(db, "fetch_df", lambda sql, params=(): catalog_df)
    monkeypatch.setattr(db, "ping", lambda: False)
    body = client.get("/api/health").json()
    assert body["status"] == "degraded" and body["database_reachable"] is False


def test_sources_deduped_and_sorted(client, fake_db):
    body = client.get("/api/sources").json()
    assert body["sources"] == ["MOBILE_APP", "NETBANKING"]


def test_range_reports_available_window(client, fake_db):
    body = client.get("/api/range", params={"table": "archive"}).json()
    assert body["table"] == "LIVE_PHOTO_LOGS_ARCHIVE"
    assert body["rows"] == 42
    assert body["min"] == "2026-09-20 00:06:47"
    assert body["max"] == "2026-10-12 23:59:50"


def test_dashboard_payload(client, fake_db):
    body = client.get("/api/dashboard", params=DATE).json()
    assert body["rows"] == 6
    assert body["kpis"]["total_txns"] == 6
    assert body["table"] == "LIVE_PHOTO_LOGS"
    assert "funnel" not in body
    assert body["time_series"]  # bucketed volume
    assert set(body["stage_breakdown"]) == {
        "Blink", "Head Nod", "Authenticity", "Image Seg", "Verify Token", "Callback",
        "Fraud Attempt", "User Review",
    }
    assert body["latency"]["stats"] and "raw" not in body["latency"]
    assert body["source"] is None


def test_dashboard_archive_table(client, fake_db):
    body = client.get("/api/dashboard", params={**DATE, "table": "archive"}).json()
    assert body["table"] == "LIVE_PHOTO_LOGS_ARCHIVE"


def test_dashboard_accepts_time_range_and_granularity(client, fake_db):
    body = client.get("/api/dashboard", params={
        **DATE, "granularity": "15m", "start_time": "09:00", "end_time": "18:00",
    }).json()
    assert body["granularity"] == "15m"
    assert body["start_time"] == "09:00"


def test_dashboard_rejects_bad_granularity(client, fake_db):
    resp = client.get("/api/dashboard", params={**DATE, "granularity": "7m"})
    assert resp.status_code == 400


def test_dashboard_rejects_bad_range(client, fake_db):
    resp = client.get("/api/dashboard", params={"start": "2026-10-05", "end": "2026-10-01"})
    assert resp.status_code == 400


def test_raw_and_raw_csv(client, fake_db):
    raw = client.get("/api/raw", params=DATE).json()
    assert raw["count"] == 6
    assert "TXN_ID" in raw["columns"]
    assert "FRAUD_ATTEMPT" in raw["columns"] and "USER_REVIEW" in raw["columns"]
    csv_resp = client.get("/api/raw.csv", params=DATE)
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    header = csv_resp.text.splitlines()[0]
    assert "TXN_ID" in header and "FRAUD_ATTEMPT" in header


def test_fraud_endpoints(client, fake_db):
    summary = client.get(
        "/api/fraud/summary",
        params={"source": "MOBILE_APP", "threshold": 4, **DATE},
    ).json()
    assert summary == {"source": "MOBILE_APP", "total_users": 10,
                       "quick_success_users": 6, "quick_success_pct": 60.0}

    eventual = client.get(
        "/api/fraud/eventual",
        params={"source": "MOBILE_APP", "min_failed": 3, **DATE},
    ).json()
    assert len(eventual["rows"]) == 1 and eventual["rows"][0]["SUCCESS_TXN_ID"] == "b2~5"

    never = client.get(
        "/api/fraud/never-succeeded",
        params={"source": "MOBILE_APP", "min_attempts": 3, **DATE, "table": "archive"},
    ).json()
    assert never["source"] == "MOBILE_APP"
    assert never["rows"] == [{"BASE_TXN_ID": "n1", "TOTAL_ATTEMPTS": 4}]


def test_database_error_maps_to_502(client, monkeypatch):
    def boom(sql, params=()):
        raise db.DatabaseError("connection refused")

    monkeypatch.setattr(db, "fetch_df", boom)
    resp = client.get("/api/dashboard", params=DATE)
    assert resp.status_code == 502
    assert "Database error" in resp.json()["detail"]
