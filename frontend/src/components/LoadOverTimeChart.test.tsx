import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import LoadOverTimeChart from './LoadOverTimeChart';

vi.mock('./Plot', () => ({
  default: ({ testId, data }: { testId?: string; data: unknown[] }) => (
    <div data-testid={testId} data-traces={data.length} />
  ),
}));

describe('LoadOverTimeChart', () => {
  it('renders a volume bar plus a variation line trace', () => {
    render(
      <LoadOverTimeChart
        granularity="1h"
        data={[
          { bucket: '2026-10-01T09:00:00', count: 10, delta_pct: null },
          { bucket: '2026-10-01T10:00:00', count: 15, delta_pct: 50 },
        ]}
      />,
    );
    const chart = screen.getByTestId('load-over-time');
    expect(chart).toHaveAttribute('data-traces', '2');
  });
});
