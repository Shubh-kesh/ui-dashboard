import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import LatencyPanel from './LatencyPanel';

vi.mock('./Plot', () => ({
  default: ({ testId }: { testId?: string }) => <div data-testid={testId} />,
}));

const stats = [
  { stage: 'Blink', mean: 0.5, p50: 0.5, p95: 0.9, min: 0.2, q1: 0.4, q3: 0.6, max: 1.0, n: 100 },
];

describe('LatencyPanel', () => {
  it('renders the summary table and the box plot', () => {
    render(<LatencyPanel stats={stats} />);
    expect(screen.getByTestId('latency-table')).toBeInTheDocument();
    expect(screen.getByText('Blink')).toBeInTheDocument();
    expect(screen.getByText('0.200s')).toBeInTheDocument(); // min
    expect(screen.getByTestId('latency-box')).toBeInTheDocument();
  });

  it('omits the Q1, Q3 and P95 columns', () => {
    render(<LatencyPanel stats={stats} />);
    expect(screen.queryByText('Q1 (s)')).not.toBeInTheDocument();
    expect(screen.queryByText('Q3 (s)')).not.toBeInTheDocument();
    expect(screen.queryByText('P95 (s)')).not.toBeInTheDocument();
  });

  it('shows an empty state without stats', () => {
    render(<LatencyPanel stats={[]} />);
    expect(screen.getByText(/no latency data/i)).toBeInTheDocument();
  });
});
