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
    FraudEventualResponse,
    FraudNeverSucceededResponse,
    FraudSummaryResponse,
    HealthResponse,
    RangeResponse,
    RawResponse,
    SourcesResponse,
)
from ..services import metrics

router = APIRouter(prefix="/api")

_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


def _table_name(key: str) -> str:
    """Resolve the table selector ('live'|'archive') to a table name."""
    return get_settings().table_for(key)


def _load_df(table_key: str, start: dt.date, end: dt.date, source: str | None):
    sql, params = queries.catalog_query(_table_name(table_key), source)
    return db.fetch_df(sql, [start.isoformat(), end.isoformat(), *params])


def _check_range(start: dt.date, end: dt.date) -> None:
    if start > end:
        raise ValueError("start date must be on or before end date")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    reachable = db.ping()
    return HealthResponse(
        status="ok" if reachable else "degraded",
        database_reachable=reachable,
        table=settings.table,
        archive_table=settings.archive_table,
    )


@router.get("/sources", response_model=SourcesResponse)
def sources(table: str = Query("live")) -> SourcesResponse:
    df = db.fetch_df(queries.sources_query(_table_name(table)))
    values = [str(v) for v in df["SOURCE"].dropna().tolist()] if "SOURCE" in df.columns else []
    return SourcesResponse(sources=sorted(set(values)))


@router.get("/range", response_model=RangeResponse)
def data_range(table: str = Query("live")) -> RangeResponse:
    resolved = _table_name(table)
    df = db.fetch_df(queries.range_query(resolved))
    if df.empty:
        return RangeResponse(table=resolved, rows=0)
    rec = df.iloc[0]
    return RangeResponse(
        table=resolved,
        min=metrics._clean(rec.get("MIN_TS")),
        max=metrics._clean(rec.get("MAX_TS")),
        rows=int(rec.get("N") or 0),
    )


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    source: str | None = Query(None),
    table: str = Query("live"),
    granularity: str = Query("auto"),
    start_time: str | None = Query(None, pattern=_HHMM),
    end_time: str | None = Query(None, pattern=_HHMM),
) -> DashboardResponse:
    _check_range(start, end)
    if granularity != "auto" and granularity not in metrics.GRANULARITIES:
        raise ValueError(f"unknown granularity {granularity!r}; expected auto or one of "
                         f"{sorted(metrics.GRANULARITIES)}")
    df = _load_df(table, start, end, source)
    payload = metrics.build_dashboard(
        df, start=start, end=end, granularity=granularity,
        start_time=start_time, end_time=end_time,
    )
    return DashboardResponse(
        rows=int(len(df)),
        start=start.isoformat(),
        end=end.isoformat(),
        source=source,
        table=_table_name(table),
        granularity=granularity,
        start_time=start_time,
        end_time=end_time,
        **payload,
    )


@router.get("/raw", response_model=RawResponse)
def raw(
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    source: str | None = Query(None),
    table: str = Query("live"),
) -> RawResponse:
    _check_range(start, end)
    df = _load_df(table, start, end, source)
    df = metrics.add_date_column(df) if not df.empty else df
    rows = [{k: metrics._clean(v) for k, v in rec.items()}
            for rec in df.to_dict(orient="records")] if not df.empty else []
    return RawResponse(columns=list(df.columns), rows=rows, count=len(rows))


@router.get("/raw.csv")
def raw_csv(
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    source: str | None = Query(None),
    table: str = Query("live"),
) -> Response:
    _check_range(start, end)
    df = _load_df(table, start, end, source)
    buf = io.StringIO()
    df.to_csv(buf, index=False, quoting=csv.QUOTE_MINIMAL)
    filename = f"catalog_{table}_{start.isoformat()}_{end.isoformat()}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/fraud/summary", response_model=FraudSummaryResponse)
def fraud_summary(
    source: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    threshold: int = Query(3, ge=1),
    table: str = Query("live"),
) -> FraudSummaryResponse:
    _check_range(start, end)
    sql, params = queries.fraud_summary_query(
        _table_name(table), source, threshold, start, end)
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


@router.get("/fraud/eventual", response_model=FraudEventualResponse)
def fraud_eventual(
    source: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    min_failed: int = Query(2, ge=1),
    table: str = Query("live"),
) -> FraudEventualResponse:
    _check_range(start, end)
    sql, params = queries.fraud_eventual_query(
        _table_name(table), source, min_failed, start, end)
    df = db.fetch_df(sql, params)
    rows = [{k: metrics._clean(v) for k, v in rec.items()}
            for rec in df.to_dict(orient="records")] if not df.empty else []
    return FraudEventualResponse(source=source, rows=rows)


@router.get("/fraud/never-succeeded", response_model=FraudNeverSucceededResponse)
def fraud_never_succeeded(
    source: str = Query(...),
    start: dt.date = Query(...),
    end: dt.date = Query(...),
    min_attempts: int = Query(3, ge=1),
    table: str = Query("live"),
) -> FraudNeverSucceededResponse:
    _check_range(start, end)
    sql, params = queries.fraud_never_succeeded_query(
        _table_name(table), source, min_attempts, start, end)
    df = db.fetch_df(sql, params)
    rows = [{k: metrics._clean(v) for k, v in rec.items()}
            for rec in df.to_dict(orient="records")] if not df.empty else []
    return FraudNeverSucceededResponse(source=source, rows=rows)
