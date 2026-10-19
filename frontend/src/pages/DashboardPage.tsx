import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { DashboardQuery } from '../api/types';
import { daysAgoISO, todayISO } from '../lib/format';
import FilterBar from '../components/FilterBar';
import KpiCards from '../components/KpiCards';
import VolumeChart from '../components/VolumeChart';
import FunnelChart from '../components/FunnelChart';
import StageTabs from '../components/StageTabs';
import LatencyPanel from '../components/LatencyPanel';
import ExceptionsTable from '../components/ExceptionsTable';
import RawTable from '../components/RawTable';
import FraudSection from '../components/FraudSection';

export default function DashboardPage() {
  const [start, setStart] = useState(daysAgoISO(6));
  const [end, setEnd] = useState(todayISO());
  const [source, setSource] = useState('');

  const query: DashboardQuery = useMemo(
    () => ({ start, end, source: source || undefined }),
    [start, end, source],
  );

  const sources = useQuery({ queryKey: ['sources'], queryFn: api.getSources });
  const dashboard = useQuery({
    queryKey: ['dashboard', query],
    queryFn: () => api.getDashboard(query),
  });
  const raw = useQuery({
    queryKey: ['raw', query],
    queryFn: () => api.getRaw(query),
  });

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
        onStart={setStart}
        onEnd={setEnd}
        onSource={setSource}
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

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <VolumeChart data={dashboard.data.daily_volume} />
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <FunnelChart data={dashboard.data.funnel} />
            </div>
          </div>

          <StageTabs breakdown={dashboard.data.stage_breakdown} />
          <LatencyPanel stats={dashboard.data.latency.stats} raw={dashboard.data.latency.raw} />
          <ExceptionsTable rows={dashboard.data.exceptions} />
        </>
      )}

      <RawTable
        data={raw.data}
        isLoading={raw.isLoading}
        csvUrl={api.rawCsvUrl(query)}
        query={query}
      />

      <FraudSection sources={sources.data ?? []} />
    </div>
  );
}
