"""Aggregations over the raw catalog DataFrame -> JSON-safe dashboard payloads.

Ported from the original Streamlit ``metrics.py``; ``STAGES`` / ``FUNNEL_ORDER``
definitions are unchanged so the numbers match the old dashboard.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any

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

FUNNEL_ORDER = ["Blink", "Head Nod", "Authenticity", "Image Seg", "Verify Token", "Callback"]

# Cap on raw latency points returned per request (for the box plot).
_RAW_LATENCY_CAP = 4000


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


def add_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """Add a plain DATE derived from REQUEST_HIT_DATETIME, falling back to
    HEAD_NOD_REQUEST_HIT_DATETIME when the former is null."""
    if df.empty:
        return df
    df = df.copy()
    primary = pd.to_datetime(df["REQUEST_HIT_DATETIME"], errors="coerce") \
        if "REQUEST_HIT_DATETIME" in df.columns else pd.Series(pd.NaT, index=df.index)
    fallback = pd.to_datetime(df["HEAD_NOD_REQUEST_HIT_DATETIME"], errors="coerce") \
        if "HEAD_NOD_REQUEST_HIT_DATETIME" in df.columns else pd.Series(pd.NaT, index=df.index)
    df["DATE"] = primary.fillna(fallback).dt.date
    return df


def daily_volume(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    d = add_date_column(df)
    out = (d.groupby("DATE").size().reset_index(name="COUNT")
           .rename(columns={"DATE": "date", "COUNT": "count"}).sort_values("date"))
    return _records(out)


def stage_status_breakdown(df: pd.DataFrame, stage: str) -> list[dict]:
    status_col = STAGES[stage]["status"]
    if df.empty or status_col not in df.columns:
        return []
    d = add_date_column(df)[["DATE", status_col]].copy()
    d[status_col] = d[status_col].fillna("NULL")
    out = (d.groupby(["DATE", status_col]).size().reset_index(name="COUNT")
           .rename(columns={"DATE": "date", status_col: "status", "COUNT": "count"})
           .sort_values("date"))
    return _records(out)


def funnel_counts(df: pd.DataFrame) -> list[dict]:
    rows = []
    for stage in FUNNEL_ORDER:
        resp_col = STAGES[stage]["response"]
        if df.empty or resp_col not in df.columns:
            rows.append({"stage": stage, "count": 0, "stage_key": stage})
            continue
        count = int(df[resp_col].eq(True).sum())
        rows.append({"stage": stage, "count": count})
    return rows


def latency_stats(df: pd.DataFrame) -> list[dict]:
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
            "p50": round(float(vals.quantile(0.5)), 3),
            "p95": round(float(vals.quantile(0.95)), 3),
            "n": int(vals.count()),
        })
    return rows


def latency_raw_long(df: pd.DataFrame, cap: int = _RAW_LATENCY_CAP) -> list[dict]:
    frames = []
    for stage, cols in STAGES.items():
        dur_col = cols["duration"]
        if df.empty or dur_col not in df.columns:
            continue
        vals = pd.to_numeric(df[dur_col], errors="coerce").dropna()
        if vals.empty:
            continue
        frames.append(pd.DataFrame({"stage": stage, "duration": vals}))
    if not frames:
        return []
    long_df = pd.concat(frames, ignore_index=True)
    if len(long_df) > cap:
        long_df = long_df.sample(n=cap, random_state=0)
    return _records(long_df)


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


def build_dashboard(df: pd.DataFrame) -> dict:
    """Assemble the full dashboard payload from a catalog DataFrame."""
    return {
        "kpis": kpi_summary(df),
        "daily_volume": daily_volume(df),
        "funnel": funnel_counts(df),
        "stage_breakdown": {stage: stage_status_breakdown(df, stage) for stage in STAGES},
        "latency": {
            "stats": latency_stats(df),
            "raw": latency_raw_long(df),
        },
        "exceptions": exception_rows(df),
    }
