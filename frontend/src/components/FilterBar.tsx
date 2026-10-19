interface Props {
  start: string;
  end: string;
  source: string;
  sources: string[];
  onStart: (v: string) => void;
  onEnd: (v: string) => void;
  onSource: (v: string) => void;
  onRefresh: () => void;
}

export default function FilterBar({
  start,
  end,
  source,
  sources,
  onStart,
  onEnd,
  onSource,
  onRefresh,
}: Props) {
  return (
    <div className="flex flex-wrap items-end gap-4 rounded-xl border border-slate-200 bg-white p-4">
      <label className="flex flex-col text-sm font-medium text-slate-600">
        Start date
        <input
          type="date"
          value={start}
          onChange={(e) => onStart(e.target.value)}
          data-testid="filter-start"
          className="mt-1 rounded-md border border-slate-300 px-3 py-1.5 text-slate-800"
        />
      </label>
      <label className="flex flex-col text-sm font-medium text-slate-600">
        End date
        <input
          type="date"
          value={end}
          onChange={(e) => onEnd(e.target.value)}
          data-testid="filter-end"
          className="mt-1 rounded-md border border-slate-300 px-3 py-1.5 text-slate-800"
        />
      </label>
      <label className="flex flex-col text-sm font-medium text-slate-600">
        Source
        <select
          value={source}
          onChange={(e) => onSource(e.target.value)}
          data-testid="filter-source"
          className="mt-1 rounded-md border border-slate-300 px-3 py-1.5 text-slate-800"
        >
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
  );
}
