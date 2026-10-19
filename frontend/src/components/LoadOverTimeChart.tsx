import type { TimeSeriesPoint } from '../api/types';
import Plot from './Plot';

interface Props {
  data: TimeSeriesPoint[];
  granularity: string;
}

export default function LoadOverTimeChart({ data, granularity }: Props) {
  const x = data.map((d) => d.bucket);
  const volume = {
    type: 'bar',
    name: 'Transactions',
    x,
    y: data.map((d) => d.count),
    marker: { color: '#d56116' },
    yaxis: 'y',
  };
  const variation = {
    type: 'scatter',
    mode: 'lines+markers',
    name: 'Variation %',
    x,
    y: data.map((d) => d.delta_pct),
    line: { color: '#0ea5e9', width: 2 },
    marker: { size: 5 },
    yaxis: 'y2',
    connectgaps: false,
  };
  return (
    <Plot
      testId="load-over-time"
      data={[volume, variation] as never}
      layout={{
        title: `Load over time (${granularity})`,
        xaxis: { title: 'Interval', type: 'date' },
        yaxis: { title: 'Transactions' },
        yaxis2: {
          title: 'Variation %',
          overlaying: 'y',
          side: 'right',
          showgrid: false,
        },
        legend: { orientation: 'h', y: -0.25 },
        margin: { t: 48, r: 56, b: 64, l: 56 },
        height: 360,
      }}
    />
  );
}
