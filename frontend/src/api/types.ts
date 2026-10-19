// Response types mirroring the FastAPI backend contract (backend/app/models.py).

export type TableKey = 'live' | 'archive';

export type Granularity = 'auto' | '15m' | '30m' | '1h' | '6h' | '1d';

export interface KPIs {
  total_txns: number;
}

export interface TimeSeriesPoint {
  bucket: string;
  count: number;
  delta_pct: number | null;
}

export interface StageStatusPoint {
  date: string | null;
  status: string;
  count: number;
}

export interface LatencyStat {
  stage: string;
  mean: number;
  p50: number;
  p95: number;
  min: number;
  q1: number;
  q3: number;
  max: number;
  n: number;
}

export interface DashboardResponse {
  rows: number;
  start: string;
  end: string;
  source: string | null;
  table: string;
  granularity: Granularity;
  start_time: string | null;
  end_time: string | null;
  kpis: KPIs;
  time_series: TimeSeriesPoint[];
  stage_breakdown: Record<string, StageStatusPoint[]>;
  latency: { stats: LatencyStat[] };
  exceptions: Record<string, unknown>[];
}

export interface RawResponse {
  columns: string[];
  rows: Record<string, unknown>[];
  count: number;
}

export interface RangeResponse {
  table: string;
  min: string | null;
  max: string | null;
  rows: number;
}

export interface FraudSummaryResponse {
  source: string;
  total_users: number;
  quick_success_users: number;
  quick_success_pct: number;
}

export type FraudBurstRow = Record<string, string | number | null>;
export interface FraudBurstResponse {
  source: string;
  total_users: number;
  burst_cases: number;
  burst_pct: number;
  rows: FraudBurstRow[];
}

export type FraudEventualRow = Record<string, string | number | null>;
export interface FraudEventualResponse {
  source: string;
  rows: FraudEventualRow[];
}

export interface DashboardQuery {
  start: string;
  end: string;
  source?: string;
  table?: TableKey;
  granularity?: Granularity;
  start_time?: string;
  end_time?: string;
}
