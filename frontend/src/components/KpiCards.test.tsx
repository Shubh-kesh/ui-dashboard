import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import KpiCards from './KpiCards';

describe('KpiCards', () => {
  it('renders the three KPI values', () => {
    render(<KpiCards kpis={{ total_txns: 1500, callback_success_rate: 92.5, avg_callback_latency: 1.234 }} />);

    expect(screen.getByTestId('kpi-total')).toHaveTextContent('1,500');
    expect(screen.getByTestId('kpi-callback')).toHaveTextContent('92.5%');
    expect(screen.getByTestId('kpi-latency')).toHaveTextContent('1.234s');
  });

  it('shows a dash when a KPI is unavailable', () => {
    render(<KpiCards kpis={{ total_txns: 0, callback_success_rate: null, avg_callback_latency: null }} />);

    expect(screen.getByTestId('kpi-callback')).toHaveTextContent('—');
    expect(screen.getByTestId('kpi-latency')).toHaveTextContent('—');
  });
});
