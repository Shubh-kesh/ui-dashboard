import type {
  DashboardQuery,
  DashboardResponse,
  FraudEventualResponse,
  FraudNeverSucceededResponse,
  FraudSummaryResponse,
  RangeResponse,
  RawResponse,
  TableKey,
} from './types';

const API_BASE = import.meta.env?.VITE_API_BASE ?? '';

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') search.set(k, String(v));
  });
  const s = search.toString();
  return s ? `?${s}` : '';
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

const windowParams = (q: DashboardQuery) => ({
  start: q.start,
  end: q.end,
  source: q.source,
  table: q.table,
});

export const api = {
  getDashboard: (q: DashboardQuery) =>
    getJson<DashboardResponse>(
      `/api/dashboard${qs({
        ...windowParams(q),
        granularity: q.granularity,
        start_time: q.start_time,
        end_time: q.end_time,
      })}`,
    ),

  getSources: (table: TableKey) =>
    getJson<{ sources: string[] }>(`/api/sources${qs({ table })}`).then((r) => r.sources),

  getRange: (table: TableKey) => getJson<RangeResponse>(`/api/range${qs({ table })}`),

  getRaw: (q: DashboardQuery) => getJson<RawResponse>(`/api/raw${qs(windowParams(q))}`),

  rawCsvUrl: (q: DashboardQuery) => `${API_BASE}/api/raw.csv${qs(windowParams(q))}`,

  getFraudSummary: (source: string, threshold: number, start: string, end: string, table: TableKey) =>
    getJson<FraudSummaryResponse>(
      `/api/fraud/summary${qs({ source, threshold, start, end, table })}`,
    ),

  getFraudEventual: (
    source: string,
    minFailed: number,
    start: string,
    end: string,
    table: TableKey,
  ) =>
    getJson<FraudEventualResponse>(
      `/api/fraud/eventual${qs({ source, min_failed: minFailed, start, end, table })}`,
    ),

  getFraudNeverSucceeded: (
    source: string,
    minAttempts: number,
    start: string,
    end: string,
    table: TableKey,
  ) =>
    getJson<FraudNeverSucceededResponse>(
      `/api/fraud/never-succeeded${qs({ source, min_attempts: minAttempts, start, end, table })}`,
    ),
};
