import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { DashboardQuery, Granularity, TableKey } from '../api/types';
import { daysAgoISO, todayISO } from '../lib/format';
import { LIVE_WINDOW_DAYS } from '../lib/config';
import FilterBar from '../components/FilterBar';
import KpiCards from '../components/KpiCards';
import LoadOverTimeChart from '../components/LoadOverTimeChart';
import StageTabs from '../components/StageTabs';
import LatencyPanel from '../components/LatencyPanel';
import ExceptionsTable from '../components/ExceptionsTable';
import RawTable from '../components/RawTable';
import FraudSection from '../components/FraudSection';

export default function DashboardPage() {
  const [start, setStart] = useState(daysAgoISO(LIVE_WINDOW_DAYS - 1));
  const [end, setEnd] = useState(todayISO());
  const [source, setSource] = useState('');
  const [table, setTable] = useState<TableKey>('live');
  const [tableTouched, setTableTouched] = useState(false);
  const [granularity, setGranularity] = useState<Granularity>('auto');
  const [startTime, setStartTime] = useState('00:00');
  const [endTime, setEndTime] = useState('23:59');

  // The live table only holds the most recent LIVE_WINDOW_DAYS days.
  const cutoff = daysAgoISO(LIVE_WINDOW_DAYS);

  const changeStart = (v: string) => {
    setStart(v);
    if (!tableTouched) setTable(v < cutoff ? 'archive' : 'live');
  };
  const changeTable = (v: TableKey) => {
    setTable(v);
    setTableTouched(true);
  };

  const query: DashboardQuery = useMemo(
    () => ({
      start,
      end,
      source: source || undefined,
      table,
      granularity,
      start_time: startTime,
      end_time: endTime,
    }),
    [start, end, source, table, granularity, startTime, endTime],
  );

  const rawQuery: DashboardQuery = useMemo(
    () => ({ start, end, source: source || undefined, table }),
    [start, end, source, table],
  );

  const sources = useQuery({
    queryKey: ['sources', table],
    queryFn: () => api.getSources(table),
  });
  const dashboard = useQuery({
    queryKey: ['dashboard', query],
    queryFn: () => api.getDashboard(query),
  });
  const raw = useQuery({
    queryKey: ['raw', rawQuery],
    queryFn: () => api.getRaw(rawQuery),
  });

  const spansBoundary = start < cutoff && end >= cutoff;
  let notice: string | undefined;
  if (table === 'archive') {
    notice = 'Showing archived data (older than the live window).';
  } else if (spansBoundary) {
    notice =
      'The selected range spans the live/archive boundary — only live rows are shown. ' +
      'Switch to Archive for older data.';
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">LivePhoto KYC Dashboard</h1>
          <p className="text-sm text-slate-500">Liveness, authenticity and callback metrics.</p>
        </div>
      </header>

      <FilterBar
        start={start}
        end={end}
        source={source}
        sources={sources.data ?? []}
        table={table}
        granularity={granularity}
        startTime={startTime}
        endTime={endTime}
        notice={notice}
        onStart={changeStart}
        onEnd={setEnd}
        onSource={setSource}
        onTable={changeTable}
        onGranularity={setGranularity}
        onStartTime={setStartTime}
        onEndTime={setEndTime}
        onRefresh={() => {
          void dashboard.refetch();
          void raw.refetch();
        }}
      />

      {dashboard.isError && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          Failed to load dashboard: {(dashboard.error as Error).message}
        </p>
      )}

      {dashboard.isLoading && <p className="text-sm text-slate-500">Loading dashboard…</p>}

      {dashboard.data && (
        <>
          <KpiCards kpis={dashboard.data.kpis} />

          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <LoadOverTimeChart
              data={dashboard.data.time_series}
              granularity={dashboard.data.granularity}
            />
          </div>

          <StageTabs breakdown={dashboard.data.stage_breakdown} />
          <LatencyPanel stats={dashboard.data.latency.stats} />
          <ExceptionsTable rows={dashboard.data.exceptions} />
        </>
      )}

      <RawTable
        data={raw.data}
        isLoading={raw.isLoading}
        csvUrl={api.rawCsvUrl(rawQuery)}
        query={rawQuery}
      />

      <FraudSection sources={sources.data ?? []} table={table} />
    </div>
  );
}
