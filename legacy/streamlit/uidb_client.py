"""
Client for talking to the `uidb` (digivision/ai) microservice, which proxies
queries to the MSSQL catalog table backing blink/head-nod/authenticity/
image-seg status.

Confirmed contract (verified by live testing against the real endpoint):
    Request (all fields required -- omitting RESULT causes a KeyError server-side;
    RESULT appears to act as a "fetch rows back" flag -- must be true to get DATA populated):
        {
            "DB_SERVER": "DOCAI",
            "DBTYPE": "RUN",
            "QUERY": "<sql string>",
            "DATA": [],
            "RESULT": true
        }
    Response:
        {
            "CODE": 200,
            "DATA": [ {...row...}, {...row...} ],
            "EXCEPTION_MESSAGE": "",
            "MESSAGE": "SUCCESSFULLY INSERTED DATA INTO DATABASE",  # generic; not query-type-specific
            "STATUS": true | false
        }

NOTE: the MESSAGE wording is generic/misleading for SELECTs (says "INSERTED").
Rely on STATUS + DATA, not MESSAGE, to judge outcome.
"""

import os
import re
import requests
import pandas as pd
from datetime import date

# --- Config -----------------------------------------------------------
# Read from env vars (set via k8s ConfigMap) with a local-dev fallback.
UIDB_ENDPOINT = os.environ.get(
    "UIDB_ENDPOINT", "http://10.152.1.78:8442/digivision/ai"
)
DB_SERVER = os.environ.get("DB_SERVER", "DOCAI")
TABLE_NAME = os.environ.get("TABLE_NAME", "LIVE_PHOTO_LOGS")
REQUEST_TIMEOUT_SECS = int(os.environ.get("UIDB_TIMEOUT_SECS", "15"))

# Columns pulled straight from your schema
CATALOG_COLUMNS = [
    "ID", "TXN_ID", "REQUEST_HIT_DATETIME",
    "BLINK_REQUEST", "BLINK_RESPONSE", "BLINK_FACE_IN_CENTRE", "BLINK_MULTIFACE",
    "BLINK_STATUS", "BLINK_RESPONSE_DURATION",
    "HEAD_NOD_REQUEST_HIT_DATETIME", "HEAD_NOD_REQUEST", "HEAD_NOD_RESPONSE",
    "HEAD_NOD_STATUS", "HEAD_NOD_RESPONSE_DURATION",
    "AUTHENTICITY_REQUEST", "AUTHENTICITY_RESPONSE", "AUTHENTICITY_STATUS",
    "AUTHENTICITY_RESPONSE_DURATION",
    "IMAGE_SEG_REQUEST", "IMAGE_SEG_RESPONSE", "IMAGE_SEG_STATUS",
    "IMAGE_SEG_RESPONSE_DURATION",
    "EXCEPTION_MESSAGE", "HEAD_NOD_EXCEPTION_MESSAGE", "SOURCE",
    "VERIFY_TOKEN_EXCEPTION", "CALLBACK_EXCEPTION",
    "VERIFY_TOKEN_RES_DURATION", "CALLBACK_RES_DURATION",
    "VERIFYTOKEN_REQ", "VERIFYTOKEN_RES", "VERIFYTOKEN_STATUS",
    "CALLBACK_REQ", "CALLBACK_RES", "CALLBACK_STATUS", "TRACKING_ID",
]


class UidbError(Exception):
    """Raised when uidb returns STATUS: false, or the call otherwise fails."""


# Human-readable text for uidb/digivision CODE values, since the service's
# own MESSAGE field is often generic or misleading (e.g. "SUCCESSFULLY
# INSERTED DATA INTO DATABASE" even for SELECT queries). Add to this as you
# discover what each CODE actually means in practice.
ERROR_CODE_MESSAGES: dict[int, str] = {
    200: "Success.",
    203: "Request payload was missing a required field (commonly a missing 'RESULT' key).",
    204: "Query executed but the server reported it as incomplete or invalid.",
    415: "Unsupported request format -- Content-Type header was not application/json.",
}


def describe_code(code) -> str:
    """Human-readable text for a uidb CODE value. Falls back to a generic
    message for any code not yet catalogued above."""
    try:
        code_int = int(code)
    except (TypeError, ValueError):
        return "Unknown response code."
    return ERROR_CODE_MESSAGES.get(
        code_int, f"Unrecognized code {code_int} -- check with the uidb/digivision team."
    )


def _escape_sql_literal(value: str) -> str:
    """Minimal defense against breaking out of a quoted SQL literal.
    Doubling single quotes is the standard MSSQL escape for string literals."""
    return value.replace("'", "''")


def _parse_uidb_datetime(series: pd.Series) -> pd.Series:
    """uidb/digivision serializes datetimes as 'DD-MM-YYYY hh:mm:ss:fff AM/PM'
    (e.g. '03-09-2026 03:29:55:467 PM') -- NOT ISO format, and NOT the raw
    SQL Server datetime2 string shape. DD-MM-YYYY is ambiguous to pandas'
    generic inference, so this parses the exact confirmed format explicitly."""
    return pd.to_datetime(series, format="%d-%m-%Y %I:%M:%S:%f %p", errors="coerce")


def _call_uidb(query: str) -> list[dict]:
    payload = {
        "DB_SERVER": DB_SERVER,
        "DBTYPE": "RUN",
        "QUERY": query,
        "DATA": [],
        "RESULT": True,
    }
    headers = {"Content-Type": "application/json"}
    resp = requests.post(UIDB_ENDPOINT, json=payload, headers=headers, timeout=REQUEST_TIMEOUT_SECS)
    resp.raise_for_status()
    body = resp.json()

    # Real response contract uses STATUS (bool), plus CODE/MESSAGE/EXCEPTION_MESSAGE
    # on failure -- NOT "RESULT" (that was a mismatch with an earlier/different sample).
    if not body.get("STATUS", False):
        code = body.get("CODE")
        detail = body.get("EXCEPTION_MESSAGE") or body.get("MESSAGE") or "unknown error"
        raise UidbError(
            f"uidb reported failure (code={code}): {describe_code(code)} | raw: {detail} | query: {query}"
        )

    return body.get("DATA", [])


def fetch_txn_data(
    start_date: date,
    end_date: date,
    source: str | None = None,
    limit: int = 5000,
) -> pd.DataFrame:
    """Fetch catalog rows for a date range (inclusive), optionally filtered by SOURCE.

    Dates are passed as plain 'YYYY-MM-DD' literals -- safe because they come
    from a Streamlit date_input widget (constrained type), not free-text input.
    """
    cols = ", ".join(CATALOG_COLUMNS)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    where_clauses = [
        f"REQUEST_HIT_DATETIME >= '{start_str}'",
        f"REQUEST_HIT_DATETIME < DATEADD(day, 1, '{end_str}')",
    ]
    if source:
        where_clauses.append(f"SOURCE = '{_escape_sql_literal(source)}'")

    where_sql = " AND ".join(where_clauses)

    query = (
        f"SELECT TOP {int(limit)} {cols} FROM {TABLE_NAME} WITH (NOLOCK) "
        f"WHERE {where_sql} ORDER BY REQUEST_HIT_DATETIME DESC"
    )

    rows = _call_uidb(query)
    df = pd.DataFrame(rows)

    if not df.empty:
        df.columns = [str(c).strip().upper() for c in df.columns]

    if not df.empty and "REQUEST_HIT_DATETIME" in df.columns:
        df["REQUEST_HIT_DATETIME"] = _parse_uidb_datetime(df["REQUEST_HIT_DATETIME"])

    if not df.empty and "HEAD_NOD_REQUEST_HIT_DATETIME" in df.columns:
        df["HEAD_NOD_REQUEST_HIT_DATETIME"] = _parse_uidb_datetime(
            df["HEAD_NOD_REQUEST_HIT_DATETIME"]
        )

    return df


def run_raw_query(query: str) -> pd.DataFrame:
    """Public helper for ad-hoc SQL beyond the standard catalog fetch (e.g. the
    attempt-pattern/fraud analysis aggregate queries in fraud_metrics.py).
    Reuses the same request/response handling as fetch_txn_data."""
    rows = _call_uidb(query)
    df = pd.DataFrame(rows)
    if not df.empty:
        df.columns = [str(c).strip().upper() for c in df.columns]
    return df


def fetch_distinct_sources() -> list[str]:
    """Pull the list of distinct SOURCE values for the filter dropdown."""
    query = f"SELECT DISTINCT SOURCE FROM {TABLE_NAME} WITH (NOLOCK)"
    rows = _call_uidb(query)
    return sorted({r["SOURCE"] for r in rows if r.get("SOURCE")})
