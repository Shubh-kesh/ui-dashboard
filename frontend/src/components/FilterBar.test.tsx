import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import FilterBar from './FilterBar';

function setup(overrides: Partial<React.ComponentProps<typeof FilterBar>> = {}) {
  const handlers = {
    onStart: vi.fn(),
    onEnd: vi.fn(),
    onSource: vi.fn(),
    onTable: vi.fn(),
    onGranularity: vi.fn(),
    onStartTime: vi.fn(),
    onEndTime: vi.fn(),
    onRefresh: vi.fn(),
  };
  render(
    <FilterBar
      start="2026-10-13"
      end="2026-10-19"
      source=""
      sources={['MOBILE_APP']}
      table="live"
      granularity="auto"
      startTime="00:00"
      endTime="23:59"
      {...handlers}
      {...overrides}
    />,
  );
  return handlers;
}

describe('FilterBar', () => {
  it('emits the selected dataset and interval', async () => {
    const h = setup();
    await userEvent.selectOptions(screen.getByTestId('filter-table'), 'archive');
    expect(h.onTable).toHaveBeenCalledWith('archive');
    await userEvent.selectOptions(screen.getByTestId('filter-granularity'), '30m');
    expect(h.onGranularity).toHaveBeenCalledWith('30m');
  });

  it('shows the auto-select notice', () => {
    setup({ notice: 'Showing archived data (older than the live window).' });
    expect(screen.getByText(/showing archived data/i)).toBeInTheDocument();
  });
});
