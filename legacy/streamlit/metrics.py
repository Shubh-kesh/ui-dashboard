"""
Transforms the raw catalog DataFrame (from uidb_client.fetch_txn_data) into
dashboard-ready aggregates: daily volume, per-stage status breakdowns,
funnel counts, latency stats, and exception rows.
"""

import pandas as pd

# Maps a human-readable stage name to its (request, response, status, duration,
# exception) column names in the catalog table. `exception` is None where the
# schema doesn't have a stage-specific exception column.
STAGES: dict[str, dict[str, str | None]] = {
    "Blink": {
        "request": "BLINK_REQUEST",
        "response": "BLINK_RESPONSE",
        "status": "BLINK_STATUS",
        "duration": "BLINK_RESPONSE_DURATION",
        "exception": "EXCEPTION_MESSAGE",  # shared/general exception column
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

# Ordered stage sequence for the funnel chart (pipeline order)
FUNNEL_ORDER = ["Blink", "Head Nod", "Authenticity", "Image Seg", "Verify Token", "Callback"]


def add_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """Adds a plain DATE column derived from REQUEST_HIT_DATETIME (populated
    when blink was attempted), falling back to HEAD_NOD_REQUEST_HIT_DATETIME
    (populated when head-nod was attempted instead) when the former is null."""
    if df.empty:
        return df
    df = df.copy()

    if "REQUEST_HIT_DATETIME" in df.columns:
        primary = pd.to_datetime(df["REQUEST_HIT_DATETIME"], errors="coerce")
    else:
        primary = pd.Series(pd.NaT, index=df.index)

    if "HEAD_NOD_REQUEST_HIT_DATETIME" in df.columns:
        fallback = pd.to_datetime(df["HEAD_NOD_REQUEST_HIT_DATETIME"], errors="coerce")
    else:
        fallback = pd.Series(pd.NaT, index=df.index)

    combined = primary.fillna(fallback)
    df["DATE"] = combined.dt.date
    return df


def daily_volume(df: pd.DataFrame) -> pd.DataFrame:
    """Transaction count per day."""
    if df.empty:
        return pd.DataFrame(columns=["DATE", "COUNT"])
    df = add_date_column(df)
    out = df.groupby("DATE").size().reset_index(name="COUNT")
    return out.sort_values("DATE")


def stage_status_breakdown(df: pd.DataFrame, stage: str) -> pd.DataFrame:
    """Count of each distinct STATUS value for a stage, per day.
    Returns columns: DATE, STATUS, COUNT."""
    status_col = STAGES[stage]["status"]
    if df.empty or status_col not in df.columns:
        return pd.DataFrame(columns=["DATE", "STATUS", "COUNT"])

    d = add_date_column(df)
    d = d[[("DATE"), status_col]].copy()
    d[status_col] = d[status_col].fillna("NULL")
    out = d.groupby(["DATE", status_col]).size().reset_index(name="COUNT")
    out = out.rename(columns={status_col: "STATUS"})
    return out.sort_values("DATE")


def funnel_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Count of txns that completed (RESPONSE == 1/True) at each stage,
    in pipeline order. Returns columns: STAGE, COUNT."""
    rows = []
    for stage in FUNNEL_ORDER:
        resp_col = STAGES[stage]["response"]
        if df.empty or resp_col not in df.columns:
            rows.append({"STAGE": stage, "COUNT": 0})
            continue
        count = int(df[resp_col].fillna(False).astype(bool).sum())
        rows.append({"STAGE": stage, "COUNT": count})
    return pd.DataFrame(rows)


def latency_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Mean / p50 / p95 latency per stage, from *_RESPONSE_DURATION columns.
    Returns columns: STAGE, MEAN, P50, P95, N."""
    rows = []
    for stage, cols in STAGES.items():
        dur_col = cols["duration"]
        if df.empty or dur_col not in df.columns:
            continue
        vals = df[dur_col].dropna()
        if vals.empty:
            continue
        rows.append({
            "STAGE": stage,
            "MEAN": round(vals.mean(), 3),
            "P50": round(vals.quantile(0.5), 3),
            "P95": round(vals.quantile(0.95), 3),
            "N": int(vals.count()),
        })
    return pd.DataFrame(rows)


def latency_raw_long(df: pd.DataFrame) -> pd.DataFrame:
    """Long-format (STAGE, DURATION) table across all stages, for a box plot."""
    frames = []
    for stage, cols in STAGES.items():
        dur_col = cols["duration"]
        if df.empty or dur_col not in df.columns:
            continue
        vals = df[dur_col].dropna()
        if vals.empty:
            continue
        frames.append(pd.DataFrame({"STAGE": stage, "DURATION": vals}))
    if not frames:
        return pd.DataFrame(columns=["STAGE", "DURATION"])
    return pd.concat(frames, ignore_index=True)


def exception_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows where any exception column is non-null/non-empty."""
    exception_cols = [c["exception"] for c in STAGES.values() if c["exception"]]
    exception_cols = list(dict.fromkeys(exception_cols))  # dedupe, keep order
    present_cols = [c for c in exception_cols if c in df.columns]
    if df.empty or not present_cols:
        return pd.DataFrame()

    mask = pd.Series(False, index=df.index)
    for c in present_cols:
        mask = mask | df[c].notna() & (df[c].astype(str).str.strip() != "")

    id_cols = [c for c in ["TXN_ID", "TRACKING_ID", "REQUEST_HIT_DATETIME", "SOURCE"] if c in df.columns]
    return df.loc[mask, id_cols + present_cols].sort_values(
        "REQUEST_HIT_DATETIME", ascending=False
    ) if "REQUEST_HIT_DATETIME" in df.columns else df.loc[mask, id_cols + present_cols]


def kpi_summary(df: pd.DataFrame) -> dict:
    """Top-line numbers for the KPI row."""
    if df.empty:
        return {"total_txns": 0, "callback_success_rate": None, "avg_callback_latency": None}

    total = len(df)
    callback_rate = None
    if "CALLBACK_RES" in df.columns:
        callback_rate = round(100 * df["CALLBACK_RES"].fillna(False).astype(bool).mean(), 1)

    avg_latency = None
    if "CALLBACK_RES_DURATION" in df.columns:
        vals = df["CALLBACK_RES_DURATION"].dropna()
        if not vals.empty:
            avg_latency = round(vals.mean(), 3)

    return {
        "total_txns": total,
        "callback_success_rate": callback_rate,
        "avg_callback_latency": avg_latency,
    }
