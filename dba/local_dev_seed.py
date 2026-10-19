#!/usr/bin/env python
"""Seed the local docai catalog tables with realistic dashboard data.

Applies dba/live_photo_logs_schema.sql (idempotent, creates BOTH tables), then
generates a UAT-like catalog for the LIVEPHOTO_UCJv5 source with per-stage
statuses, latencies, exceptions, review columns and multi-attempt user journeys
(incl. a few burst/velocity users) so every dashboard chart and the fraud
analysis have signal.

Status semantics mirror UAT: a journey uses one liveness method (blink OR head
nod) and records the other as "NOT REQUIRED"; skipped stages are "NOT REQUIRED"
except VERIFYTOKEN_STATUS / CALLBACK_STATUS which stay NULL; failed stages carry
specific codes (FAILED / FB01 / FB02 / FB03). TXN_IDs use the UAT shape
"<uuid>_<hex8>~<attempt>".

Data is split to mirror production:
    LIVE_PHOTO_LOGS          - the most recent LIVE_DAYS days (default 7)
    LIVE_PHOTO_LOGS_ARCHIVE  - the preceding ARCHIVE_DAYS days (default 23)

Usage (from ui-dashboard/):
    <venv>/bin/python dba/local_dev_seed.py
    python dba/local_dev_seed.py

Overrides via env: MSSQL_SERVER, MSSQL_USERNAME, MSSQL_PASSWORD, ODBC_DRIVER,
LIVE_PHOTO_TABLE, LIVE_PHOTO_ARCHIVE_TABLE, SEED_LIVE_DAYS, SEED_ARCHIVE_DAYS,
SEED_ROWS_PER_DAY, SEED_RANDOM_SEED.
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import random
import sys
import uuid

import pyodbc

SCHEMA_FILE = pathlib.Path(__file__).with_name("live_photo_logs_schema.sql")
SERVER = os.getenv("MSSQL_SERVER", "localhost,1433")
USERNAME = os.getenv("MSSQL_USERNAME", "sa")
PASSWORD = os.getenv("MSSQL_PASSWORD", "LocalDev123!")
DRIVER = os.getenv("ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
DATABASE = os.getenv("MSSQL_DATABASE", "docai")
LIVE_TABLE = os.getenv("LIVE_PHOTO_TABLE", "LIVE_PHOTO_LOGS")
ARCHIVE_TABLE = os.getenv("LIVE_PHOTO_ARCHIVE_TABLE", "LIVE_PHOTO_LOGS_ARCHIVE")

LIVE_DAYS = int(os.getenv("SEED_LIVE_DAYS", "7"))
ARCHIVE_DAYS = int(os.getenv("SEED_ARCHIVE_DAYS", "23"))
ROWS_PER_DAY = int(os.getenv("SEED_ROWS_PER_DAY", "300"))
RNG = random.Random(int(os.getenv("SEED_RANDOM_SEED", "42")))

# Source name matches the UAT catalog.
SOURCES = ["LIVEPHOTO_UCJv5"]
# Sources written by earlier seed versions; cleared on reseed so only UAT-like
# data remains.
_LEGACY_SOURCES = ["MOBILE_APP", "NETBANKING", "BRANCH_TAB"]
_CLEAR_SOURCES = SOURCES + _LEGACY_SOURCES

USER_REVIEW_VALUES = ["ACCEPT", "REJECTED", "REVIEW PENDING", None]
USER_REVIEW_WEIGHTS = [0.50, 0.15, 0.25, 0.10]

# stage -> (request, response, status, duration, exception) column names.
STAGES = {
    "blink":       ("BLINK_REQUEST", "BLINK_RESPONSE", "BLINK_STATUS",
                    "BLINK_RESPONSE_DURATION", "EXCEPTION_MESSAGE"),
    "head_nod":    ("HEAD_NOD_REQUEST", "HEAD_NOD_RESPONSE", "HEAD_NOD_STATUS",
                    "HEAD_NOD_RESPONSE_DURATION", "HEAD_NOD_EXCEPTION_MESSAGE"),
    "authenticity": ("AUTHENTICITY_REQUEST", "AUTHENTICITY_RESPONSE", "AUTHENTICITY_STATUS",
                     "AUTHENTICITY_RESPONSE_DURATION", None),
    "image_seg":   ("IMAGE_SEG_REQUEST", "IMAGE_SEG_RESPONSE", "IMAGE_SEG_STATUS",
                    "IMAGE_SEG_RESPONSE_DURATION", None),
    "verify_token": ("VERIFYTOKEN_REQ", "VERIFYTOKEN_RES", "VERIFYTOKEN_STATUS",
                     "VERIFY_TOKEN_RES_DURATION", "VERIFY_TOKEN_EXCEPTION"),
    "callback":    ("CALLBACK_REQ", "CALLBACK_RES", "CALLBACK_STATUS",
                    "CALLBACK_RES_DURATION", "CALLBACK_EXCEPTION"),
}

EXCEPTIONS = [
    "Face not detected in frame",
    "Blink not detected within timeout",
    "Liveness check inconclusive",
    "Image quality too low",
    "Upstream timeout",
    "Callback delivery failed",
]

# Real deployments emit specific failure codes (e.g. FB01/FB02) in the status
# columns; mix them in so "Status by stage" shows raw DB values.
FAILURE_CODES = ["FAILED", "FB01", "FB02", "FB03"]

# UAT semantics:
#   * A journey uses ONE liveness method (blink OR head nod); the other stage is
#     recorded as "NOT REQUIRED".
#   * Stages skipped because an earlier stage failed are also "NOT REQUIRED",
#     except VERIFYTOKEN_STATUS / CALLBACK_STATUS which are left NULL.
NOT_REQUIRED = "NOT REQUIRED"
NULL_WHEN_UNATTEMPTED = {"verify_token", "callback"}
LIVENESS_METHODS = ["blink", "head_nod"]


def batches(sql_text: str):
    """Yield statement batches split on standalone GO lines."""
    buf: list[str] = []
    for line in sql_text.splitlines():
        if line.strip().upper() == "GO":
            batch = "\n".join(buf).strip()
            if batch:
                yield batch
            buf = []
        else:
            buf.append(line)
    tail = "\n".join(buf).strip()
    if tail:
        yield tail


def _connect(database: str) -> pyodbc.Connection:
    return pyodbc.connect(
        f"DRIVER={{{DRIVER}}};SERVER={SERVER};DATABASE={database};"
        f"UID={USERNAME};PWD={PASSWORD};TrustServerCertificate=yes;Encrypt=yes;",
        autocommit=True,
    )


def apply_schema() -> int:
    conn = _connect("master")
    cur = conn.cursor()
    n = 0
    for batch in batches(SCHEMA_FILE.read_text()):
        cur.execute(batch)
        n += 1
    cur.close()
    conn.close()
    return n


def _blank_stage(row: dict, name: str, status: str | None) -> None:
    req_col, res_col, status_col, dur_col, exc_col = STAGES[name]
    row[req_col] = None
    row[res_col] = None
    row[dur_col] = None
    row[status_col] = status
    if exc_col:
        row[exc_col] = None


def _mark_not_required(row: dict, name: str) -> None:
    """Stage was skipped: 'NOT REQUIRED', or NULL for verify-token/callback."""
    _blank_stage(row, name, None if name in NULL_WHEN_UNATTEMPTED else NOT_REQUIRED)


def _mark_stage(row: dict, name: str, *, passed: bool) -> None:
    req_col, res_col, status_col, dur_col, exc_col = STAGES[name]
    row[req_col] = 1
    row[res_col] = 1 if passed else 0
    if passed:
        row[status_col] = "PASSED"
        row[dur_col] = round(RNG.uniform(0.08, 1.8), 3)
    else:
        row[status_col] = RNG.choices(FAILURE_CODES, weights=[0.55, 0.2, 0.15, 0.10])[0]
        row[dur_col] = round(RNG.uniform(0.5, 4.0), 3)
    if exc_col:
        row[exc_col] = None if passed else RNG.choice(EXCEPTIONS)


def _pipeline(method: str, verify_used: bool) -> list[str]:
    order = [method, "authenticity", "image_seg"]
    if verify_used:
        order.append("verify_token")
    order.append("callback")
    return order


def _blanks() -> dict:
    row: dict = {}
    for name in STAGES:
        req_col, res_col, status_col, dur_col, exc_col = STAGES[name]
        row[req_col] = row[res_col] = row[status_col] = row[dur_col] = None
        if exc_col:
            row[exc_col] = None
    return row


def _fraud_attempt_value() -> int | None:
    if RNG.random() < 0.05:
        return 1
    if RNG.random() < 0.10:
        return None
    return 0


def _attempt_rows(base: str, attempt_no: int, when: dt.datetime, source: str,
                  method: str, passed: bool, fail_stage: str | None,
                  verify_used: bool) -> dict:
    row = _blanks()
    # Only one liveness method is exercised per journey.
    _mark_not_required(row, "head_nod" if method == "blink" else "blink")

    order = _pipeline(method, verify_used)
    if passed:
        for name in order:
            _mark_stage(row, name, passed=True)
    else:
        fail_idx = order.index(fail_stage) if fail_stage in order else len(order) - 1
        for idx, name in enumerate(order):
            if idx < fail_idx:
                _mark_stage(row, name, passed=True)
            elif idx == fail_idx:
                _mark_stage(row, name, passed=False)
            else:
                _mark_not_required(row, name)
    if not verify_used:
        _mark_not_required(row, "verify_token")

    row.update({
        "TXN_ID": f"{base}~{attempt_no}",
        "REQUEST_HIT_DATETIME": when if method == "blink" else None,
        "HEAD_NOD_REQUEST_HIT_DATETIME": None if method == "blink" else when,
        "SOURCE": source,
        "TRACKING_ID": "NOT_FOUND" if RNG.random() < 0.85 else f"TRK{RNG.randrange(16**8):08X}",
        "FRAUD_ATTEMPT": _fraud_attempt_value(),
        "USER_REVIEW": RNG.choices(USER_REVIEW_VALUES, weights=USER_REVIEW_WEIGHTS)[0],
    })
    return row


def generate_rows(days: int, start_offset: int) -> list[dict]:
    """Generate rows for `days` calendar days starting `start_offset` days ago."""
    rows: list[dict] = []
    today = dt.date.today()
    for day_offset in range(start_offset, start_offset + days):
        day = today - dt.timedelta(days=day_offset)
        for source in SOURCES:
            n = RNG.randint(int(ROWS_PER_DAY * 0.7), int(ROWS_PER_DAY * 1.3))
            for _ in range(n):
                base_ts = dt.datetime.combine(
                    day, dt.time(RNG.randint(0, 23), RNG.randint(0, 59), RNG.randint(0, 59)))
                # UAT TXN_ID shape: "<uuid>_<hex8>~<attempt>".
                base = f"{uuid.uuid4()}_{RNG.randrange(16**8):08x}"
                method = RNG.choices(LIVENESS_METHODS, weights=[0.85, 0.15])[0]
                verify_used = RNG.random() < 0.10
                order = _pipeline(method, verify_used)

                roll = RNG.random()
                if roll < 0.04:            # burst / scripted retries
                    attempts = RNG.randint(3, 6)
                    when = base_ts
                    for a in range(1, attempts + 1):
                        passed = a == attempts and RNG.random() < 0.5
                        fail = None if passed else RNG.choice(order)
                        rows.append(_attempt_rows(base, a, when, source, method, passed, fail, verify_used))
                        when += dt.timedelta(seconds=RNG.randint(1, 4))
                elif roll < 0.10:          # never succeeded within attempts
                    attempts = RNG.randint(1, 3)
                    when = base_ts
                    for a in range(1, attempts + 1):
                        fail = "callback" if RNG.random() < 0.5 else RNG.choice(order)
                        rows.append(_attempt_rows(base, a, when, source, method, False, fail, verify_used))
                        when += dt.timedelta(seconds=RNG.randint(20, 180))
                else:                       # normal (usually passes, may retry)
                    attempts = RNG.choices([1, 2, 3, 4], weights=[0.72, 0.16, 0.08, 0.04])[0]
                    when = base_ts
                    for a in range(1, attempts + 1):
                        passed = a == attempts and RNG.random() < 0.9
                        fail = None if passed else RNG.choice(order[1:])
                        rows.append(_attempt_rows(base, a, when, source, method, passed, fail, verify_used))
                        when += dt.timedelta(seconds=RNG.randint(30, 300))
    return rows


def insert_rows(table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in cols)
    col_sql = ", ".join(cols)
    sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"
    values = [tuple(r[c] for c in cols) for r in rows]

    conn = _connect(DATABASE)
    cur = conn.cursor()
    marks = ", ".join("?" for _ in _CLEAR_SOURCES)
    cur.execute(f"DELETE FROM {table} WHERE SOURCE IN ({marks})", *_CLEAR_SOURCES)
    cur.fast_executemany = True
    cur.executemany(sql, values)
    cur.close()
    conn.close()
    return len(values)


def main() -> None:
    if not SCHEMA_FILE.exists():
        sys.exit(f"missing {SCHEMA_FILE}")
    n_batches = apply_schema()
    live_rows = generate_rows(LIVE_DAYS, 0)
    archive_rows = generate_rows(ARCHIVE_DAYS, LIVE_DAYS)
    n_live = insert_rows(LIVE_TABLE, live_rows)
    n_archive = insert_rows(ARCHIVE_TABLE, archive_rows)
    print(f"OK: {n_batches} schema batches applied on {SERVER}/{DATABASE} "
          f"({LIVE_TABLE}, {ARCHIVE_TABLE})")
    print(f"Seeded {n_live} rows -> {LIVE_TABLE} (last {LIVE_DAYS} days)")
    print(f"Seeded {n_archive} rows -> {ARCHIVE_TABLE} (days {LIVE_DAYS}..{LIVE_DAYS + ARCHIVE_DAYS})")


if __name__ == "__main__":
    main()
