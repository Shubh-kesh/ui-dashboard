import type { LatencyRawPoint, LatencyStat } from '../api/types';
import Plot from './Plot';
import { fmtNumber, fmtSeconds } from '../lib/format';

interface Props {
  stats: LatencyStat[];
  raw: LatencyRawPoint[];
}

const STAGES = ['Blink', 'Head Nod', 'Authenticity', 'Image Seg', 'Verify Token', 'Callback'];

export default function LatencyPanel({ stats, raw }: Props) {
  if (stats.length === 0) {
    return (
      <section>
        <h2 className="mb-3 text-lg font-semibold text-slate-800">Latency</h2>
        <p className="text-sm text-slate-500">No latency data available for the selected range.</p>
      </section>
    );
  }

  const boxTraces = STAGES.filter((s) => raw.some((r) => r.stage === s)).map((stage) => ({
    type: 'box',
    name: stage,
    y: raw.filter((r) => r.stage === stage).map((r) => r.duration),
    boxpoints: false,
  }));

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold text-slate-800">Latency</h2>
      <div className="mb-4 overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm" data-testid="latency-table">
          <thead className="bg-slate-100 text-left text-slate-600">
            <tr>
              <th className="px-4 py-2 font-medium">Stage</th>
              <th className="px-4 py-2 font-medium">Mean (s)</th>
              <th className="px-4 py-2 font-medium">P50 (s)</th>
              <th className="px-4 py-2 font-medium">P95 (s)</th>
              <th className="px-4 py-2 font-medium">N</th>
            </tr>
          </thead>
          <tbody>
            {stats.map((s) => (
              <tr key={s.stage} className="border-t border-slate-100">
                <td className="px-4 py-2 font-medium text-slate-700">{s.stage}</td>
                <td className="px-4 py-2">{fmtSeconds(s.mean)}</td>
                <td className="px-4 py-2">{fmtSeconds(s.p50)}</td>
                <td className="px-4 py-2">{fmtSeconds(s.p95)}</td>
                <td className="px-4 py-2">{fmtNumber(s.n)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {boxTraces.length > 0 && (
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
      )}
    </section>
  );
}
