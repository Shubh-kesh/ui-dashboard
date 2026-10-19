import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api } from '../api/client';
import type { FraudBurstResponse, FraudEventualResponse, FraudSummaryResponse } from '../api/types';
import { fmtNumber, fmtPct } from '../lib/format';

interface Props {
  sources: string[];
}

export default function FraudSection({ sources }: Props) {
  const [source, setSource] = useState('');
  const [threshold, setThreshold] = useState(10);
  const [gapSeconds, setGapSeconds] = useState(2);
  const [minPairs, setMinPairs] = useState(3);

  const summary = useMutation<FraudSummaryResponse>({
    mutationFn: () => api.getFraudSummary(source, threshold),
  });
  const eventual = useMutation<FraudEventualResponse>({
    mutationFn: () => api.getFraudEventual(source, threshold),
  });
  const burst = useMutation<FraudBurstResponse>({
    mutationFn: () => api.getFraudBurst(source, gapSeconds, minPairs),
  });

  const disabled = !source || summary.isPending || eventual.isPending || burst.isPending;
  const run = () => {
    if (!source) return;
    summary.mutate();
    eventual.mutate();
    burst.mutate();
  };

  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold text-slate-800">Fraud analysis</h2>
      <div className="flex flex-wrap items-end gap-4 rounded-xl border border-slate-200 bg-white p-4">
        <label className="flex flex-col text-sm font-medium text-slate-600">
          Source
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            data-testid="fraud-source"
            className="mt-1 rounded-md border border-slate-300 px-3 py-1.5"
          >
            <option value="">Select source…</option>
            {sources.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col text-sm font-medium text-slate-600">
          Threshold (attempts)
          <input
            type="number"
            min={1}
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            data-testid="fraud-threshold"
            className="mt-1 w-28 rounded-md border border-slate-300 px-3 py-1.5"
          />
        </label>
        <label className="flex flex-col text-sm font-medium text-slate-600">
          Burst gap (s)
          <input
            type="number"
            min={1}
            value={gapSeconds}
            onChange={(e) => setGapSeconds(Number(e.target.value))}
            className="mt-1 w-24 rounded-md border border-slate-300 px-3 py-1.5"
          />
        </label>
        <label className="flex flex-col text-sm font-medium text-slate-600">
          Min pairs
          <input
            type="number"
            min={1}
            value={minPairs}
            onChange={(e) => setMinPairs(Number(e.target.value))}
            className="mt-1 w-24 rounded-md border border-slate-300 px-3 py-1.5"
          />
        </label>
        <button
          onClick={run}
          disabled={disabled}
          className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-dark disabled:opacity-50"
        >
          {summary.isPending || eventual.isPending || burst.isPending ? 'Running…' : 'Run analysis'}
        </button>
      </div>

      {(summary.error || eventual.error || burst.error) && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {(summary.error as Error)?.message ??
            (eventual.error as Error)?.message ??
            (burst.error as Error)?.message}
        </p>
      )}

      {summary.data && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Stat label="Total users" value={fmtNumber(summary.data.total_users)} />
          <Stat label={`Users with ≤ ${threshold} attempts`} value={fmtNumber(summary.data.quick_success_users)} />
          <Stat label="Quick-success rate" value={fmtPct(summary.data.quick_success_pct)} />
        </div>
      )}

      {eventual.data && (
        <TableCard
          title={`Eventual successes (≥ ${threshold} failed attempts)`}
          columns={['BASE_TXN_ID', 'TOTAL_ATTEMPTS', 'SUCCESS_ATTEMPT_NO', 'FAILED_ATTEMPTS_BEFORE_SUCCESS', 'SUCCESS_TXN_ID']}
          rows={eventual.data.rows as Record<string, unknown>[]}
        />
      )}

      {burst.data && (
        <TableCard
          title={`Burst cases (gap ≤ ${gapSeconds}s, ≥ ${minPairs} pairs)`}
          columns={['BASE_TXN_ID', 'TOTAL_ATTEMPTS', 'MIN_GAP_SECONDS', 'BURST_PAIRS']}
          rows={burst.data.rows as Record<string, unknown>[]}
        />
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-slate-900">{value}</p>
    </div>
  );
}

function TableCard({
  title,
  columns,
  rows,
}: {
  title: string;
  columns: string[];
  rows: Record<string, unknown>[];
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h3 className="mb-2 font-medium text-slate-700">
        {title} <span className="text-sm font-normal text-slate-500">({rows.length})</span>
      </h3>
      {rows.length === 0 ? (
        <p className="text-sm text-slate-500">No matching cases.</p>
      ) : (
        <div className="max-h-72 overflow-auto">
          <table className="min-w-full text-sm">
            <thead className="sticky top-0 bg-slate-100 text-left text-slate-600">
              <tr>
                {columns.map((c) => (
                  <th key={c} className="px-3 py-2 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-slate-100">
                  {columns.map((c) => (
                    <td key={c} className="px-3 py-2 text-slate-700">
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
  );
}
