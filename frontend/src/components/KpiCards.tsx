import type { KPIs } from '../api/types';
import { fmtNumber, fmtPct, fmtSeconds } from '../lib/format';

interface Props {
  kpis: KPIs;
}

export default function KpiCards({ kpis }: Props) {
  const cards = [
    { key: 'total', label: 'Total Transactions', value: fmtNumber(kpis.total_txns) },
    { key: 'callback', label: 'Callback Success Rate', value: fmtPct(kpis.callback_success_rate) },
    { key: 'latency', label: 'Avg Callback Latency', value: fmtSeconds(kpis.avg_callback_latency) },
  ];
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {cards.map((c) => (
        <div
          key={c.key}
          data-testid={`kpi-${c.key}`}
          className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
        >
          <p className="text-sm font-medium text-slate-500">{c.label}</p>
          <p className="mt-1 text-2xl font-semibold text-slate-900">{c.value}</p>
        </div>
      ))}
    </div>
  );
}
