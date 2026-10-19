"""HTTP API routes for the dashboard."""
from __future__ import annotations

import csv
import datetime as dt
import io

from fastapi import APIRouter, Query
from fastapi.responses import Response

from .. import db, queries
from ..config import get_settings
from ..models import (
    DashboardResponse,
    FraudBurstResponse,
    FraudEventualResponse,
    FraudSummaryResponse,
    FraudTotalUsersResponse,
    HealthResponse,
    RawResponse,
    SourcesResponse,
)
from ..services import metrics

router = APIRouter(prefix="/api")


def _clamp_limit(limit: int) -> int:
    settings = get_settings()
    return max(1, min(int(limit), settings.max_row_limit))


def _load_df(start: dt.date, end: dt.date, source: str | None, limit: int):
    sql, params = queries.catalog_query(_clamp_limit(limit), source)
    return db.fetch_df(sql, [start.isoformat(), end.isoformat(), *params])


def _check_range(start: dt.date, end: dt.date) -> None:
    if start > end:
        raise ValueError("start date must be on or before end date")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok" if db.ping() else "degraded",
        database_reachable=db.ping(),
        table=settings.table,
    )


@router.get("/sources", response_model=SourcesResponse)
def sources() -> SourcesResponse:
    df = db.fetch_df(queries.sources_query())
    values = [str(v) for v in df["SOURCE"].dropna().tolist()] if "SOURCE" in df.columns else []
    return SourcesResponse(sources=sorted(set(values)))


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    source: str | None = Query(None),
    limit: int = Query(0),
) -> DashboardResponse:
    _check_range(start, end)
    limit = limit or get_settings().default_row_limit
    df = _load_df(start, end, source, limit)
    payload = metrics.build_dashboard(df)
    return DashboardResponse(
        rows=int(len(df)),
        start=start.isoformat(),
        end=end.isoformat(),
        source=source,
        **payload,
    )


@router.get("/raw", response_model=RawResponse)
def raw(
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    source: str | None = Query(None),
    limit: int = Query(0),
) -> RawResponse:
    _check_range(start, end)
    limit = limit or get_settings().default_row_limit
    df = _load_df(start, end, source, limit)
    df = metrics.add_date_column(df) if not df.empty else df
    rows = [{k: metrics._clean(v) for k, v in rec.items()}
            for rec in df.to_dict(orient="records")] if not df.empty else []
    return RawResponse(columns=list(df.columns), rows=rows, count=len(rows))


@router.get("/raw.csv")
def raw_csv(
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    source: str | None = Query(None),
    limit: int = Query(0),
) -> Response:
    _check_range(start, end)
    limit = limit or get_settings().default_row_limit
    df = _load_df(start, end, source, limit)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    filename = f"catalog_{start.isoformat()}_{end.isoformat()}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/fraud/summary", response_model=FraudSummaryResponse)
def fraud_summary(source: str = Query(...), threshold: int = Query(3, ge=1)) -> FraudSummaryResponse:
    sql, params = queries.fraud_summary_query(source, threshold)
    df = db.fetch_df(sql, params)
    if df.empty or int(df.iloc[0]["TOTAL_USERS"] or 0) == 0:
        return FraudSummaryResponse(source=source, total_users=0, quick_success_users=0,
                                    quick_success_pct=0.0)
    total = int(df.iloc[0]["TOTAL_USERS"])
    quick = int(df.iloc[0]["QUICK_SUCCESS_USERS"] or 0)
    return FraudSummaryResponse(
        source=source, total_users=total, quick_success_users=quick,
        quick_success_pct=round(100 * quick / total, 2),
    )


@router.get("/fraud/total-users", response_model=FraudTotalUsersResponse)
def fraud_total_users(source: str = Query(...)) -> FraudTotalUsersResponse:
    sql, params = queries.fraud_total_users_query(source)
    df = db.fetch_df(sql, params)
    total = 0
    if not df.empty and df.iloc[0]["TOTAL_USERS"] is not None:
        total = int(df.iloc[0]["TOTAL_USERS"])
    return FraudTotalUsersResponse(source=source, total_users=total)


@router.get("/fraud/eventual", response_model=FraudEventualResponse)
def fraud_eventual(source: str = Query(...), min_failed: int = Query(3, ge=1)) -> FraudEventualResponse:
    sql, params = queries.fraud_eventual_query(source, min_failed)
    df = db.fetch_df(sql, params)
    rows = [{k: metrics._clean(v) for k, v in rec.items()}
            for rec in df.to_dict(orient="records")] if not df.empty else []
    return FraudEventualResponse(source=source, rows=rows)


@router.get("/fraud/burst", response_model=FraudBurstResponse)
def fraud_burst(
    source: str = Query(...),
    gap_seconds: int = Query(5, ge=1),
    min_pairs: int = Query(3, ge=1),
) -> FraudBurstResponse:
    total_sql, total_params = queries.fraud_total_users_query(source)
    total_df = db.fetch_df(total_sql, total_params)
    total = int(total_df.iloc[0]["TOTAL_USERS"]) if not total_df.empty and total_df.iloc[0]["TOTAL_USERS"] is not None else 0

    sql, params = queries.fraud_burst_query(source, gap_seconds, min_pairs)
    df = db.fetch_df(sql, params)
    rows = [{k: metrics._clean(v) for k, v in rec.items()}
            for rec in df.to_dict(orient="records")] if not df.empty else []
    pct = round(100 * len(rows) / total, 2) if total else 0.0
    return FraudBurstResponse(
        source=source, total_users=total, burst_cases=len(rows), burst_pct=pct, rows=rows,
    )
