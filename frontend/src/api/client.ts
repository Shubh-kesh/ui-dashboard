import type {
  DashboardQuery,
  DashboardResponse,
  FraudBurstResponse,
  FraudEventualResponse,
  FraudSummaryResponse,
  RawResponse,
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

export const api = {
  getDashboard: (q: DashboardQuery) =>
    getJson<DashboardResponse>(`/api/dashboard${qs({ ...q })}`),

  getSources: () => getJson<{ sources: string[] }>('/api/sources').then((r) => r.sources),

  getRaw: (q: DashboardQuery) => getJson<RawResponse>(`/api/raw${qs({ ...q })}`),

  rawCsvUrl: (q: DashboardQuery) => `${API_BASE}/api/raw.csv${qs({ ...q })}`,

  getFraudSummary: (source: string, threshold: number) =>
    getJson<FraudSummaryResponse>(`/api/fraud/summary${qs({ source, threshold })}`),

  getFraudEventual: (source: string, minFailed: number) =>
    getJson<FraudEventualResponse>(`/api/fraud/eventual${qs({ source, min_failed: minFailed })}`),

  getFraudBurst: (source: string, gapSeconds: number, minPairs: number) =>
    getJson<FraudBurstResponse>(
      `/api/fraud/burst${qs({ source, gap_seconds: gapSeconds, min_pairs: minPairs })}`,
    ),
};
