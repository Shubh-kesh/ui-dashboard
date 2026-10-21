"""Pydantic response models (the backend/frontend contract)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


class HealthResponse(BaseModel):
    status: str
    database_reachable: bool
    table: str
    archive_table: str


class SourcesResponse(BaseModel):
    sources: list[str]


class RangeResponse(BaseModel):
    table: str
    min: str | None = None
    max: str | None = None
    rows: int


class KPIs(_Base):
    total_txns: int


class TimeSeriesPoint(_Base):
    bucket: str
    count: int
    delta_pct: float | None = None


class StageStatusPoint(_Base):
    date: str | None
    status: str
    count: int


class LatencyStat(_Base):
    stage: str
    mean: float
    p50: float
    p95: float
    min: float
    q1: float
    q3: float
    max: float
    n: int


class LatencyBlock(BaseModel):
    stats: list[LatencyStat]


class DashboardResponse(_Base):
    rows: int
    start: str
    end: str
    source: str | None = None
    table: str
    granularity: str
    start_time: str | None = None
    end_time: str | None = None
    kpis: KPIs
    time_series: list[TimeSeriesPoint]
    stage_breakdown: dict[str, list[StageStatusPoint]]
    latency: LatencyBlock
    exceptions: list[dict]


class RawResponse(_Base):
    columns: list[str]
    rows: list[dict]
    count: int


class FraudSummaryResponse(_Base):
    source: str
    total_users: int
    quick_success_users: int
    quick_success_pct: float


class FraudEventualCase(_Base):
    BASE_TXN_ID: str
    TOTAL_ATTEMPTS: int
    SUCCESS_ATTEMPT_NO: int
    FAILED_ATTEMPTS_BEFORE_SUCCESS: int
    SUCCESS_TXN_ID: str


class FraudEventualResponse(_Base):
    source: str
    rows: list[FraudEventualCase]


class FraudNeverSucceededCase(_Base):
    BASE_TXN_ID: str
    TOTAL_ATTEMPTS: int


class FraudNeverSucceededResponse(_Base):
    source: str
    rows: list[FraudNeverSucceededCase]
