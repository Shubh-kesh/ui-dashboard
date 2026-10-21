import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import FraudSection from './FraudSection';

const mockApi = vi.hoisted(() => ({
  getFraudSummary: vi.fn(),
  getFraudEventual: vi.fn(),
  getFraudNeverSucceeded: vi.fn(),
}));

vi.mock('../api/client', () => ({ api: mockApi }));

function renderSection(source = 'SRC_A') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FraudSection source={source} start="2026-10-01" end="2026-10-07" table="live" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.getFraudSummary.mockResolvedValue({
    source: 'SRC_A',
    total_users: 100,
    quick_success_users: 12,
    quick_success_pct: 12,
  });
  mockApi.getFraudEventual.mockResolvedValue({
    source: 'SRC_A',
    rows: [{ BASE_TXN_ID: 'b2', TOTAL_ATTEMPTS: 5, SUCCESS_ATTEMPT_NO: 5, FAILED_ATTEMPTS_BEFORE_SUCCESS: 4, SUCCESS_TXN_ID: 'b2~5' }],
  });
  mockApi.getFraudNeverSucceeded.mockResolvedValue({
    source: 'SRC_A',
    rows: [
      { BASE_TXN_ID: 'n1', TOTAL_ATTEMPTS: 4 },
      { BASE_TXN_ID: 'n2', TOTAL_ATTEMPTS: 3 },
    ],
  });
});

describe('FraudSection', () => {
  it('disables the run button until a source is selected', () => {
    renderSection('');
    expect(screen.getByRole('button', { name: /run attempt analysis/i })).toBeDisabled();
    expect(screen.getByText(/select a source/i)).toBeInTheDocument();
  });

  it('runs the three analyses over the dashboard window and renders results', async () => {
    renderSection();

    await userEvent.click(screen.getByRole('button', { name: /run attempt analysis/i }));

    await waitFor(() =>
      expect(mockApi.getFraudSummary).toHaveBeenCalledWith('SRC_A', 3, '2026-10-01', '2026-10-07', 'live'),
    );
    expect(mockApi.getFraudEventual).toHaveBeenCalledWith('SRC_A', 2, '2026-10-01', '2026-10-07', 'live');
    expect(mockApi.getFraudNeverSucceeded).toHaveBeenCalledWith('SRC_A', 3, '2026-10-01', '2026-10-07', 'live');

    expect(await screen.findByText('100 unique users (BASE_TXN_ID) found for SRC_A')).toBeInTheDocument();
    expect(screen.getByText('12.0%')).toBeInTheDocument();
    expect(screen.getByText('1.0%')).toBeInTheDocument();
    expect(screen.getByText('2.0%')).toBeInTheDocument();
    expect(screen.getByText('b2~5')).toBeInTheDocument();
    expect(screen.getByText('n1')).toBeInTheDocument();
  });

  it('uses the configured thresholds on the next run', async () => {
    renderSection();

    await userEvent.clear(screen.getByTestId('fraud-quick'));
    await userEvent.type(screen.getByTestId('fraud-quick'), '5');
    await userEvent.clear(screen.getByTestId('fraud-min-failed'));
    await userEvent.type(screen.getByTestId('fraud-min-failed'), '4');
    await userEvent.clear(screen.getByTestId('fraud-min-attempts'));
    await userEvent.type(screen.getByTestId('fraud-min-attempts'), '6');
    await userEvent.click(screen.getByRole('button', { name: /run attempt analysis/i }));

    await waitFor(() =>
      expect(mockApi.getFraudSummary).toHaveBeenCalledWith('SRC_A', 5, '2026-10-01', '2026-10-07', 'live'),
    );
    expect(mockApi.getFraudEventual).toHaveBeenCalledWith('SRC_A', 4, '2026-10-01', '2026-10-07', 'live');
    expect(mockApi.getFraudNeverSucceeded).toHaveBeenCalledWith('SRC_A', 6, '2026-10-01', '2026-10-07', 'live');
  });
});
