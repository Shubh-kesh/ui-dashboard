"""Aggregations over the raw catalog DataFrame -> JSON-safe dashboard payloads.

Ported from the original Streamlit ``metrics.py``; the ``STAGES`` definitions are
unchanged so the numbers match the old dashboard.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any, Callable

import numpy as np
import pandas as pd

# stage name -> column names in the catalog table.
STAGES: dict[str, dict[str, str | None]] = {
    "Blink": {
        "request": "BLINK_REQUEST",
        "response": "BLINK_RESPONSE",
        "status": "BLINK_STATUS",
        "duration": "BLINK_RESPONSE_DURATION",
        "exception": "EXCEPTION_MESSAGE",
    },
    "Head Nod": {
        "request": "HEAD_NOD_REQUEST",
        "response": "HEAD_NOD_RESPONSE",
        "status": "HEAD_NOD_STATUS",
        "duration": "HEAD_NOD_RESPONSE_DURATION",
        "exception": "HEAD_NOD_EXCEPTION_MESSAGE",
    },
    "Authenticity": {
        "request": "AUTHENTICITY_REQUEST",
        "response": "AUTHENTICITY_RESPONSE",
        "status": "AUTHENTICITY_STATUS",
        "duration": "AUTHENTICITY_RESPONSE_DURATION",
        "exception": None,
    },
    "Image Seg": {
        "request": "IMAGE_SEG_REQUEST",
        "response": "IMAGE_SEG_RESPONSE",
        "status": "IMAGE_SEG_STATUS",
        "duration": "IMAGE_SEG_RESPONSE_DURATION",
        "exception": None,
    },
    "Verify Token": {
        "request": "VERIFYTOKEN_REQ",
        "response": "VERIFYTOKEN_RES",
        "status": "VERIFYTOKEN_STATUS",
        "duration": "VERIFY_TOKEN_RES_DURATION",
        "exception": "VERIFY_TOKEN_EXCEPTION",
    },
    "Callback": {
        "request": "CALLBACK_REQ",
        "response": "CALLBACK_RES",
        "status": "CALLBACK_STATUS",
        "duration": "CALLBACK_RES_DURATION",
        "exception": "CALLBACK_EXCEPTION",
    },
}

# Breakdown keys rendered as extra tabs in the "Status by stage" module.
REVIEW_BREAKDOWNS = ["Fraud Attempt", "User Review"]

# Granularity key -> bucket size in minutes.
GRANULARITIES: dict[str, int] = {"15m": 15, "30m": 30, "1h": 60, "6h": 360, "1d": 1440}


def _clean(value: Any) -> Any:
    """Convert numpy/pandas scalars to JSON-safe Python values."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (pd.Timestamp, dt.datetime)):
        return value.isoformat(sep=" ")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if math.isnan(float(value)) else float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in rec.items()} for rec in df.to_dict(orient="records")]


def _event_datetimes(df: pd.DataFrame) -> pd.Series:
    """Effective event timestamp per row (blink vs head-nod path)."""
    primary = pd.to_datetime(df["REQUEST_HIT_DATETIME"], errors="coerce") \
        if "REQUEST_HIT_DATETIME" in df.columns else pd.Series(pd.NaT, index=df.index)
    fallback = pd.to_datetime(df["HEAD_NOD_REQUEST_HIT_DATETIME"], errors="coerce") \
        if "HEAD_NOD_REQUEST_HIT_DATETIME" in df.columns else pd.Series(pd.NaT, index=df.index)
    return primary.fillna(fallback)


def add_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """Add a plain DATE derived from the effective event timestamp."""
    if df.empty:
        return df
    df = df.copy()
    df["DATE"] = _event_datetimes(df).dt.date
    return df


def _breakdown(df: pd.DataFrame, column: str,
               labeler: Callable[[Any], str] | None = None) -> list[dict]:
    """Count rows per (DATE, value) for a given column."""
    if df.empty or column not in df.columns:
        return []
    d = add_date_column(df)[["DATE", column]].copy()
    if labeler is not None:
        d[column] = d[column].map(labeler)
    else:
        d[column] = d[column].where(d[column].notna(), "NULL")
    out = (d.groupby(["DATE", column]).size().reset_index(name="COUNT")
           .rename(columns={"DATE": "date", column: "status", "COUNT": "count"})
           .sort_values("date"))
    return _records(out)


def _fraud_label(value: Any) -> str:
    try:
        if pd.isna(value):
            return "NULL"
    except (TypeError, ValueError):
        pass
    return "FRAUD" if bool(value) else "GENUINE"


def stage_status_breakdown(df: pd.DataFrame, stage: str) -> list[dict]:
    return _breakdown(df, STAGES[stage]["status"])


def fraud_attempt_breakdown(df: pd.DataFrame) -> list[dict]:
    return _breakdown(df, "FRAUD_ATTEMPT", labeler=_fraud_label)


def user_review_breakdown(df: pd.DataFrame) -> list[dict]:
    return _breakdown(df, "USER_REVIEW")


def _auto_granularity(start: dt.date, end: dt.date) -> str:
    span_days = max((end - start).days + 1, 1)
    if span_days <= 1:
        return "30m"
    if span_days <= 3:
        return "1h"
    if span_days <= 14:
        return "6h"
    return "1d"


def _parse_hhmm(value: str | None) -> dt.time | None:
    if not value:
        return None
    try:
        hh, mm = value.split(":")
        return dt.time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return None


def time_series(
    df: pd.DataFrame,
    start: dt.date,
    end: dt.date,
    granularity: str = "auto",
    start_time: str | None = None,
    end_time: str | None = None,
) -> list[dict]:
    """Count rows per time bucket inside a [start, end] date window.

    ``start_time``/``end_time`` (HH:MM) restrict to a time-of-day window applied
    to every selected day, so e.g. a 7-day range with 09:00-18:00 yields one
    bucket series per interval across those hours. No row limit is applied.
    """
    bucket = _auto_granularity(start, end) if granularity == "auto" else granularity
    if bucket not in GRANULARITIES:
        bucket = "1d"
    minutes = GRANULARITIES[bucket]

    if df.empty:
        return []

    event = _event_datetimes(df)
    mask = event.notna()
    t_from = _parse_hhmm(start_time)
    t_to = _parse_hhmm(end_time)
    if t_from is not None:
        mask &= event.dt.time >= t_from
    if t_to is not None:
        # Treat the end bound as inclusive of its whole minute.
        t_to = (dt.datetime(2000, 1, 1, t_to.hour, t_to.minute)
                + dt.timedelta(seconds=59)).time()
        mask &= event.dt.time <= t_to

    events = event[mask]
    if events.empty:
        return []

    floored = events.dt.floor(f"{minutes}min")
    counts = floored.value_counts().sort_index()

    # Fill gaps so the axis is continuous.
    full_index = pd.date_range(counts.index.min(), counts.index.max(), freq=f"{minutes}min")
    counts = counts.reindex(full_index, fill_value=0)

    daily = minutes >= 1440
    rows = []
    prev: int | None = None
    for ts, count in counts.items():
        count = int(count)
        delta = None if prev is None or prev == 0 else round(100 * (count - prev) / prev, 2)
        rows.append({
            "bucket": ts.date().isoformat() if daily else ts.isoformat(),
            "count": count,
            "delta_pct": delta,
        })
        prev = count
    return rows


def box_stats(df: pd.DataFrame) -> list[dict]:
    """Per-stage latency distribution summary (min/q1/median/q3/max + p95)."""
    rows = []
    for stage, cols in STAGES.items():
        dur_col = cols["duration"]
        if df.empty or dur_col not in df.columns:
            continue
        vals = pd.to_numeric(df[dur_col], errors="coerce").dropna()
        if vals.empty:
            continue
        rows.append({
            "stage": stage,
            "mean": round(float(vals.mean()), 3),
            "p50": round(float(vals.quantile(0.50)), 3),
            "p95": round(float(vals.quantile(0.95)), 3),
            "min": round(float(vals.min()), 3),
            "q1": round(float(vals.quantile(0.25)), 3),
            "q3": round(float(vals.quantile(0.75)), 3),
            "max": round(float(vals.max()), 3),
            "n": int(vals.count()),
        })
    return rows


def exception_rows(df: pd.DataFrame) -> list[dict]:
    exception_cols = list(dict.fromkeys(
        c["exception"] for c in STAGES.values() if c["exception"]))
    present = [c for c in exception_cols if c in df.columns]
    if df.empty or not present:
        return []
    mask = pd.Series(False, index=df.index)
    for c in present:
        mask = mask | (df[c].notna() & (df[c].astype(str).str.strip() != ""))
    id_cols = [c for c in ["TXN_ID", "TRACKING_ID", "REQUEST_HIT_DATETIME", "SOURCE"]
               if c in df.columns]
    out = df.loc[mask, id_cols + present]
    if "REQUEST_HIT_DATETIME" in out.columns:
        out = out.sort_values("REQUEST_HIT_DATETIME", ascending=False)
    return _records(out)


def kpi_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"total_txns": 0, "callback_success_rate": None, "avg_callback_latency": None}
    callback_rate = None
    if "CALLBACK_RES" in df.columns:
        callback_rate = round(100 * float(df["CALLBACK_RES"].eq(True).mean()), 1)
    avg_latency = None
    if "CALLBACK_RES_DURATION" in df.columns:
        vals = pd.to_numeric(df["CALLBACK_RES_DURATION"], errors="coerce").dropna()
        if not vals.empty:
            avg_latency = round(float(vals.mean()), 3)
    return {
        "total_txns": int(len(df)),
        "callback_success_rate": callback_rate,
        "avg_callback_latency": avg_latency,
    }


def _window_dates(df: pd.DataFrame, start: dt.date | None, end: dt.date | None) -> tuple[dt.date, dt.date]:
    if start is not None and end is not None:
        return start, end
    events = _event_datetimes(df).dropna()
    if events.empty:
        today = dt.date.today()
        return today, today
    return events.min().date(), events.max().date()


def build_dashboard(
    df: pd.DataFrame,
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
    granularity: str = "auto",
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict:
    """Assemble the full dashboard payload from a catalog DataFrame."""
    start_d, end_d = _window_dates(df, start, end)
    breakdown = {stage: stage_status_breakdown(df, stage) for stage in STAGES}
    breakdown["Fraud Attempt"] = fraud_attempt_breakdown(df)
    breakdown["User Review"] = user_review_breakdown(df)
    return {
        "kpis": kpi_summary(df),
        "time_series": time_series(df, start_d, end_d, granularity, start_time, end_time),
        "stage_breakdown": breakdown,
        "latency": {"stats": box_stats(df)},
        "exceptions": exception_rows(df),
    }
