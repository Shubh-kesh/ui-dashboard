#!/usr/bin/env python
"""Seed the local docai.LIVE_PHOTO_LOGS with realistic dashboard data.

Applies dba/live_photo_logs_schema.sql (idempotent), then generates a
multi-day, multi-source catalog with per-stage statuses, latencies,
exceptions and multi-attempt user journeys (incl. a few burst/velocity
users) so every dashboard chart and the fraud analysis have signal.

Usage (from ui-dashboard/):
    <venv>/bin/python dba/local_dev_seed.py
    python dba/local_dev_seed.py

Overrides via env: MSSQL_SERVER, MSSQL_USERNAME, MSSQL_PASSWORD, ODBC_DRIVER,
SEED_DAYS, SEED_ROWS_PER_DAY, SEED_RANDOM_SEED.
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import random
import sys

import pyodbc

SCHEMA_FILE = pathlib.Path(__file__).with_name("live_photo_logs_schema.sql")
SERVER = os.getenv("MSSQL_SERVER", "localhost,1433")
USERNAME = os.getenv("MSSQL_USERNAME", "sa")
PASSWORD = os.getenv("MSSQL_PASSWORD", "LocalDev123!")
DRIVER = os.getenv("ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
DATABASE = os.getenv("MSSQL_DATABASE", "docai")

DAYS = int(os.getenv("SEED_DAYS", "14"))
ROWS_PER_DAY = int(os.getenv("SEED_ROWS_PER_DAY", "80"))
RNG = random.Random(int(os.getenv("SEED_RANDOM_SEED", "42")))

SOURCES = ["MOBILE_APP", "NETBANKING", "BRANCH_TAB"]

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


def _stage_attempt(progress: int, fail_at: int | None) -> dict:
    """Return per-stage columns for a pipeline that ran up to `fail_at`.

    `progress` = number of stages attempted; `fail_at` = index of the failing
    stage (None = all attempted stages passed).
    """
    row: dict = {}
    for idx, name in enumerate(STAGES):
        req_col, res_col, status_col, dur_col, exc_col = STAGES[name]
        if idx >= progress:
            row[req_col] = None
            row[res_col] = None
            row[status_col] = None
            row[dur_col] = None
            if exc_col:
                row[exc_col] = None
            continue
        passed = fail_at is None or idx < fail_at
        row[req_col] = 1
        row[res_col] = 1 if passed else 0
        row[status_col] = "PASSED" if passed else "FAILED"
        row[dur_col] = round(RNG.uniform(0.08, 1.8) if passed else RNG.uniform(0.5, 4.0), 3)
        if exc_col:
            row[exc_col] = None if passed else RNG.choice(EXCEPTIONS)
    return row


def _blanks() -> dict:
    row: dict = {}
    for name in STAGES:
        req_col, res_col, status_col, dur_col, exc_col = STAGES[name]
        row[req_col] = row[res_col] = row[status_col] = row[dur_col] = None
        if exc_col:
            row[exc_col] = None
    return row


def _attempt_rows(base: str, attempt_no: int, when: dt.datetime, source: str,
                  passed: bool, fail_stage: int | None, blink: bool) -> dict:
    row = _blanks()
    pipeline = list(STAGES) if blink else list(STAGES)[1:]  # skip blink on head-nod path
    if passed:
        progress, fail_at = len(pipeline), None
    elif fail_stage is None:
        progress, fail_at = len(pipeline), len(pipeline)  # never succeeded
    else:
        progress, fail_at = fail_stage + 1, fail_stage
    stage_cols = _stage_attempt(progress, fail_at)
    for name in pipeline:
        req_col, res_col, status_col, dur_col, exc_col = STAGES[name]
        row[req_col] = stage_cols[req_col]
        row[res_col] = stage_cols[res_col]
        row[status_col] = stage_cols[status_col]
        row[dur_col] = stage_cols[dur_col]
        if exc_col:
            row[exc_col] = stage_cols[exc_col]

    row.update({
        "TXN_ID": f"{base}~{attempt_no}",
        "REQUEST_HIT_DATETIME": when if blink else None,
        "HEAD_NOD_REQUEST_HIT_DATETIME": None if blink else when,
        "SOURCE": source,
        "TRACKING_ID": f"TRK{base[-8:].upper()}{attempt_no}",
        "FRAUD_ATTEMPT": None,
        "USER_REVIEW": "REVIEW PENDING",
    })
    return row


def generate_rows() -> list[dict]:
    rows: list[dict] = []
    today = dt.date.today()
    for day_offset in range(DAYS):
        day = today - dt.timedelta(days=day_offset)
        for source in SOURCES:
            n = RNG.randint(int(ROWS_PER_DAY * 0.7), int(ROWS_PER_DAY * 1.3))
            for _ in range(n):
                base_ts = dt.datetime.combine(
                    day, dt.time(RNG.randint(0, 23), RNG.randint(0, 59), RNG.randint(0, 59)))
                base = f"{base_ts.strftime('%Y%m%d%H%M%S')}_{RNG.randrange(16**8):08x}"

                roll = RNG.random()
                if roll < 0.04:            # burst / scripted retries
                    attempts = RNG.randint(3, 6)
                    when = base_ts
                    for a in range(1, attempts + 1):
                        blink = RNG.random() < 0.8
                        passed = a == attempts and RNG.random() < 0.5
                        rows.append(_attempt_rows(base, a, when, source, passed, None if passed else RNG.randint(0, 5), blink))
                        when += dt.timedelta(seconds=RNG.randint(1, 4))
                elif roll < 0.10:          # never succeeded
                    attempts = RNG.randint(1, 3)
                    when = base_ts
                    for a in range(1, attempts + 1):
                        blink = RNG.random() < 0.8
                        fail_stage = None if RNG.random() < 0.5 else RNG.randint(0, 5)
                        rows.append(_attempt_rows(base, a, when, source, False, fail_stage, blink))
                        when += dt.timedelta(seconds=RNG.randint(20, 180))
                else:                       # normal (usually passes, may retry)
                    attempts = RNG.choices([1, 2, 3, 4], weights=[0.72, 0.16, 0.08, 0.04])[0]
                    when = base_ts
                    for a in range(1, attempts + 1):
                        blink = RNG.random() < 0.85
                        passed = a == attempts and RNG.random() < 0.9
                        rows.append(_attempt_rows(base, a, when, source, passed,
                                                  None if passed else RNG.randint(1, 5), blink))
                        when += dt.timedelta(seconds=RNG.randint(30, 300))
    return rows


def insert_rows(rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in cols)
    col_sql = ", ".join(cols)
    sql = f"INSERT INTO LIVE_PHOTO_LOGS ({col_sql}) VALUES ({placeholders})"
    values = [tuple(r[c] for c in cols) for r in rows]

    conn = _connect(DATABASE)
    cur = conn.cursor()
    cur.execute("DELETE FROM LIVE_PHOTO_LOGS WHERE SOURCE IN (?, ?, ?)", *SOURCES)
    cur.fast_executemany = True
    cur.executemany(sql, values)
    cur.close()
    conn.close()
    return len(values)


def main() -> None:
    if not SCHEMA_FILE.exists():
        sys.exit(f"missing {SCHEMA_FILE}")
    n_batches = apply_schema()
    rows = generate_rows()
    n = insert_rows(rows)
    print(f"OK: {n_batches} schema batches applied on {SERVER}/{DATABASE}")
    print(f"Seeded {n} LIVE_PHOTO_LOGS rows across {DAYS} days x {len(SOURCES)} sources "
          f"({', '.join(SOURCES)})")


if __name__ == "__main__":
    main()
