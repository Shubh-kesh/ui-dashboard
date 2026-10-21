"""SQL builders for the dashboard. All catalog reads are direct T-SQL against
the DocAI MSSQL tables (no uidb proxy).

The catalog table is keyed by the full ``TXN_ID = "<txnid>~<attempt>"``; the
fraud/attempt analysis parses ``BASE_TXN_ID`` (before the first ``_``) and
``ATTEMPT_NO`` (after the final ``~``).

Reads are split across two tables in the same database:
  * ``LIVE_PHOTO_LOGS``          - recent data (last ``LIVE_WINDOW_DAYS`` days)
  * ``LIVE_PHOTO_LOGS_ARCHIVE``  - older data

No ``TOP``/``LIMIT`` is applied: every builder returns the full window.
"""
from __future__ import annotations

import datetime as dt

# Authoritative catalog column set (kept identical to the historical
# Streamlit uidb_client.CATALOG_COLUMNS, plus the review columns).
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
    "FRAUD_ATTEMPT", "USER_REVIEW",
]

# Effective event time: blink rows use REQUEST_HIT_DATETIME, head-nod-path
# rows use HEAD_NOD_REQUEST_HIT_DATETIME.
_EVENT_TIME = "COALESCE(REQUEST_HIT_DATETIME, HEAD_NOD_REQUEST_HIT_DATETIME)"


def sources_query(table: str) -> str:
    return (
        f"SELECT DISTINCT SOURCE FROM {table} WITH (NOLOCK) "
        "WHERE SOURCE IS NOT NULL ORDER BY SOURCE"
    )


def range_query(table: str) -> str:
    """Available data window + row count for a table."""
    return (
        f"SELECT COUNT(*) AS N, MIN({_EVENT_TIME}) AS MIN_TS, MAX({_EVENT_TIME}) AS MAX_TS "
        f"FROM {table} WITH (NOLOCK)"
    )


def catalog_query(table: str, source: str | None = None) -> tuple[str, list]:
    """SELECT the full catalog for a [start, end] date window (inclusive).

    No row limit is applied; the window is bounded by the two date params.
    """
    cols = ", ".join(CATALOG_COLUMNS)
    where = [f"{_EVENT_TIME} >= ?", f"{_EVENT_TIME} < DATEADD(day, 1, ?)"]
    params: list = []
    if source:
        where.append("SOURCE = ?")
        params.append(source)
    sql = (
        f"SELECT {cols} FROM {table} WITH (NOLOCK) "
        f"WHERE {' AND '.join(where)} ORDER BY {_EVENT_TIME} DESC"
    )
    return sql, params


# --- Attempt / fraud analysis -------------------------------------------------

_PARSED_CTE = """
WITH parsed AS (
    SELECT
        TXN_ID,
        LEFT(TXN_ID, CHARINDEX('_', TXN_ID) - 1) AS BASE_TXN_ID,
        CAST(SUBSTRING(TXN_ID, CHARINDEX('~', TXN_ID) + 1, LEN(TXN_ID)) AS INT) AS ATTEMPT_NO,
        AUTHENTICITY_STATUS,
        CALLBACK_STATUS,
        SOURCE
    FROM {table} WITH (NOLOCK)
    WHERE SOURCE = ?
      AND {event_time} >= ?
      AND {event_time} < DATEADD(day, 1, ?)
      AND CHARINDEX('_', TXN_ID) > 0
      AND CHARINDEX('~', TXN_ID) > 0
),
per_user AS (
    SELECT
        BASE_TXN_ID,
        COUNT(*) AS TOTAL_ATTEMPTS,
        MIN(CASE WHEN AUTHENTICITY_STATUS = 'PASSED' AND CALLBACK_STATUS = 'PASSED'
                 THEN ATTEMPT_NO END) AS SUCCESS_ATTEMPT_NO
    FROM parsed
    GROUP BY BASE_TXN_ID
)
"""


def _parsed_cte(table: str) -> str:
    return _PARSED_CTE.format(table=table, event_time=_EVENT_TIME)


def fraud_summary_query(
    table: str, source: str, quick_success_threshold: int,
    start: str, end: str,
) -> tuple[str, list]:
    sql = _parsed_cte(table) + f"""
SELECT
    COUNT(*) AS TOTAL_USERS,
    SUM(CASE WHEN SUCCESS_ATTEMPT_NO IS NOT NULL AND SUCCESS_ATTEMPT_NO < {int(quick_success_threshold)}
             THEN 1 ELSE 0 END) AS QUICK_SUCCESS_USERS
FROM per_user
"""
    return sql, [source, start, end]


def fraud_eventual_query(
    table: str, source: str, min_failed_attempts: int,
    start: str, end: str,
) -> tuple[str, list]:
    sql = _parsed_cte(table) + f"""
SELECT
    pu.BASE_TXN_ID,
    pu.TOTAL_ATTEMPTS,
    pu.SUCCESS_ATTEMPT_NO,
    pu.SUCCESS_ATTEMPT_NO - 1 AS FAILED_ATTEMPTS_BEFORE_SUCCESS,
    p.TXN_ID AS SUCCESS_TXN_ID
FROM per_user pu
JOIN parsed p
    ON p.BASE_TXN_ID = pu.BASE_TXN_ID AND p.ATTEMPT_NO = pu.SUCCESS_ATTEMPT_NO
WHERE pu.SUCCESS_ATTEMPT_NO IS NOT NULL
  AND (pu.SUCCESS_ATTEMPT_NO - 1) >= {int(min_failed_attempts)}
ORDER BY FAILED_ATTEMPTS_BEFORE_SUCCESS DESC
"""
    return sql, [source, start, end]


def fraud_never_succeeded_query(
    table: str, source: str, min_attempts: int,
    start: str, end: str,
) -> tuple[str, list]:
    """Users who made >= min_attempts attempts in the window and never passed
    both authenticity and callback on any attempt."""
    sql = _parsed_cte(table) + f"""
SELECT
    pu.BASE_TXN_ID,
    pu.TOTAL_ATTEMPTS
FROM per_user pu
WHERE pu.SUCCESS_ATTEMPT_NO IS NULL
  AND pu.TOTAL_ATTEMPTS >= {int(min_attempts)}
ORDER BY pu.TOTAL_ATTEMPTS DESC
"""
    return sql, [source, start, end]


def alert_counts_query(
    table: str, start: dt.datetime, end: dt.datetime,
) -> tuple[str, list]:
    """Per-source request counts for the load-alert worker.

    ``*_REQUEST`` columns are BIT: 1 = requested, NULL = skipped. ``SUM`` is
    used instead of ``COUNT`` so an explicit 0 would not be counted either.
    Timestamps are naive IST, matching the values stored in the catalog.
    """
    sql = f"""
SELECT
    SOURCE,
    COUNT(*) AS TOTAL,
    SUM(CASE WHEN BLINK_REQUEST = 1 THEN 1 ELSE 0 END) AS BLINK,
    SUM(CASE WHEN HEAD_NOD_REQUEST = 1 THEN 1 ELSE 0 END) AS HEAD_NOD,
    SUM(CASE WHEN AUTHENTICITY_REQUEST = 1 THEN 1 ELSE 0 END) AS AUTH,
    SUM(CASE WHEN IMAGE_SEG_REQUEST = 1 THEN 1 ELSE 0 END) AS IMAGE_SEG,
    SUM(CASE WHEN VERIFYTOKEN_REQ = 1 THEN 1 ELSE 0 END) AS VERIFYTOKEN,
    SUM(CASE WHEN CALLBACK_REQ = 1 THEN 1 ELSE 0 END) AS CALLBACK
FROM {table} WITH (NOLOCK)
WHERE COALESCE(REQUEST_HIT_DATETIME, HEAD_NOD_REQUEST_HIT_DATETIME) >= ?
  AND COALESCE(REQUEST_HIT_DATETIME, HEAD_NOD_REQUEST_HIT_DATETIME) < ?
GROUP BY SOURCE
ORDER BY SOURCE
"""
    return sql, [start, end]

