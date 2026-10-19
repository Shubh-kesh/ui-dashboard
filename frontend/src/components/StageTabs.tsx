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
];

const STATUS_COLORS: Record<string, string> = {
  PASSED: '#16a34a',
  FAILED: '#dc2626',
  NULL: '#94a3b8',
  PENDING: '#f59e0b',
};

function StageStatusChart({ stage, rows }: { stage: string; rows: StageStatusPoint[] }) {
  const dates = [...new Set(rows.map((r) => r.date ?? '—'))].sort();
  const statuses = [...new Set(rows.map((r) => r.status))];
  const lookup = new Map(rows.map((r) => [`${r.date ?? '—'}|${r.status}`, r.count]));
  const traces = statuses.map((status) => ({
    type: 'bar',
    name: status,
    x: dates,
    y: dates.map((d) => lookup.get(`${d}|${status}`) ?? 0),
    marker: { color: STATUS_COLORS[status] ?? '#0ea5e9' },
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
      <h2 className="mb-3 text-lg font-semibold text-slate-800">Status by Stage</h2>
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
