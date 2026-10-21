import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api } from '../api/client';
import type {
  FraudEventualResponse,
  FraudNeverSucceededResponse,
  FraudSummaryResponse,
  TableKey,
} from '../api/types';
import { fmtNumber, fmtPct } from '../lib/format';

interface Props {
  source: string;
  start: string;
  end: string;
  table: TableKey;
}

export default function FraudSection({ source, start, end, table }: Props) {
  const [quick, setQuick] = useState(3);
  const [minPriorFailed, setMinPriorFailed] = useState(2);
  const [minAttempts, setMinAttempts] = useState(3);
  const [ranKey, setRanKey] = useState<string | null>(null);

  const summary = useMutation<FraudSummaryResponse>({
    mutationFn: () => api.getFraudSummary(source, quick, start, end, table),
  });
  const eventual = useMutation<FraudEventualResponse>({
    mutationFn: () => api.getFraudEventual(source, minPriorFailed, start, end, table),
  });
  const never = useMutation<FraudNeverSucceededResponse>({
    mutationFn: () => api.getFraudNeverSucceeded(source, minAttempts, start, end, table),
  });

  const running = summary.isPending || eventual.isPending || never.isPending;
  const currentKey = `${source}|${start}|${end}|${table}|${quick}|${minPriorFailed}|${minAttempts}`;
  const showResults = ranKey === currentKey;
  const disabled = !source || running;

  const run = () => {
    if (!source) return;
    setRanKey(currentKey);
    summary.mutate();
    eventual.mutate();
    never.mutate();
  };

  const totalUsers = summary.data?.total_users ?? 0;
  const eventualPct = totalUsers > 0 ? (100 * (eventual.data?.rows.length ?? 0)) / totalUsers : 0;
  const neverPct = totalUsers > 0 ? (100 * (never.data?.rows.length ?? 0)) / totalUsers : 0;

  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold text-slate-800">Fraud analysis</h2>
      <div className="flex flex-wrap items-end gap-4 rounded-xl border border-slate-200 bg-white p-4">
        <label className="flex flex-col text-sm font-medium text-slate-600">
          Quick success: fewer than N attempts
          <input
            type="number"
            min={1}
            value={quick}
            onChange={(e) => setQuick(Number(e.target.value))}
            data-testid="fraud-quick"
            className="mt-1 w-24 rounded-md border border-slate-300 px-3 py-1.5"
          />
        </label>
        <label className="flex flex-col text-sm font-medium text-slate-600">
          Suspected fraud (succeeded): min prior failed attempts
          <input
            type="number"
            min={1}
            value={minPriorFailed}
            onChange={(e) => setMinPriorFailed(Number(e.target.value))}
            data-testid="fraud-min-failed"
            className="mt-1 w-24 rounded-md border border-slate-300 px-3 py-1.5"
          />
        </label>
        <label className="flex flex-col text-sm font-medium text-slate-600">
          Suspected fraud (never succeeded): min attempts
          <input
            type="number"
            min={1}
            value={minAttempts}
            onChange={(e) => setMinAttempts(Number(e.target.value))}
            data-testid="fraud-min-attempts"
            className="mt-1 w-24 rounded-md border border-slate-300 px-3 py-1.5"
          />
        </label>
        <button
          onClick={run}
          disabled={disabled}
          className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-dark disabled:opacity-50"
        >
          {running ? 'Running…' : 'Run Attempt Analysis'}
        </button>
      </div>

      {!source && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Select a source in the filters above to run fraud analysis.
        </p>
      )}

      {showResults && (summary.error || eventual.error || never.error) && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {(summary.error as Error)?.message ??
            (eventual.error as Error)?.message ??
            (never.error as Error)?.message}
        </p>
      )}

      {showResults && summary.data && (
        <>
          <p className="text-sm text-slate-600">
            {fmtNumber(totalUsers)} unique users (BASE_TXN_ID) found for {source}
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Stat
              label={`Succeeded in < ${quick} attempts`}
              value={fmtPct(summary.data.quick_success_pct)}
            />
            <Stat
              label={`Suspected fraud, succeeded (≥ ${minPriorFailed} prior fails)`}
              value={fmtPct(eventualPct)}
            />
            <Stat
              label={`Suspected fraud, never succeeded (≥ ${minAttempts} attempts)`}
              value={fmtPct(neverPct)}
            />
          </div>
        </>
      )}

      {showResults && eventual.data && (
        <TableCard
          title="Suspected fraud — eventually succeeded"
          columns={[
            'BASE_TXN_ID',
            'TOTAL_ATTEMPTS',
            'SUCCESS_ATTEMPT_NO',
            'FAILED_ATTEMPTS_BEFORE_SUCCESS',
            'SUCCESS_TXN_ID',
          ]}
          rows={eventual.data.rows as Record<string, unknown>[]}
        />
      )}

      {showResults && never.data && (
        <TableCard
          title="Suspected fraud — never succeeded"
          columns={['BASE_TXN_ID', 'TOTAL_ATTEMPTS']}
          rows={never.data.rows as Record<string, unknown>[]}
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
