import type { KPIs } from '../api/types';
import { fmtNumber } from '../lib/format';

interface Props {
  kpis: KPIs;
}

export default function KpiCards({ kpis }: Props) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <div
        data-testid="kpi-total"
        className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
      >
        <p className="text-sm font-medium text-slate-500">Total Transactions</p>
        <p className="mt-1 text-2xl font-semibold text-slate-900">{fmtNumber(kpis.total_txns)}</p>
      </div>
    </div>
  );
}
