import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import FraudSection from './FraudSection';

const mockApi = vi.hoisted(() => ({
  getFraudSummary: vi.fn(),
  getFraudEventual: vi.fn(),
  getFraudBurst: vi.fn(),
}));

vi.mock('../api/client', () => ({ api: mockApi }));

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FraudSection sources={['SRC_A']} />
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
  mockApi.getFraudBurst.mockResolvedValue({
    source: 'SRC_A',
    total_users: 100,
    burst_cases: 1,
    burst_pct: 1,
    rows: [{ BASE_TXN_ID: 'T9', TOTAL_ATTEMPTS: 5, MIN_GAP_SECONDS: 1, BURST_PAIRS: 4 }],
  });
});

describe('FraudSection', () => {
  it('disables the run button until a source is chosen', () => {
    renderSection();
    expect(screen.getByRole('button', { name: /run analysis/i })).toBeDisabled();
  });

  it('runs all three analyses and renders results', async () => {
    renderSection();

    await userEvent.selectOptions(screen.getByTestId('fraud-source'), 'SRC_A');
    await userEvent.click(screen.getByRole('button', { name: /run analysis/i }));

    await waitFor(() => expect(mockApi.getFraudSummary).toHaveBeenCalledWith('SRC_A', 10));
    expect(mockApi.getFraudEventual).toHaveBeenCalledWith('SRC_A', 10);
    expect(mockApi.getFraudBurst).toHaveBeenCalledWith('SRC_A', 2, 3);

    expect(await screen.findByText('100')).toBeInTheDocument();
    expect(await screen.findByText('b2~5')).toBeInTheDocument();
  });
});
