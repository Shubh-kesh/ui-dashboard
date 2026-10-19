import { useState } from 'react';
import type { DashboardQuery, RawResponse } from '../api/types';

interface Props {
  data: RawResponse | undefined;
  isLoading: boolean;
  csvUrl: string;
  query: DashboardQuery;
}

const PAGE = 50;

export default function RawTable({ data, isLoading, csvUrl, query }: Props) {
  const [showAll, setShowAll] = useState(false);
  const rows = data?.rows ?? [];
  const visible = showAll ? rows : rows.slice(0, PAGE);

  return (
    <section className="rounded-xl border border-slate-200 bg-white">
      <details>
        <summary className="cursor-pointer px-4 py-3 font-semibold text-slate-800">
          Raw data {data ? `(${data.count} rows, ${query.start} → ${query.end})` : ''}
        </summary>
        <div className="border-t border-slate-100 p-4">
          <div className="mb-3 flex items-center gap-3">
            <a
              href={csvUrl}
              className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-dark"
            >
              Download CSV
            </a>
            {rows.length > PAGE && (
              <button
                onClick={() => setShowAll((v) => !v)}
                className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-slate-100"
              >
                {showAll ? 'Show first 50' : `Show all ${rows.length}`}
              </button>
            )}
          </div>
          {isLoading ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : (
            <div className="max-h-96 overflow-auto">
              <table className="min-w-full text-xs" data-testid="raw-table">
                <thead className="sticky top-0 bg-slate-100 text-left text-slate-600">
                  <tr>
                    {(data?.columns ?? []).map((c) => (
                      <th key={c} className="whitespace-nowrap px-2 py-1.5 font-medium">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visible.map((r, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      {(data?.columns ?? []).map((c) => (
                        <td key={c} className="whitespace-nowrap px-2 py-1 text-slate-700">
                          {r[c] === null || r[c] === undefined ? '' : String(r[c])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </details>
    </section>
  );
}
