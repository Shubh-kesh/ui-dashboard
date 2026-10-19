import type { DailyVolumePoint } from '../api/types';
import Plot from './Plot';

interface Props {
  data: DailyVolumePoint[];
}

export default function VolumeChart({ data }: Props) {
  const trace = {
    type: 'bar',
    x: data.map((d) => d.date ?? ''),
    y: data.map((d) => d.count),
    marker: { color: '#d56116' },
    name: 'Transactions',
  };
  return (
    <Plot
      testId="volume-chart"
      data={[trace] as never}
      layout={{ title: 'Transaction Volume by Date', xaxis: { title: 'Date' }, yaxis: { title: 'Transactions' }, margin: { t: 48, r: 16, b: 48, l: 56 }, height: 340 }}
    />
  );
}
