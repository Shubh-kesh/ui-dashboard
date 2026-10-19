// Response types mirroring the FastAPI backend contract (backend/app/models.py).

export interface KPIs {
  total_txns: number;
  callback_success_rate: number | null;
  avg_callback_latency: number | null;
}

export interface DailyVolumePoint {
  date: string | null;
  count: number;
}

export interface FunnelPoint {
  stage: string;
  count: number;
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
  n: number;
}

export interface LatencyRawPoint {
  stage: string;
  duration: number;
}

export interface DashboardResponse {
  rows: number;
  start: string;
  end: string;
  source: string | null;
  kpis: KPIs;
  daily_volume: DailyVolumePoint[];
  funnel: FunnelPoint[];
  stage_breakdown: Record<string, StageStatusPoint[]>;
  latency: { stats: LatencyStat[]; raw: LatencyRawPoint[] };
  exceptions: Record<string, unknown>[];
}

export interface RawResponse {
  columns: string[];
  rows: Record<string, unknown>[];
  count: number;
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
  limit?: number;
}
