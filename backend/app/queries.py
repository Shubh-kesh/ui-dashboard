"""SQL builders for the dashboard. All catalog reads are direct T-SQL against
the DocAI MSSQL table (no uidb proxy).

The catalog table is keyed by the full ``TXN_ID = "<txnid>~<attempt>"``; the
fraud/attempt analysis parses ``BASE_TXN_ID`` (before the first ``_``) and
``ATTEMPT_NO`` (after the final ``~``).
"""
from __future__ import annotations

from .config import get_settings

# Authoritative catalog column set (kept identical to the historical
# Streamlit uidb_client.CATALOG_COLUMNS).
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

# Effective event time: blink rows use REQUEST_HIT_DATETIME, head-nod-path
# rows use HEAD_NOD_REQUEST_HIT_DATETIME.
_EVENT_TIME = "COALESCE(REQUEST_HIT_DATETIME, HEAD_NOD_REQUEST_HIT_DATETIME)"


def _table() -> str:
    return get_settings().table


def sources_query() -> str:
    return (
        f"SELECT DISTINCT SOURCE FROM {_table()} WITH (NOLOCK) "
        "WHERE SOURCE IS NOT NULL ORDER BY SOURCE"
    )


def catalog_query(limit: int, source: str | None = None) -> tuple[str, list]:
    """SELECT the catalog columns for a [start, end] date window (inclusive)."""
    cols = ", ".join(CATALOG_COLUMNS)
    where = [f"{_EVENT_TIME} >= ?", f"{_EVENT_TIME} < DATEADD(day, 1, ?)"]
    params: list = []
    if source:
        where.append("SOURCE = ?")
        params.append(source)
    sql = (
        f"SELECT TOP ({int(limit)}) {cols} FROM {_table()} WITH (NOLOCK) "
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
    FROM {table}
    WHERE SOURCE = ?
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

_PARSED_TIME_CTE = """
WITH parsed AS (
    SELECT
        TXN_ID,
        LEFT(TXN_ID, CHARINDEX('_', TXN_ID) - 1) AS BASE_TXN_ID,
        CAST(SUBSTRING(TXN_ID, CHARINDEX('~', TXN_ID) + 1, LEN(TXN_ID)) AS INT) AS ATTEMPT_NO,
        COALESCE(REQUEST_HIT_DATETIME, HEAD_NOD_REQUEST_HIT_DATETIME) AS ATTEMPT_TIME,
        SOURCE
    FROM {table}
    WHERE SOURCE = ?
      AND CHARINDEX('_', TXN_ID) > 0
      AND CHARINDEX('~', TXN_ID) > 0
),
gaps AS (
    SELECT
        BASE_TXN_ID,
        ATTEMPT_NO,
        DATEDIFF(SECOND,
                 LAG(ATTEMPT_TIME) OVER (PARTITION BY BASE_TXN_ID ORDER BY ATTEMPT_NO),
                 ATTEMPT_TIME) AS GAP_SECONDS
    FROM parsed
),
per_user_velocity AS (
    SELECT
        BASE_TXN_ID,
        COUNT(*) AS TOTAL_ATTEMPTS,
        MIN(GAP_SECONDS) AS MIN_GAP_SECONDS,
        SUM(CASE WHEN GAP_SECONDS IS NOT NULL AND GAP_SECONDS <= {gap} THEN 1 ELSE 0 END) AS BURST_PAIRS
    FROM gaps
    GROUP BY BASE_TXN_ID
)
"""


def fraud_summary_query(source: str, quick_success_threshold: int) -> tuple[str, list]:
    sql = _PARSED_CTE.format(table=_table()) + f"""
SELECT
    COUNT(*) AS TOTAL_USERS,
    SUM(CASE WHEN SUCCESS_ATTEMPT_NO IS NOT NULL AND SUCCESS_ATTEMPT_NO < {int(quick_success_threshold)}
             THEN 1 ELSE 0 END) AS QUICK_SUCCESS_USERS
FROM per_user
"""
    return sql, [source]


def fraud_total_users_query(source: str) -> tuple[str, list]:
    sql = (
        "SELECT COUNT(DISTINCT LEFT(TXN_ID, CHARINDEX('_', TXN_ID) - 1)) AS TOTAL_USERS "
        f"FROM {_table()} WITH (NOLOCK) "
        "WHERE SOURCE = ? AND CHARINDEX('_', TXN_ID) > 0 AND CHARINDEX('~', TXN_ID) > 0"
    )
    return sql, [source]


def fraud_eventual_query(source: str, min_failed_attempts: int) -> tuple[str, list]:
    sql = _PARSED_CTE.format(table=_table()) + f"""
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
    return sql, [source]


def fraud_burst_query(source: str, gap_seconds: int, min_pairs: int) -> tuple[str, list]:
    sql = _PARSED_TIME_CTE.format(table=_table(), gap=int(gap_seconds)) + f"""
SELECT BASE_TXN_ID, TOTAL_ATTEMPTS, MIN_GAP_SECONDS, BURST_PAIRS
FROM per_user_velocity
WHERE BURST_PAIRS >= {int(min_pairs)}
ORDER BY BURST_PAIRS DESC, MIN_GAP_SECONDS ASC
"""
    return sql, [source]
