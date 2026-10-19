import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from './client';

function mockFetch(body: unknown, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => body,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('api client', () => {
  it('builds the dashboard query string with window, table and granularity', async () => {
    const fetchMock = mockFetch({ rows: 1, kpis: {} });
    vi.stubGlobal('fetch', fetchMock);

    const res = await api.getDashboard({
      start: '2026-10-01',
      end: '2026-10-02',
      source: 'A',
      table: 'archive',
      granularity: '30m',
      start_time: '09:00',
      end_time: '18:00',
    });

    expect(res).toEqual({ rows: 1, kpis: {} });
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain('/api/dashboard?');
    expect(url).toContain('start=2026-10-01');
    expect(url).toContain('end=2026-10-02');
    expect(url).toContain('source=A');
    expect(url).toContain('table=archive');
    expect(url).toContain('granularity=30m');
    expect(url).toContain('start_time=09%3A00');
  });

  it('omits the optional source when empty', async () => {
    const fetchMock = mockFetch({ rows: 0 });
    vi.stubGlobal('fetch', fetchMock);

    await api.getDashboard({ start: '2026-10-01', end: '2026-10-02', table: 'live' });

    expect(fetchMock.mock.calls[0][0] as string).not.toContain('source=');
  });

  it('scopes sources to the selected table', async () => {
    const fetchMock = mockFetch({ sources: ['A', 'B'] });
    vi.stubGlobal('fetch', fetchMock);
    await expect(api.getSources('archive')).resolves.toEqual(['A', 'B']);
    expect(fetchMock.mock.calls[0][0] as string).toContain('table=archive');
  });

  it('fetches the available range for a table', async () => {
    const range = { table: 'LIVE_PHOTO_LOGS_ARCHIVE', min: '2026-09-20 00:00:00', max: '2026-10-12 23:59:59', rows: 8811 };
    const fetchMock = mockFetch(range);
    vi.stubGlobal('fetch', fetchMock);
    await expect(api.getRange('archive')).resolves.toEqual(range);
    expect(fetchMock.mock.calls[0][0] as string).toContain('/api/range?table=archive');
  });

  it('passes the table through to fraud calls', async () => {
    const fetchMock = mockFetch({ source: 'A', total_users: 0, quick_success_users: 0, quick_success_pct: 0 });
    vi.stubGlobal('fetch', fetchMock);
    await api.getFraudSummary('A', 5, 'archive');
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain('/api/fraud/summary?');
    expect(url).toContain('table=archive');
  });

  it('throws ApiError with the server detail on failure', async () => {
    vi.stubGlobal('fetch', mockFetch({ detail: 'start date must be on or before end date' }, false, 400));

    await expect(api.getDashboard({ start: '2026-10-02', end: '2026-10-01' })).rejects.toThrow(ApiError);
    await expect(api.getDashboard({ start: '2026-10-02', end: '2026-10-01' })).rejects.toThrow(
      'start date must be on or before end date',
    );
  });
});
