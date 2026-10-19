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
  it('builds the dashboard query string and unwraps JSON', async () => {
    const fetchMock = mockFetch({ rows: 1, kpis: {} });
    vi.stubGlobal('fetch', fetchMock);

    const res = await api.getDashboard({ start: '2026-10-01', end: '2026-10-02', source: 'A' });

    expect(res).toEqual({ rows: 1, kpis: {} });
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain('/api/dashboard?');
    expect(url).toContain('start=2026-10-01');
    expect(url).toContain('end=2026-10-02');
    expect(url).toContain('source=A');
  });

  it('omits the optional source when empty', async () => {
    const fetchMock = mockFetch({ rows: 0 });
    vi.stubGlobal('fetch', fetchMock);

    await api.getDashboard({ start: '2026-10-01', end: '2026-10-02' });

    expect(fetchMock.mock.calls[0][0] as string).not.toContain('source=');
  });

  it('unwraps the sources array', async () => {
    vi.stubGlobal('fetch', mockFetch({ sources: ['A', 'B'] }));
    await expect(api.getSources()).resolves.toEqual(['A', 'B']);
  });

  it('throws ApiError with the server detail on failure', async () => {
    vi.stubGlobal('fetch', mockFetch({ detail: 'start date must be on or before end date' }, false, 400));

    await expect(api.getDashboard({ start: '2026-10-02', end: '2026-10-01' })).rejects.toThrow(ApiError);
    await expect(api.getDashboard({ start: '2026-10-02', end: '2026-10-01' })).rejects.toThrow(
      'start date must be on or before end date',
    );
  });
});
