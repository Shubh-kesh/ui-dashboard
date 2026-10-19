import type { Granularity, TableKey } from '../api/types';

interface Props {
  start: string;
  end: string;
  source: string;
  sources: string[];
  table: TableKey;
  granularity: Granularity;
  startTime: string;
  endTime: string;
  notice?: string;
  onStart: (v: string) => void;
  onEnd: (v: string) => void;
  onSource: (v: string) => void;
  onTable: (v: TableKey) => void;
  onGranularity: (v: Granularity) => void;
  onStartTime: (v: string) => void;
  onEndTime: (v: string) => void;
  onRefresh: () => void;
}

const GRANULARITIES: Granularity[] = ['auto', '15m', '30m', '1h', '6h', '1d'];
const GRANULARITY_LABELS: Record<Granularity, string> = {
  auto: 'Auto',
  '15m': '15 minutes',
  '30m': '30 minutes',
  '1h': '1 hour',
  '6h': '6 hours',
  '1d': '1 day',
};

const field = 'mt-1 rounded-md border border-slate-300 px-3 py-1.5 text-slate-800';
const label = 'flex flex-col text-sm font-medium text-slate-600';

export default function FilterBar({
  start,
  end,
  source,
  sources,
  table,
  granularity,
  startTime,
  endTime,
  notice,
  onStart,
  onEnd,
  onSource,
  onTable,
  onGranularity,
  onStartTime,
  onEndTime,
  onRefresh,
}: Props) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-end gap-4">
        <label className={label}>
          Dataset
          <select
            value={table}
            onChange={(e) => onTable(e.target.value as TableKey)}
            data-testid="filter-table"
            className={field}
          >
            <option value="live">Live (recent)</option>
            <option value="archive">Archive (older)</option>
          </select>
        </label>

        <label className={label}>
          Start date
          <input type="date" value={start} onChange={(e) => onStart(e.target.value)}
            data-testid="filter-start" className={field} />
        </label>
        <label className={label}>
          End date
          <input type="date" value={end} onChange={(e) => onEnd(e.target.value)}
            data-testid="filter-end" className={field} />
        </label>
        <label className={label}>
          Time from
          <input type="time" value={startTime} onChange={(e) => onStartTime(e.target.value)}
            data-testid="filter-start-time" className={field} />
        </label>
        <label className={label}>
          Time to
          <input type="time" value={endTime} onChange={(e) => onEndTime(e.target.value)}
            data-testid="filter-end-time" className={field} />
        </label>
        <label className={label}>
          Interval
          <select
            value={granularity}
            onChange={(e) => onGranularity(e.target.value as Granularity)}
            data-testid="filter-granularity"
            className={field}
          >
            {GRANULARITIES.map((g) => (
              <option key={g} value={g}>
                {GRANULARITY_LABELS[g]}
              </option>
            ))}
          </select>
        </label>
        <label className={label}>
          Source
          <select value={source} onChange={(e) => onSource(e.target.value)}
            data-testid="filter-source" className={field}>
            <option value="">All sources</option>
            {sources.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <button
          onClick={onRefresh}
          className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-dark"
        >
          Refresh
        </button>
      </div>
      {notice && (
        <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">{notice}</p>
      )}
    </div>
  );
}
