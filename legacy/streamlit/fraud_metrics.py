"""
Attempt-pattern / suspected-fraud analysis.

TXN_ID encodes both a user identity and an attempt number, e.g.:
    '20260904105104_a05bcac7~3'
     \_____________/         \
      BASE_TXN_ID (before    ATTEMPT_NO (after the final '~')
      the first '_')  -- identifies one user's journey across retries

All three scenarios share the same PARSED/PER_USER CTEs; only the filter and
configurable threshold differ.

Scenario 1 -- quick success: % of unique users who reached AUTHENTICITY +
    CALLBACK success within fewer than N attempts.
Scenario 2 -- eventual success (suspected fraud that got through): users who
    failed for a run of attempts before eventually succeeding.
Scenario 3 -- never succeeded (suspected fraud that never got through): users
    who kept failing and never reached success, across at least N attempts.
"""

import pandas as pd
import uidb_client

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
    WHERE SOURCE = '{source}'
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


def _escape(value: str) -> str:
    return value.replace("'", "''")


def fetch_summary(source: str, quick_success_threshold: int) -> dict:
    """Scenario 1. Also returns TOTAL_USERS, reused as the denominator for
    scenarios 2 and 3 so all three percentages are consistent."""
    query = _PARSED_CTE.format(table=uidb_client.TABLE_NAME, source=_escape(source)) + f"""
SELECT
    COUNT(*) AS TOTAL_USERS,
    SUM(CASE WHEN SUCCESS_ATTEMPT_NO IS NOT NULL AND SUCCESS_ATTEMPT_NO < {int(quick_success_threshold)}
             THEN 1 ELSE 0 END) AS QUICK_SUCCESS_USERS
FROM per_user
"""
    df = uidb_client.run_raw_query(query)
    if df.empty or df.iloc[0]["TOTAL_USERS"] in (None, 0):
        return {"total_users": 0, "quick_success_users": 0, "quick_success_pct": 0.0}

    total = int(df.iloc[0]["TOTAL_USERS"])
    quick = int(df.iloc[0]["QUICK_SUCCESS_USERS"] or 0)
    return {
        "total_users": total,
        "quick_success_users": quick,
        "quick_success_pct": round(100 * quick / total, 2),
    }


def fetch_eventual_success_cases(source: str, min_failed_attempts: int) -> pd.DataFrame:
    """Scenario 2: users who failed for a run of >= min_failed_attempts
    attempts before eventually passing both AUTHENTICITY and CALLBACK.
    Includes the TXN_ID of the successful attempt (fraud-suspected rows only,
    per your requirement -- not shown for scenario 1 or 3)."""
    query = _PARSED_CTE.format(table=uidb_client.TABLE_NAME, source=_escape(source)) + f"""
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
    return uidb_client.run_raw_query(query)


def fetch_total_users(source: str) -> int:
    """Count of unique users (distinct BASE_TXN_ID) for a source -- the
    denominator for the burst-pattern percentage below."""
    query = f"""
SELECT COUNT(DISTINCT LEFT(TXN_ID, CHARINDEX('_', TXN_ID) - 1)) AS TOTAL_USERS
FROM {uidb_client.TABLE_NAME}
WHERE SOURCE = '{_escape(source)}'
  AND CHARINDEX('_', TXN_ID) > 0
  AND CHARINDEX('~', TXN_ID) > 0
"""
    df = uidb_client.run_raw_query(query)
    if df.empty or df.iloc[0]["TOTAL_USERS"] is None:
        return 0
    return int(df.iloc[0]["TOTAL_USERS"])


_PARSED_TIME_CTE = """
WITH parsed AS (
    SELECT
        TXN_ID,
        LEFT(TXN_ID, CHARINDEX('_', TXN_ID) - 1) AS BASE_TXN_ID,
        CAST(SUBSTRING(TXN_ID, CHARINDEX('~', TXN_ID) + 1, LEN(TXN_ID)) AS INT) AS ATTEMPT_NO,
        COALESCE(REQUEST_HIT_DATETIME, HEAD_NOD_REQUEST_HIT_DATETIME) AS ATTEMPT_TIME,
        SOURCE
    FROM {table}
    WHERE SOURCE = '{source}'
      AND CHARINDEX('_', TXN_ID) > 0
      AND CHARINDEX('~', TXN_ID) > 0
),
gaps AS (
    SELECT
        BASE_TXN_ID,
        ATTEMPT_NO,
        DATEDIFF(
            SECOND,
            LAG(ATTEMPT_TIME) OVER (PARTITION BY BASE_TXN_ID ORDER BY ATTEMPT_NO),
            ATTEMPT_TIME
        ) AS GAP_SECONDS
    FROM parsed
),
per_user_velocity AS (
    SELECT
        BASE_TXN_ID,
        COUNT(*) AS TOTAL_ATTEMPTS,
        MIN(GAP_SECONDS) AS MIN_GAP_SECONDS,
        SUM(CASE WHEN GAP_SECONDS IS NOT NULL AND GAP_SECONDS <= {burst_gap_seconds}
                 THEN 1 ELSE 0 END) AS BURST_PAIRS
    FROM gaps
    GROUP BY BASE_TXN_ID
)
"""


def fetch_burst_cases(source: str, burst_gap_seconds: int, min_burst_pairs: int) -> pd.DataFrame:
    """Scenario 4: users with at least `min_burst_pairs` consecutive attempts
    less than `burst_gap_seconds` apart -- rapid-fire retries suggestive of
    scripted/bot behavior rather than a human manually retrying."""
    query = _PARSED_TIME_CTE.format(
        table=uidb_client.TABLE_NAME,
        source=_escape(source),
        burst_gap_seconds=int(burst_gap_seconds),
    ) + f"""
SELECT
    BASE_TXN_ID,
    TOTAL_ATTEMPTS,
    MIN_GAP_SECONDS,
    BURST_PAIRS
FROM per_user_velocity
WHERE BURST_PAIRS >= {int(min_burst_pairs)}
ORDER BY BURST_PAIRS DESC, MIN_GAP_SECONDS ASC
"""
    return uidb_client.run_raw_query(query)
