"""Shared pytest fixtures for the ui-dashboard backend tests."""
from __future__ import annotations

import datetime as dt
import os

import pandas as pd
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MSSQL_DATABASE", "docai")
os.environ.setdefault("LIVE_PHOTO_TABLE", "LIVE_PHOTO_LOGS")

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def make_catalog_df(n: int = 6, day: int = 1) -> pd.DataFrame:
    """A small catalog DataFrame with one row per attempt."""
    base = dt.datetime(2026, 10, day, 10, 0, 0)
    rows = []
    for i in range(n):
        callback_ok = i % 2 == 0
        rows.append({
            "TXN_ID": f"20261{day:02d}100000_{i:08x}~1",
            "REQUEST_HIT_DATETIME": base + dt.timedelta(minutes=i),
            "HEAD_NOD_REQUEST_HIT_DATETIME": None,
            "BLINK_REQUEST": 1, "BLINK_RESPONSE": 1, "BLINK_STATUS": "PASSED",
            "BLINK_RESPONSE_DURATION": 0.5,
            "HEAD_NOD_REQUEST": 1, "HEAD_NOD_RESPONSE": 1, "HEAD_NOD_STATUS": "PASSED",
            "HEAD_NOD_RESPONSE_DURATION": 0.6,
            "AUTHENTICITY_REQUEST": 1, "AUTHENTICITY_RESPONSE": 1,
            "AUTHENTICITY_STATUS": "PASSED", "AUTHENTICITY_RESPONSE_DURATION": 0.7,
            "IMAGE_SEG_REQUEST": 1, "IMAGE_SEG_RESPONSE": 1, "IMAGE_SEG_STATUS": "PASSED",
            "IMAGE_SEG_RESPONSE_DURATION": 0.8,
            "VERIFYTOKEN_REQ": 1, "VERIFYTOKEN_RES": 1, "VERIFYTOKEN_STATUS": "PASSED",
            "VERIFY_TOKEN_RES_DURATION": 0.9,
            "CALLBACK_REQ": 1, "CALLBACK_RES": 1 if callback_ok else 0,
            "CALLBACK_STATUS": "PASSED" if callback_ok else "FAILED",
            "CALLBACK_RES_DURATION": 1.0,
            "EXCEPTION_MESSAGE": "boom" if i == 0 else None,
            "HEAD_NOD_EXCEPTION_MESSAGE": None,
            "VERIFY_TOKEN_EXCEPTION": None,
            "CALLBACK_EXCEPTION": None,
            "SOURCE": "MOBILE_APP",
            "TRACKING_ID": f"TRK{i}",
        })
    return pd.DataFrame(rows)


@pytest.fixture
def catalog_df() -> pd.DataFrame:
    return make_catalog_df()
