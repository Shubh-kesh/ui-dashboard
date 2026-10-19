import type { LatencyStat } from '../api/types';
import Plot from './Plot';
import { fmtNumber, fmtSeconds } from '../lib/format';

interface Props {
  stats: LatencyStat[];
}

export default function LatencyPanel({ stats }: Props) {
  if (stats.length === 0) {
    return (
      <section>
        <h2 className="mb-3 text-lg font-semibold text-slate-800">Latency</h2>
        <p className="text-sm text-slate-500">No latency data available for the selected range.</p>
      </section>
    );
  }

  // Box plot built from server-side summary stats (no raw points shipped).
  const boxTraces = stats.map((s) => ({
    type: 'box',
    name: s.stage,
    q1: [s.q1],
    median: [s.p50],
    q3: [s.q3],
    lowerfence: [s.min],
    upperfence: [s.max],
    mean: [s.mean],
    boxpoints: false,
  }));

  const columns: { key: keyof LatencyStat; label: string }[] = [
    { key: 'min', label: 'Min (s)' },
    { key: 'q1', label: 'Q1 (s)' },
    { key: 'p50', label: 'Median (s)' },
    { key: 'q3', label: 'Q3 (s)' },
    { key: 'max', label: 'Max (s)' },
    { key: 'mean', label: 'Mean (s)' },
    { key: 'p95', label: 'P95 (s)' },
  ];

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold text-slate-800">Latency</h2>
      <div className="mb-4 overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm" data-testid="latency-table">
          <thead className="bg-slate-100 text-left text-slate-600">
            <tr>
              <th className="px-4 py-2 font-medium">Stage</th>
              {columns.map((c) => (
                <th key={c.key} className="px-4 py-2 font-medium">
                  {c.label}
                </th>
              ))}
              <th className="px-4 py-2 font-medium">N</th>
            </tr>
          </thead>
          <tbody>
            {stats.map((s) => (
              <tr key={s.stage} className="border-t border-slate-100">
                <td className="px-4 py-2 font-medium text-slate-700">{s.stage}</td>
                {columns.map((c) => (
                  <td key={c.key} className="px-4 py-2">
                    {fmtSeconds(s[c.key] as number)}
                  </td>
                ))}
                <td className="px-4 py-2">{fmtNumber(s.n)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Plot
        testId="latency-box"
        data={boxTraces as never}
        layout={{
          title: 'Response Latency by Stage',
          yaxis: { title: 'Duration (sec)' },
          showlegend: false,
          margin: { t: 48, r: 16, b: 48, l: 56 },
          height: 340,
        }}
      />
    </section>
  );
}
