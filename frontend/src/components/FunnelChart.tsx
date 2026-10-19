import type { FunnelPoint } from '../api/types';
import Plot from './Plot';

interface Props {
  data: FunnelPoint[];
}

export default function FunnelChart({ data }: Props) {
  const trace = {
    type: 'funnel',
    y: data.map((d) => d.stage),
    x: data.map((d) => d.count),
    marker: { color: '#f0792e' },
  };
  return (
    <Plot
      testId="funnel-chart"
      data={[trace] as never}
      layout={{ title: 'Pipeline Completion Funnel', margin: { t: 48, r: 16, b: 48, l: 120 }, height: 340 }}
    />
  );
}
