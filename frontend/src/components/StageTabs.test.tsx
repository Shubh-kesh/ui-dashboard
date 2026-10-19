import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import StageTabs from './StageTabs';

// Plotly needs a real canvas/WebGL context; render a lightweight stub instead.
vi.mock('./Plot', () => ({
  default: ({ testId }: { testId?: string }) => <div data-testid={testId} />,
}));

const breakdown = {
  Blink: [{ date: '2026-10-01', status: 'PASSED', count: 8 }],
  Callback: [{ date: '2026-10-01', status: 'FAILED', count: 3 }],
};

describe('StageTabs', () => {
  it('defaults to the first stage and renders its chart', () => {
    render(<StageTabs breakdown={breakdown} />);
    expect(screen.getByTestId('stage-chart-Blink')).toBeInTheDocument();
  });

  it('switches charts when another tab is selected', async () => {
    render(<StageTabs breakdown={breakdown} />);
    await userEvent.click(screen.getByRole('tab', { name: 'Callback' }));
    expect(screen.getByTestId('stage-chart-Callback')).toBeInTheDocument();
  });

  it('shows an empty state when a stage has no data', async () => {
    render(<StageTabs breakdown={breakdown} />);
    await userEvent.click(screen.getByRole('tab', { name: 'Authenticity' }));
    expect(screen.getByText(/no data for this stage/i)).toBeInTheDocument();
  });
});
