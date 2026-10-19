import { useState } from 'react';
import type { StageStatusPoint } from '../api/types';
import Plot from './Plot';

const STAGE_ORDER: string[] = [
  'Blink',
  'Head Nod',
  'Authenticity',
  'Image Seg',
  'Verify Token',
  'Callback',
  'Fraud Attempt',
  'User Review',
];

const STATUS_COLORS: Record<string, string> = {
  PASSED: '#16a34a',
  FAILED: '#dc2626',
  GENUINE: '#16a34a',
  FRAUD: '#dc2626',
  ACCEPT: '#16a34a',
  REJECTED: '#dc2626',
  'REVIEW PENDING': '#f59e0b',
  PENDING: '#f59e0b',
  'NOT REQUIRED': '#94a3b8',
  NULL: '#94a3b8',
};

// Deterministic palette so arbitrary DB status codes (FB01, FB02, ...) each get
// a distinct, stable colour and appear in the legend.
const FALLBACK_PALETTE = [
  '#0ea5e9',
  '#8b5cf6',
  '#f97316',
  '#14b8a6',
  '#e11d48',
  '#a855f7',
  '#eab308',
  '#2563eb',
  '#db2777',
  '#65a30d',
];

function orderStatuses(rows: StageStatusPoint[]): string[] {
  const present = [...new Set(rows.map((r) => r.status))];
  const known = present.filter((s) => s in STATUS_COLORS).sort();
  const unknown = present.filter((s) => !(s in STATUS_COLORS)).sort();
  return [...known, ...unknown];
}

function statusColor(status: string, statuses: string[]): string {
  if (status in STATUS_COLORS) return STATUS_COLORS[status];
  const unknown = statuses.filter((s) => !(s in STATUS_COLORS));
  const idx = unknown.indexOf(status);
  return FALLBACK_PALETTE[idx % FALLBACK_PALETTE.length];
}

function StageStatusChart({ stage, rows }: { stage: string; rows: StageStatusPoint[] }) {
  const dates = [...new Set(rows.map((r) => r.date ?? '—'))].sort();
  const statuses = orderStatuses(rows);
  const lookup = new Map(rows.map((r) => [`${r.date ?? '—'}|${r.status}`, r.count]));
  const traces = statuses.map((status) => ({
    type: 'bar',
    name: status,
    x: dates,
    y: dates.map((d) => lookup.get(`${d}|${status}`) ?? 0),
    marker: { color: statusColor(status, statuses) },
  }));
  return (
    <Plot
      testId={`stage-chart-${stage}`}
      data={traces as never}
      layout={{
        barmode: 'stack',
        title: `${stage} Status by Date`,
        xaxis: { title: 'Date' },
        yaxis: { title: 'Count' },
        margin: { t: 48, r: 16, b: 48, l: 56 },
        height: 320,
      }}
    />
  );
}

interface Props {
  breakdown: Record<string, StageStatusPoint[]>;
}

export default function StageTabs({ breakdown }: Props) {
  const [active, setActive] = useState(STAGE_ORDER[0]);
  const rows = breakdown[active] ?? [];
  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold text-slate-800">Status by stage</h2>
      <div className="mb-3 flex flex-wrap gap-2" role="tablist">
        {STAGE_ORDER.map((stage) => (
          <button
            key={stage}
            role="tab"
            aria-selected={stage === active}
            onClick={() => setActive(stage)}
            className={`rounded-full px-3 py-1 text-sm font-medium transition ${
              stage === active
                ? 'bg-brand text-white'
                : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-100'
            }`}
          >
            {stage}
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-slate-500">No data for this stage in the selected range.</p>
      ) : (
        <StageStatusChart stage={active} rows={rows} />
      )}
    </section>
  );
}
