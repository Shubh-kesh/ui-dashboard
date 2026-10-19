import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import KpiCards from './KpiCards';

describe('KpiCards', () => {
  it('renders the total transactions KPI', () => {
    render(<KpiCards kpis={{ total_txns: 1500 }} />);

    expect(screen.getByTestId('kpi-total')).toHaveTextContent('1,500');
  });

  it('does not render callback KPIs', () => {
    render(<KpiCards kpis={{ total_txns: 10 }} />);

    expect(screen.queryByTestId('kpi-callback')).not.toBeInTheDocument();
    expect(screen.queryByTestId('kpi-latency')).not.toBeInTheDocument();
  });
});
