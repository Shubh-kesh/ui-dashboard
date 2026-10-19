"""Pydantic response models (the backend/frontend contract)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


class HealthResponse(BaseModel):
    status: str
    database_reachable: bool
    table: str


class SourcesResponse(BaseModel):
    sources: list[str]


class KPIs(_Base):
    total_txns: int
    callback_success_rate: float | None = None
    avg_callback_latency: float | None = None


class DailyVolumePoint(_Base):
    date: str | None
    count: int


class FunnelPoint(_Base):
    stage: str
    count: int


class StageStatusPoint(_Base):
    date: str | None
    status: str
    count: int


class LatencyStat(_Base):
    stage: str
    mean: float
    p50: float
    p95: float
    n: int


class LatencyRawPoint(_Base):
    stage: str
    duration: float


class LatencyBlock(BaseModel):
    stats: list[LatencyStat]
    raw: list[LatencyRawPoint]


class DashboardResponse(_Base):
    rows: int
    start: str
    end: str
    source: str | None = None
    kpis: KPIs
    daily_volume: list[DailyVolumePoint]
    funnel: list[FunnelPoint]
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


class FraudTotalUsersResponse(_Base):
    source: str
    total_users: int


class FraudEventualCase(_Base):
    BASE_TXN_ID: str
    TOTAL_ATTEMPTS: int
    SUCCESS_ATTEMPT_NO: int
    FAILED_ATTEMPTS_BEFORE_SUCCESS: int
    SUCCESS_TXN_ID: str


class FraudEventualResponse(_Base):
    source: str
    rows: list[FraudEventualCase]


class FraudBurstCase(_Base):
    BASE_TXN_ID: str
    TOTAL_ATTEMPTS: int
    MIN_GAP_SECONDS: int | None = None
    BURST_PAIRS: int


class FraudBurstResponse(_Base):
    source: str
    total_users: int
    burst_cases: int
    burst_pct: float
    rows: list[FraudBurstCase]
